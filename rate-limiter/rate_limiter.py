"""Rate limiters — Build Your Own Rate Limiter (codingchallenges.fyi).

Implements the challenge steps: token bucket, fixed window counter,
sliding window log, sliding window counter, plus a shared-store
variant of the sliding window counter for the multi-server step
(see docs/DESIGN.md for the honest Redis scope note).

Python 3 standard library only. Every limiter takes an optional
``now`` callable returning seconds (default: ``time.monotonic``);
tests inject :class:`FakeClock` so nothing depends on real time.

Common interface: ``allow(key, cost=1) -> bool``. An accepted
request is charged; a rejected request changes nothing.

Run the demo server (Step 1 endpoints, Step 2 defaults)::

    python3 rate_limiter.py [--port 8080] [--algorithm token-bucket]
                            [--capacity 10] [--rate 1]
                            [--window 60] [--limit 60]
"""

import argparse
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

__all__ = [
    "FakeClock",
    "TokenBucketLimiter",
    "FixedWindowLimiter",
    "SlidingWindowLogLimiter",
    "SlidingWindowCounterLimiter",
    "InMemorySharedStore",
    "SharedSlidingWindowCounterLimiter",
    "make_server",
]


def _check_cost(cost):
    if cost <= 0:
        raise ValueError("cost must be positive, got %r" % (cost,))


class FakeClock:
    """Deterministic clock for tests. Not used by the server."""

    def __init__(self, start=0.0):
        self._now = float(start)

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now += float(seconds)


class TokenBucketLimiter:
    """Token bucket: capacity tokens, refilled at a fixed rate.

    A new key starts with a full bucket. Refill accrues
    fractionally and lazily on each call; a full bucket
    discards overflow tokens.
    """

    def __init__(self, capacity, refill_per_second, now=None):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_second < 0:
            raise ValueError("refill_per_second must not be negative")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._buckets = {}  # key -> [tokens, last_refill_time]

    def _refill(self, key, now):
        tokens, last = self._buckets[key]
        elapsed = now - last
        if elapsed > 0:
            tokens = min(self.capacity, tokens + elapsed * self.refill_per_second)
            self._buckets[key] = [tokens, now]
        return tokens

    def allow(self, key, cost=1):
        _check_cost(cost)
        now = self._now()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = [self.capacity, now]
            tokens = self._refill(key, now)
            if tokens >= cost:
                self._buckets[key][0] = tokens - cost
                return True
            return False

    def remaining(self, key):
        now = self._now()
        with self._lock:
            if key not in self._buckets:
                return self.capacity
            return self._refill(key, now)

    def reset(self, key):
        with self._lock:
            self._buckets.pop(key, None)


class FixedWindowLimiter:
    """Fixed window counter: floor-aligned windows, count per window."""

    def __init__(self, window_seconds, limit, now=None):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.window_seconds = float(window_seconds)
        self.limit = limit
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._windows = {}  # key -> [window_start, count]

    def _window_start(self, now):
        return int(now // self.window_seconds) * self.window_seconds

    def allow(self, key, cost=1):
        _check_cost(cost)
        now = self._now()
        start = self._window_start(now)
        with self._lock:
            window = self._windows.get(key)
            if window is None or window[0] != start:
                window = [start, 0]
                self._windows[key] = window
            if window[1] + cost <= self.limit:
                window[1] += cost
                return True
            return False

    def remaining(self, key):
        now = self._now()
        start = self._window_start(now)
        with self._lock:
            window = self._windows.get(key)
            if window is None or window[0] != start:
                return self.limit
            return max(0, self.limit - window[1])

    def reset(self, key):
        with self._lock:
            self._windows.pop(key, None)


class SlidingWindowLogLimiter:
    """Sliding window log: one timestamp per accepted request."""

    def __init__(self, window_seconds, limit, now=None):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.window_seconds = float(window_seconds)
        self.limit = limit
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._logs = {}  # key -> deque of timestamps

    def _prune(self, key, now):
        log = self._logs[key]
        cutoff = now - self.window_seconds
        while log and log[0] <= cutoff:
            log.popleft()

    def allow(self, key, cost=1):
        _check_cost(cost)
        if cost != int(cost):
            # One log entry per request: fractional costs have no
            # meaning here, so refuse them instead of guessing.
            raise ValueError("sliding window log requires an integer cost")
        now = self._now()
        with self._lock:
            log = self._logs.setdefault(key, deque())
            self._prune(key, now)
            if len(log) + cost <= self.limit:
                for _ in range(int(cost)):
                    log.append(now)
                return True
            return False

    def remaining(self, key):
        now = self._now()
        with self._lock:
            log = self._logs.get(key)
            if log is None:
                return self.limit
            self._prune(key, now)
            return max(0, self.limit - len(log))

    def reset(self, key):
        with self._lock:
            self._logs.pop(key, None)


class SlidingWindowCounterLimiter:
    """Sliding window counter: current + weighted previous window.

    Weighted count = current_count + previous_count * (1 - elapsed
    fraction of the current window), per the challenge page.
    """

    def __init__(self, window_seconds, limit, now=None):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.window_seconds = float(window_seconds)
        self.limit = limit
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        # key -> [current_window_start, current_count, previous_count]
        self._state = {}

    def _window_start(self, now):
        return int(now // self.window_seconds) * self.window_seconds

    def _roll(self, key, start):
        state = self._state.get(key)
        if state is None:
            state = [start, 0, 0]
            self._state[key] = state
            return state
        if state[0] == start:
            return state
        if state[0] == start - self.window_seconds:
            state[2] = state[1]  # previous window becomes previous count
        else:
            state[2] = 0  # gap of 2+ windows: old counts are stale
        state[0] = start
        state[1] = 0
        return state

    def weighted_count(self, key, now=None):
        now = self._now() if now is None else now
        start = self._window_start(now)
        with self._lock:
            state = self._roll(key, start)
            elapsed_fraction = (now - start) / self.window_seconds
            return state[1] + state[2] * (1.0 - elapsed_fraction)

    def allow(self, key, cost=1):
        _check_cost(cost)
        now = self._now()
        start = self._window_start(now)
        with self._lock:
            state = self._roll(key, start)
            elapsed_fraction = (now - start) / self.window_seconds
            weighted = state[1] + state[2] * (1.0 - elapsed_fraction)
            if weighted + cost <= self.limit:
                state[1] += cost
                return True
            return False

    def remaining(self, key):
        return max(0.0, self.limit - self.weighted_count(key))

    def reset(self, key):
        with self._lock:
            self._state.pop(key, None)


class InMemorySharedStore:
    """Shared-state object for the multi-server step.

    Two limiter instances sharing one store enforce one combined
    allowance. This is in-process only: it does NOT provide the
    cross-process atomicity a real Redis store would. A Redis
    adapter implements the same ``get``/``set`` methods.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)


class SharedSlidingWindowCounterLimiter:
    """Sliding window counter whose state lives in a shared store.

    State per key: (current_window_start, current_count,
    previous_count). Instances sharing a store share an allowance,
    which is the property the challenge's two-server test checks.
    """

    def __init__(self, window_seconds, limit, store, now=None):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.window_seconds = float(window_seconds)
        self.limit = limit
        self.store = store
        self._now = now or time.monotonic
        self._lock = threading.Lock()

    def _window_start(self, now):
        return int(now // self.window_seconds) * self.window_seconds

    def allow(self, key, cost=1):
        _check_cost(cost)
        now = self._now()
        start = self._window_start(now)
        with self._lock:
            state = self.store.get(key)
            if state is None:
                current_start, current, previous = start, 0, 0
            else:
                current_start, current, previous = state
                if current_start == start:
                    pass
                elif current_start == start - self.window_seconds:
                    previous, current = current, 0
                    current_start = start
                else:
                    previous, current = 0, 0
                    current_start = start
            elapsed_fraction = (now - current_start) / self.window_seconds
            weighted = current + previous * (1.0 - elapsed_fraction)
            if weighted + cost <= self.limit:
                self.store.set(key, (current_start, current + cost, previous))
                return True
            self.store.set(key, (current_start, current, previous))
            return False

    def reset(self, key):
        with self._lock:
            self.store.delete(key)


# ---------------------------------------------------------------- server

UNLIMITED_BODY = "Unlimited! Let's Go!"
LIMITED_BODY = "Limited, don't over use me!"


def make_server(limiter, host="127.0.0.1", port=0):
    """Build a threaded HTTP server around a limiter instance.

    ``/limited`` is rate-limited per client IP, ``/unlimited``
    never is. Rejected requests get 429. Port 0 picks an
    ephemeral port (read it back from ``server.server_address``).
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, status, body):
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/unlimited":
                self._send(200, UNLIMITED_BODY)
            elif self.path == "/limited":
                if limiter.allow(self.client_address[0]):
                    self._send(200, LIMITED_BODY)
                else:
                    self._send(429, "Too Many Requests")
            else:
                self._send(404, "Not Found")

    return ThreadingHTTPServer((host, port), Handler)


def _build_limiter(args):
    if args.algorithm == "token-bucket":
        return TokenBucketLimiter(args.capacity, args.rate)
    if args.algorithm == "fixed-window":
        return FixedWindowLimiter(args.window, args.limit)
    if args.algorithm == "sliding-window-log":
        return SlidingWindowLogLimiter(args.window, args.limit)
    if args.algorithm == "sliding-window-counter":
        return SlidingWindowCounterLimiter(args.window, args.limit)
    raise ValueError("unknown algorithm: %r" % (args.algorithm,))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rate limiter demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--algorithm",
        default="token-bucket",
        choices=["token-bucket", "fixed-window",
                 "sliding-window-log", "sliding-window-counter"],
    )
    parser.add_argument("--capacity", type=float, default=10)
    parser.add_argument("--rate", type=float, default=1)
    parser.add_argument("--window", type=float, default=60)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args(argv)
    server = make_server(_build_limiter(args), args.host, args.port)
    print("Serving %s on http://%s:%d/ (Ctrl-C to stop)"
          % (args.algorithm, args.host, server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

# DESIGN — Rate Limiter

## Assumptions (stated before coding, per ponytail rules)

1. **Per-key state, in memory.** Each limiter keeps a dict
   keyed by client key (IP in the server, arbitrary string in
   the library). Keys are never evicted automatically: eviction
   policy is speculative without a stated requirement, and the
   page does not ask for one. Callers that need bounded memory
   can drop a limiter instance or use `reset(key)`.
2. **Lazy refill / lazy pruning.** Token refill and log
   pruning happen on `allow()`/`remaining()` calls for that
   key only — no background threads, no timers. This keeps the
   library single-file and deterministic under a fake clock.
3. **Monotonic time by default.** `time.monotonic` (not wall
   time) so a system clock jump cannot refill buckets or shift
   fixed windows. The fixed-window floor is therefore relative
   to process start, not to wall-clock 17:47:00 — the boundary
   behaviour (aligned windows, burst at the boundary) is
   identical; only the absolute phase differs. This is the one
   deliberate deviation from the page's wall-clock example.
4. **Token bucket starts full.** A new key's bucket starts at
   capacity, matching the page's Step 2 test (10 initial
   requests succeed, then failures begin).
5. **Fractional tokens.** Refill accrues fractionally
   (`elapsed × rate`); a request needs a whole token's worth
   of balance for `cost=1`. This is the standard reading of
   "1 token per second" and makes partial-second behaviour
   well-defined.
6. **Sliding window counter acceptance rule.** A request is
   accepted iff `weighted_count < limit` before charging, and
   an accepted request increments the current window count by
   `cost`. Rejected requests never change any count. At the
   exact start of a new window the previous weight is 1.0, so
   the previous window still counts in full — that is the
   smoothing the page describes, not a bug.
7. **Sliding window log boundary.** Entries with timestamp
   `<= now - window` are pruned (window is `(now-window, now]`),
   consistent with "logs beyond a threshold are discarded".
8. **Thread safety.** Library methods guard per-limiter state
   with a single `threading.Lock` so the HTTP server (threaded)
   can share one limiter safely. This is the minimum needed for
   the demo server, not a claim of multi-process safety.

## Components (single file: `rate_limiter.py`)

- `FakeClock` — test helper: `now()`, `advance(seconds)`.
  Lives in the main module so tests import it directly; it is
  tiny and has no production use.
- `TokenBucketLimiter(capacity, refill_per_second, now=None)`
- `FixedWindowLimiter(window_seconds, limit, now=None)`
- `SlidingWindowLogLimiter(window_seconds, limit, now=None)`
- `SlidingWindowCounterLimiter(window_seconds, limit, now=None)`
- `SharedSlidingWindowCounterLimiter` — Step 6 shape (below).
- `InMemorySharedStore` — dict-backed store object that can be
  shared between limiter instances.
- HTTP demo server (`http.server.ThreadingHTTPServer`):
  `make_server(limiter, host, port)` returns a server whose
  handler serves `/limited` (through the limiter, keyed by
  client IP) and `/unlimited` (never limited). 429 body is
  plain text; no `Retry-After` header is promised because the
  page does not ask for one.
- CLI: `python3 rate_limiter.py [--algorithm ...] [--port ...]`
  plus `--capacity/--rate/--window/--limit` overrides. Defaults
  are the page's Step 2 values (token bucket, 10, 1/s) on port
  8080, matching the page's curl examples.

## Step 6 — distributed limiting, honest scope

The page's Step 6 needs a Redis server. This project is
Python-standard-library-only and the task forbids extra
services, so no real Redis connection is built. Instead:

- The shared-state logic is implemented and tested: a store
  object exposes `get(key)` / `set(key, value)` / `delete(key)` for the
  sliding-window-counter state (previous count, current window
  start, current count). Two limiter instances sharing one
  store enforce one combined allowance — the same property the
  page's two-server test checks, minus the network hop.
- A Redis adapter would be a ~20-line class implementing the
  same two methods over `INCR`/`GET`/`SET` (or a Lua script for
  atomicity); it is documented here as the extension point
  rather than faked with an in-process dict pretending to be
  Redis. Atomicity across real processes is exactly what the
  in-memory store does NOT provide, and that limitation is
  stated in the README rather than hidden.

## What was deliberately NOT built

- Leaky bucket as a meter: equivalent to token bucket (page).
- Leaky bucket as a queue: listed, not a required step.
- Redis client, load balancer, Postman tests: out of scope
  (see SPEC.md); the demo server is testable with curl and
  with the unit tests' ephemeral-port server.
- Automatic key eviction, persistence, per-route or
  per-user-tier limits: not asked for by the page.

## Verifiable success criteria

- Every algorithm's boundary behaviour is pinned by a fake-
  clock test (full bucket, empty bucket, refill, window
  rollover, boundary burst, weighted smoothing).
- The demo server returns the page's exact bodies, 200 for
  `/unlimited` always, 200 then 429 for `/limited` past the
  allowance, with no real-time sleeps in tests.
- `python3 -m unittest discover -s tests -v` passes fully.

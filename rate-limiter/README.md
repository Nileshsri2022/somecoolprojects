# rate-limiter — Build Your Own Rate Limiter

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Implements the challenge steps from
https://codingchallenges.fyi/challenges/challenge-rate-limiter/ :

- **Step 1** — demo HTTP server with `/limited` and `/unlimited`.
- **Step 2** — token bucket, per key, capacity 10, 1 token/second,
  429 when the bucket is empty.
- **Step 3** — fixed window counter (floor-aligned windows).
- **Step 4** — sliding window log (one timestamp per request).
- **Step 5** — sliding window counter (current + weighted
  previous window).
- **Step 6** — shared-store sliding window counter: two limiter
  instances sharing one store enforce one combined allowance,
  the same property the page's two-server test checks.

## Usage

```sh
# Demo server, page defaults (token bucket 10, 1/s, port 8080)
python3 rate_limiter.py
curl http://127.0.0.1:8080/unlimited   # Unlimited! Let's Go!
curl http://127.0.0.1:8080/limited     # Limited, don't over use me!
# ... 11th rapid /limited request -> 429 Too Many Requests

# Other algorithms
python3 rate_limiter.py --algorithm fixed-window --window 60 --limit 60
python3 rate_limiter.py --algorithm sliding-window-counter --window 60 --limit 60
python3 rate_limiter.py --algorithm sliding-window-log --window 60 --limit 60
```

Library use (any key — IP, user id, API token):

```python
from rate_limiter import TokenBucketLimiter, FakeClock

clock = FakeClock()  # or omit `now=` to use time.monotonic
limiter = TokenBucketLimiter(capacity=10, refill_per_second=1,
                             now=clock.now)
limiter.allow("192.0.2.1")  # True until the bucket empties
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

21 tests, all driven by a fake clock — no test sleeps or
depends on real time. They cover every algorithm's boundary
behaviour (full/empty bucket, refill cap, window rollover and
boundary burst, log expiry, the page's 40%/60% weighted
example), the shared-store allowance, and the demo server on
an ephemeral port (exact bodies, 200 then 429, 404).

## Files

- `rate_limiter.py` — all four limiters, shared-store variant,
  demo server, CLI. Standard library only.
- `docs/SPEC.md` — challenge steps and interface.
- `docs/DESIGN.md` — assumptions and design decisions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_rate_limiter.py` — the test suite.

## Divergences from the page (documented, not hidden)

- **Fixed windows use monotonic time**, not wall-clock time,
  so a system clock jump cannot shift windows. Boundaries are
  still floor-aligned; only the absolute phase differs from
  the page's 17:47:00 example.
- **Leaky bucket as a meter is not a separate class**: the
  page itself calls it equivalent to the token bucket.
  Leaky bucket as a queue is listed but is not a required
  step (Steps 2–5), so it is not built.
- **Step 6 has no real Redis client.** The project is
  stdlib-only and no Redis server is in scope, so the shared
  state is a store object (`get`/`set`/`delete`) with an
  in-memory implementation; a Redis adapter is the documented
  extension point. The in-memory store does NOT give
  cross-process atomicity — that limitation is stated here
  rather than papered over.
- **No automatic key eviction or persistence**: not asked
  for by the page; see `docs/DESIGN.md`.

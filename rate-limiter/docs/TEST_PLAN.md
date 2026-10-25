# TEST_PLAN — Rate Limiter

All tests use `FakeClock` — no test sleeps or depends on
real time. Run:

```sh
python3 -m unittest discover -s tests -v
```

## Token bucket (`test_token_bucket`)

- New key starts full: 10 accepts at capacity 10, 11th rejected.
- Rejected requests do not consume: after rejection, still
  rejected until refill.
- Refill: after 1 s at 1 token/s, exactly 1 more accept; after
  10 s idle, bucket caps at 10 (no overflow credit).
- Fractional refill: 0.5 s gives no new token for cost 1.
- Keys are independent: exhausting key A leaves key B full.
- `cost` validation: 0 / negative raises `ValueError`;
  cost > capacity is never accepted.
- `remaining()` tracks balance (10 → 9 after one accept).

## Fixed window (`test_fixed_window`)

- Limit accepts up to the threshold, then rejects, within one
  window (page example shape: 60 requests / 60 s, tested at
  small scale: 3 / 10 s).
- Window rollover resets the count: requests just after the
  boundary succeed again (the page's boundary burst).
- Windows are floor-aligned: a request at t=9 and t=10 with a
  10 s window fall in different windows.
- Keys are independent.

## Sliding window log (`test_sliding_window_log`)

- Accepts up to the limit, then rejects.
- Old entries expire: after the window slides past the first
  requests, new requests are accepted again.
- Rejected requests are not logged: a rejected request does
  not itself extend the block.
- Boundary: an entry exactly one window old is pruned.

## Sliding window counter (`test_sliding_window_counter`)

- Accepts up to the limit in a fresh window, then rejects.
- Smoothing: previous window full (limit requests), 40%
  through the new window → weighted count ≈ 60% of limit, so
  only the remaining ~40% are accepted (page's 40%/60%
  example, at small scale).
- Window rollover: two windows later, the old previous count
  no longer counts at all.
- Keys are independent.

## Shared store / Step 6 (`test_shared_counter`)

- Two limiter instances sharing one `InMemorySharedStore`
  enforce a single combined allowance: exhausting it through
  instance A makes instance B reject.
- A limiter with its own store does not share: same key, full
  allowance on the second instance.

## Demo server (`test_server`)

- Server on an ephemeral port (port 0), threaded, shut down
  explicitly in tearDown.
- `GET /unlimited` → 200 `Unlimited! Let's Go!` every time.
- `GET /limited` → 200 `Limited, don't over use me!` up to
  the allowance, then 429 (token bucket capacity 2, refill 0
  for determinism — refill 0 is a test-only configuration).
- Unknown path → 404. Different client keys are not
  distinguished by the loopback test (all from 127.0.0.1),
  so per-IP separation is covered at library level instead.

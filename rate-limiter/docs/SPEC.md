# SPEC — Build Your Own Rate Limiter

Source: https://codingchallenges.fyi/challenges/challenge-rate-limiter/
Page slug: `challenge-rate-limiter` (first guess, no 404 — no correction needed).
Challenge number on the site: #27 in the newsletter; this repo entry is 28.

## Goal

Build an API rate limiter: stop one client (or a burst) from
overloading a service, while letting everyone else through.

## Steps from the page, and what this project implements

### Step 1 — Test API

Two endpoints:

- `GET /unlimited` → 200, body `Unlimited! Let's Go!`
- `GET /limited` → 200, body `Limited, don't over use me!`
  while the caller is within its allowance.

A request rejected by the limiter returns HTTP **429 Too Many
Requests**.

### Step 2 — Token bucket (per IP)

- One bucket per key (client IP in the server; any string key in
  the library).
- Capacity **10 tokens**; tokens are added at **1 token per second**.
- A full bucket discards newly added tokens (no overflow).
- A request is accepted only if the bucket holds at least one
  token; an accepted request removes one token.
- A request arriving at an empty bucket is declined (429).

### Step 3 — Fixed window counter

- A window of N seconds tracks the request count per key.
- Each request increments the counter for its window; a request
  that would push the counter past the threshold is rejected.
- Windows are aligned to the floor of the timestamp: e.g. with a
  60 s window, 17:47:13 falls in the 17:47:00 window.
- Page example: 60 s window, 60-request threshold.

### Step 4 — Sliding window log

- Keep a timestamped log per key, sorted by time.
- On each request, discard log entries older than the window,
  then accept the request only if adding it would not exceed
  the threshold.
- Advantage (per page): no fixed-window boundary burst.
- Disadvantage (per page): unbounded log growth per key, so
  summation gets expensive under bursts — it does not scale
  as well as the counter variants.

### Step 5 — Sliding window counter

- Hybrid of fixed window (cheap) and sliding log (smooth).
- Keep the current window's count and the previous window's
  count per key.
- Weighted count = current count + previous count ×
  (1 − fraction of the current window elapsed).
  Page example: 40% through the current window → previous
  count weighted by 60%.
- Accept only if the weighted count is below the threshold;
  an accepted request increments the current window's count.

### Step 6 — Rate limiting across several servers (Redis)

- The page asks for the counts to live in Redis so two or more
  servers share one allowance (e.g. 60 requests/minute total
  across servers, not 60 per server).
- See DESIGN.md for how this is honoured without a Redis
  server, and what is deliberately not built.

## Algorithms listed but NOT required as separate steps

The page lists six approaches. The leaky bucket "as a meter"
is, by the page's own words, the mirror image of / equivalent
to the token bucket, so it is not implemented as a separate
class (see DESIGN.md). The leaky bucket "as a queue" (FIFO
queue with limited capacity, requests processed at a fixed
rate) is listed but is not one of the steps the page asks to
implement (Steps 2–5 are token bucket, fixed window, sliding
log, sliding window counter); it is likewise out of scope.

## Common interface (library)

Every limiter is constructed with its parameters plus an
optional clock, and exposes:

- `allow(key, cost=1) -> bool` — True = request accepted
  (and charged), False = rejected (not charged).
- `remaining(key) -> float | int` — best-effort estimate of
  headroom for that key, for diagnostics only.

`cost` must be a positive number; anything else raises
`ValueError`. A `cost` larger than a token bucket's capacity
can never be accepted.

## Clock

Library limiters take a `now` callable returning seconds as a
float (default: `time.monotonic`). Tests inject a fake clock
so no test depends on real-time sleeps. The demo server uses
the real clock.

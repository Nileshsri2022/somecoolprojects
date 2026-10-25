# http-load-tester — TEST_PLAN

All tests live in `tests/test_load_tester.py`, run with:

```sh
python3 -m unittest discover -s tests -v
```

## Test server (no real network, no real-time correctness)

A `ThreadingHTTPServer` on an ephemeral port (`port 0`, OS-assigned)
started per test and shut down in tearDown, with deterministic
endpoints:

- `/ok` — 200, small fixed body.
- `/error` — 500, small fixed body.
- `/notfound` — 404.
- `/slow` — sleeps 0.2 s, then 200. Used only for timeout and
  duration tests with loose bounds, never for exact timing asserts.
- `/redirect` — 301 (verifies redirects are reported, not followed).
- A request counter (lock-guarded) proves exactly N requests
  arrived, independent of what the client counted.

HTTPS: a second server wrapped with a locally generated self-signed
certificate (`openssl req -x509`, temp dir, per test class). It is
used to verify two real behaviours: `--insecure` succeeds against
the self-signed cert, and verified mode fails with an error result
(no response, error recorded, run does not crash). If `openssl` is
absent the HTTPS tests skip themselves rather than failing.

## Cases

Stats (pure, deterministic — no server, no clock):

1. `compute_stats` on a fixed list: exact min/max/mean.
2. `compute_stats` percentiles (nearest-rank) on 1..10: p50=5,
   p90=9, p99=10.
3. `compute_stats` on an empty list: all fields None (no crash).
4. `summarise` on hand-built results: 2XX/5XX counts, per-code
   breakdown, successes/failures, error count, rps > 0.

Single request / count / concurrency (local server):

5. One request to `/ok`: status 200, timings present, TTFB <= total,
   TTLB >= 0, total == TTFB + TTLB (within float rounding).
6. `-n` exactness: `run_load` with n=20 returns 20 results and the
   server counter reads exactly 20.
7. Concurrency: n=20, c=5, all 200, server counter exactly 20.
8. Sequential default (c=1) still delivers all requests.
9. Mixed statuses via one run: `/ok` + `/error` + `/notfound`
   (file-cycled, c=1) give the exact per-code breakdown.
10. Redirect: `/redirect` reports status 301, not a followed 200.

Errors:

11. Connection refused (closed port): status None, error set, run
    completes with all results recorded, no exception escapes.
12. Per-request timeout: `/slow` with timeout 0.05 s yields an error
    result, not a 200.
13. Unsupported scheme (`ftp://...`): library returns an error
    result; CLI exits 2.

File mode:

14. URLs file with `/ok` and `/error`, n=4, c=1: each URL hit twice
    (round-robin cycling, server counters prove it).
15. Blank lines in the file are skipped.
16. Missing file: CLI exits 2 with an error on stderr.

Duration mode (loose bounds only — timing, not correctness):

17. Duration-only run against `/slow`: at least one result, wall
    time well under duration + slack (deadline gates new starts).
18. Count + duration together: a huge count with a short duration
    finishes with far fewer than the count (duration wins).

CLI (subprocess, real entry point):

19. Bare positional URL prints exactly `Response code: 200`.
20. `-u URL -n 1` prints `Response code: 200`.
21. Multi-request run prints `Results:`, the page's
    `Total Requests (2XX)` line, `Request/second`, and a
    `Status codes` line.
22. No URL at all: exit 2.
23. HTTPS via CLI with `--insecure` against the self-signed server:
    `Response code: 200` (this is the verified-HTTPS claim; without
    it, no HTTPS claim is made).

## What is deliberately NOT asserted

- Exact request/second or latency values against a live server
  (machine-dependent, flaky by construction).
- Behaviour against third-party sites (permission/safety, and
  non-deterministic).
- Exact wall time equalling the duration limit (in-flight requests
  may overrun it; see DESIGN.md).

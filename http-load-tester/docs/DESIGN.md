# http-load-tester — DESIGN

Assumptions, stated before coding (ponytail: think first, minimum
code, nothing speculative).

## Pipeline

```
argv
  -> parse_args()        argparse; resolve -n default (1 positional, else 10)
  -> load_urls()         positional / -u / -f (round-robin list)
  -> run_load()          thread pool, one request per worker slot
  -> do_request()        http.client, timings around getresponse()/read()
  -> summarise()         counts, per-code breakdown, stats
  -> format_summary()    page's Step 5 layout + extra lines
```

One file, `load_tester.py`, stdlib only: `argparse`, `http.client`,
`ssl`, `threading`, `time`, `urllib.parse`, `dataclasses`, `math`,
`collections`.

## Why http.client, not urllib

`urllib.request.urlopen` returns only after headers, but it also
follows redirects and raises on 4XX/5XX, which would blur the status
breakdown the page asks for. `http.client` gives the three things the
stats need directly and separately: `getresponse()` marks first byte
(headers received), `read()` marks last byte, and `resp.status` is
just a number for every code range — no exceptions for 4XX/5XX.
Redirects are therefore NOT followed; a 3XX is reported as a 3XX.
That is a deliberate simplification, recorded here: a load tester
measuring a redirecting endpoint measures the redirect responses,
which is honest and predictable.

## Data structures

```python
@dataclass RequestResult:
    url: str
    status: int | None      # None => no HTTP response (network error)
    total: float | None     # seconds; None on error before completion
    ttfb: float | None
    ttlb: float | None
    error: str | None

@dataclass Summary:
    results: list[RequestResult]
    wall_time: float        # whole run, first dispatch to last finish
    # derived by summarise(): counts, status_counts, error_count,
    # successes, failures, requests_per_second, stats dicts
```

Timings use `time.monotonic()`, never wall-clock time, so clock
adjustments cannot corrupt a measurement. Only completed requests
(status is not None) contribute timing stats; errored requests
contribute to the error count only. An all-errors run therefore
prints `n/a` for timing lines instead of crashing on an empty list.

## Percentiles

Nearest-rank: sort ascending, take element
`ceil(p / 100 * n)` (1-indexed). Deterministic, trivially testable
with fixed lists, no interpolation arguments. p50/p90/p99 are
reported for total request time only; min/max/mean are reported for
total, TTFB, and TTLB, matching the page's Step 5 lines.

## Concurrency and limits

- Workers are plain `threading.Thread`s (one per `-c` slot), each
  looping: claim the next request index under a lock, run it, append
  its result. A thread pool with a shared counter is the smallest
  shape that gives exact-count runs: `run_load` returns exactly `n`
  results for a count run, no more, no fewer.
- Duration (`-d`): a monotonic deadline. Workers check it before
  claiming each new request; a request already in flight is allowed
  to finish (the deadline gates starts, it does not abort sockets —
  aborting mid-request would corrupt that request's timing and is
  not what "stop after N seconds" means for a report). Consequence,
  documented: wall time may exceed the deadline by up to one
  slowest in-flight request.
- Count + duration together: whichever limit is hit first stops
  claiming. Duration alone: count is unbounded.
- Concurrency is capped by the work available: `-c 50 -n 3` spawns
  3 effective workers' worth of work (threads are still created, but
  extra threads exit immediately on an empty claim — harmless and
  simpler than min() bookkeeping; the claim loop handles it).

## HTTPS

`https` URLs use `ssl.create_default_context()` (certificate
verification on, system CA store). `--insecure` substitutes
`ssl._create_unverified_context()`. No custom CA option — out of
scope. HTTP and HTTPS share the same code path; only the connection
class and context differ. Host header handling is left to
`http.client` defaults, plus `User-Agent: ccload/1.0` and
`Connection: close` so each request is a fresh, independently timed
connection (keep-alive reuse would make later requests' timings
incomparable with the first — a load tester that reuses one
connection is measuring something else).

## Errors

Any exception from connect/send/read (connection refused, DNS
failure, timeout, TLS failure, malformed response) becomes a
`RequestResult` with `status=None` and `error=str(exc)`. The run
never aborts on a single request's failure. Invalid CLI input
(unsupported scheme, empty host, missing file, non-positive counts)
is a usage error before any request is sent: stderr + exit 2.

## Assumptions

1. GET-like requests with no body are sufficient for the page's
   steps; the page's own examples are all GETs.
2. The page gives no `-c` default, no duration option, and no
   TTLB definition — the choices above (1, extension, body-drain)
   are the documented resolutions, not page text.
3. Tests must not depend on real time for correctness: fixed
   latency lists for stats, a fixed-delay server for timing
   invariants (TTFB <= total, TTLB >= 0), and only loose upper
   bounds for duration-mode wall time.

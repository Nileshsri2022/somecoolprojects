# http-load-tester — SPEC

Coding Challenges: Build Your Own HTTP(S) Load Tester
(https://codingchallenges.fyi/challenges/challenge-load-tester/,
slug `challenge-load-tester` — worked first try, no 404, no correction
needed. The same steps appear in the Substack mirror, challenge #42.)

## What it is

A command-line load tester (`load_tester.py`, Python 3 standard library
only): it fires a number of concurrent HTTP(S) requests at a URL (or a
list of URLs from a file), records per-request timings and status codes,
and prints a summary. Think of it as `curl` on steroids, with metrics.

Safety note from the page, repeated here because it matters: only load
test a site you own or have permission to test — at volume this looks
like, and can become, a denial-of-service attack. The tests in this
project only ever hit a local test server.

## Challenge steps (from the page)

- **Step 0 — setup / target:** pick a language and a target. Python 3
  stdlib; the target for testing is a local HTTP server (see
  `tests/test_load_tester.py`), never a third-party site.
- **Step 1 — one request:** read a URL from the command line, make one
  request, print its response code:

  ```
  % ccload http://eu.httpbin.org/get
  Response code: 200
  ```
- **Step 2 — request count:** `-u` for the URL (default: none), `-n`
  for the number of requests (default: 10):

  ```
  % ccload -u http://eu.httpbin.org/get -n 1
  Response code: 200
  ```
- **Step 3 — concurrency:** `-c` for the number of concurrent
  requests; stop reporting each result and print a brief summary
  instead. Handle the different HTTP response-code ranges as well as
  network errors:

  ```
  % ccload -u http://localhost:8000 -n 100 -c 10
  Successes: 100
  Failures: 0
  ```
- **Step 4 — gather stats per request:** total time, time to first
  byte, time to last byte, plus the count of responses per HTTP
  response code, collected in a suitable data structure.
- **Step 5 — report the stats** in a summary, e.g.:

  ```
  Results:
   Total Requests (2XX).......................: 100
   Failed Requests (5XX)......................: 0
   Request/second.............................: 79.57
  Total Request Time (s) (Min, Max, Mean).....: 0.15, 0.65, 0.35
  Time to First Byte (s) (Min, Max, Mean).....: 0.1, 0.5, 0.25
  Time to Last Byte (s) (Min, Max, Mean)......: 0.12, 0.6, 0.27
  ```
- **Step 6 — URLs from a file:** `-f urls.txt` reads the URLs to test.
  If there are fewer URLs than requests, the URLs are simply
  repeated (round-robin): 10 URLs and 100 requests means each URL is
  requested 10 times.

## Supported CLI

```
python3 load_tester.py [URL] [-u URL] [-n N] [-c C] [-f FILE]
                       [-d SECONDS] [-X METHOD] [--timeout SECONDS]
                       [--insecure]
```

- `URL` (positional) or `-u/--url`: the URL to test. One of the
  positional URL, `-u`, or `-f` is required.
- `-n/--requests`: number of requests. Default 10 with `-u`/`-f`;
  default 1 with a bare positional URL (Step 1 behaviour).
- `-c/--concurrency`: concurrent workers. Default 1 (sequential).
  The page gives no default for `-c`; 1 preserves the pre-Step-3
  sequential behaviour until the user asks for concurrency.
- `-f/--file`: file with one URL per line; blank lines are skipped.
  URLs are cycled round-robin. Takes precedence over `-u`/positional
  when both are given (documented choice; the page does not say).
- `-d/--duration`: stop starting new requests after this many
  seconds. See DESIGN.md — this is an extension beyond the page,
  added because a count-only tester cannot do a "sustain this load
  for 30s" run. If both `-n` and `-d` are given, whichever limit is
  hit first stops the run. If only `-d` is given, the request count
  is unlimited until the deadline.
- `-X/--method`: HTTP method, default `GET`. No request body is sent
  (bodies/POST/PUT scripting are a "Going Further" item, not built).
- `--timeout`: per-request timeout in seconds, default 30.
- `--insecure`: skip TLS certificate verification (for local
  self-signed test servers). By default HTTPS verifies certificates
  with the stdlib default SSL context.

## Output

- Single request (`-n 1`, no `-d`): exactly the page's Step 1/2 form:

  ```
  Response code: 200
  ```

  On a network error instead: `Error: <message>` on stderr, exit 1.
- Multi-request run: a `Results:` summary in the page's Step 5 form,
  extended with lines the page invites ("feel free to add other
  stats"): `Successes`/`Failures` (Step 3 form), total request count,
  p50/p90/p99 of total request time, a per-status-code breakdown, and
  an error count. `Successes` = 2XX responses; `Failures` = everything
  else (non-2XX responses plus network errors). `Failed Requests
  (5XX)` counts 5XX responses only, exactly as labelled.
- Exit code is 0 for a completed run (even with failures — the report
  is the product); 2 for argument/usage errors (bad URL, missing
  file, non-positive `-n`/`-c`, negative `-d`).

## Timing definitions

- Total time: start of request to body fully read.
- Time to first byte (TTFB): start of request to response headers
  received.
- Time to last byte (TTLB): headers received to body fully read
  (the body-drain time). So total = TTFB + TTLB by construction.
  The page's example numbers do not satisfy any consistent reading
  of these definitions, so they are treated as illustrative only;
  these definitions are the ones implemented and tested.

## What is NOT built (page's "Going Further", out of scope)

Scripting of requests, POST/PUT bodies, export to a metrics format,
distributed testing across clients, graphs.

# http-load-tester — Build Your Own HTTP(S) Load Tester

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.
Page: https://codingchallenges.fyi/challenges/challenge-load-tester/

Fires concurrent HTTP(S) requests at a URL (or URLs cycled from a
file), records per-request timings and status codes, and prints a
summary in the challenge's Step 5 form, extended with percentiles,
a per-code breakdown, and an error count.

Only load test targets you own or have permission to test.

## Usage

```sh
# Step 1/2: one request, prints its response code
python3 load_tester.py http://127.0.0.1:8000/
Response code: 200

# Step 3/5: 100 requests, 10 concurrent, summary report
python3 load_tester.py -u http://127.0.0.1:8000/ -n 100 -c 10

# Step 6: URLs from a file, cycled round-robin
python3 load_tester.py -f urls.txt -n 100 -c 10

# Sustain load for 30 seconds instead of a fixed count
python3 load_tester.py -u http://127.0.0.1:8000/ -d 30 -c 10

# HTTPS against a local self-signed server
python3 load_tester.py -u https://127.0.0.1:8443/ -n 10 --insecure
```

Defaults: `-n 10` (or 1 for a bare positional URL), `-c 1`,
`--timeout 30`, method `GET`. With both `-n` and `-d`, whichever
limit is hit first stops the run; with `-d` alone the count is
unlimited until the deadline.

Sample summary output:

```
Results:
 Total Requests (2XX).......................: 100
 Failed Requests (5XX)......................: 0
 Successes..................................: 100
 Failures...................................: 0
 Total Requests.............................: 100
 Request/second.............................: 79.57
Total Request Time (s) (Min, Max, Mean).....: 0.150, 0.650, 0.350
Time to First Byte (s) (Min, Max, Mean).....: 0.100, 0.500, 0.250
Time to Last Byte (s) (Min, Max, Mean)......: 0.120, 0.600, 0.270
Total Request Time percentiles (s) (p50, p90, p99): 0.300, 0.550, 0.640
Status codes...............................: 200: 100
Errors.....................................: 0
```

Timing definitions: total = request start to body fully read;
time to first byte = start to headers received; time to last byte
= headers received to body fully read (so total = TTFB + TTLB).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use only local servers on ephemeral ports (HTTP plus a
self-signed HTTPS server); they never touch a third-party site.

## Files

- `load_tester.py` — CLI, request engine, stats, summary formatting.
- `docs/SPEC.md` — challenge spec and supported CLI.
- `docs/DESIGN.md` — pipeline, assumptions, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_load_tester.py` — the test suite.

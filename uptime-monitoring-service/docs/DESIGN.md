# DESIGN — Uptime Monitoring Service

## Stack

Python 3 standard library only. One main file,
`uptime_monitor.py`, plus the `tests/` suite. No third-party
packages, no database server.

## Store format

One JSON file (`--store PATH`, default `uptime-store.json`):

```json
{
  "targets": [
    {"url": "http://127.0.0.1:PORT/health", "interval_seconds": 60,
     "method": "HEAD", "slow_threshold_ms": 1000, "alert_after": 3,
     "alert_log": null, "webhook": null, "email_hook": null}
  ],
  "checks": [ {"url": ..., "timestamp": "2026-10-25T17:00:00+00:00",
               "status": 200, "ok": true, "latency_ms": 12.3,
               "ttfb_ms": null, "total_ms": 12.3, "method": "HEAD",
               "error": null} ],
  "alerts": [ {"url": ..., "timestamp": ..., "kind": "DOWN",
               "message": ..., "consecutive_failures": 3} ],
  "state": { "<url>": {"consecutive_failures": 0, "alerting": false} }
}
```

`state` is the per-target incident memory that makes DOWN alerts
fire once per incident and enables RECOVERY alerts. It is stored
in the same file so a restarted `run` does not re-alert for an
ongoing incident.

Reads tolerate a missing file (empty store) and a corrupt file
raises a clear error instead of silently discarding history.

## Checking

- HEAD: `http.client` with the URL's scheme/host/port/path, so
  only headers are requested and no body is downloaded. Timeout
  10 s (hard cap; a hung target becomes a failed check, not a hung
  monitor). HTTPS uses `HTTPSConnection` with default context.
- GET: `urllib.request` with a streaming read. TTFB is measured
  from request start to first byte read (first `read(1)`); total
  is measured to end of body. The body is consumed and discarded
  (monitoring does not need to keep it). HTTP errors
  (`HTTPError`) still record their status code (4xx/5xx → DOWN);
  `URLError`/timeouts record `status: null` with an error string.
- Any unexpected exception in one target's check is caught and
  recorded as a failed check for that target only; one bad target
  never kills the loop for the others.

## Monitor loop (`run`)

Single-threaded, sequential: each iteration, check every target
whose `interval_seconds` has elapsed since its last check (or
never checked), then sleep 1 s. `--cycles` bounds iterations for
testing/scripting; `--max-seconds` bounds wall time. Both default
to unbounded (Ctrl-C stops it; `KeyboardInterrupt` exits 0 with a
summary line). Sequential checks keep timing honest and avoid
thread-safety issues in the JSON store; intervals below 1 s are
rejected at `add` time.

## Alerts

After each recorded check, `evaluate_alerts()` runs for that
target:

- Failure → increment `consecutive_failures`. If it reaches
  `alert_after` and `alerting` is false → emit DOWN alert, set
  `alerting: true`.
- Success → if `alerting` is true → emit RECOVERY alert, reset
  counter and flag. If `slow_threshold_ms` set and latency
  exceeds it → emit SLOW alert (independent of the DOWN counter).
- Sinks, in order, best-effort (a failing sink never fails the
  check): append a line to `alert_log` (if set); append a
  formatted message to `email_hook` (if set); POST the alert
  JSON to `webhook` (if set, 5 s timeout, failures swallowed and
  noted in the returned sink result, not raised).
- Every emitted alert is also appended to the store's `alerts`
  list, so `alerts`/`report` show history even with no sinks.

## Reporting

`report` filters checks by URL (optional) and `--from`/`--to`
(ISO-8601, inclusive, UTC assumed for naive values). It prints:
check count, up count, uptime %, avg/min/max latency, and for
GET checks avg TTFB, plus a per-check table (newest last) and an
ASCII sparkline of latencies (`▁▂▃▄▅▆▇█` scaled to max). No
checks in range → "no checks in range" and uptime "n/a".

`export` writes the same filtered checks as JSON (array) or CSV
(header row + one row per check) to `--out`.

## CLI parsing

`argparse` with subcommands. Errors (unknown target on `remove`,
bad URL, interval < 1, bad method, bad date) exit non-zero with
a message on stderr; nothing is written to the store on a failed
`add`/`remove`. URL validation: must parse with http/https
scheme and a host.

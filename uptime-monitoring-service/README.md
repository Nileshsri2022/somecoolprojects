# Uptime Monitoring Service

A command-line uptime monitor in Python 3 (standard library only),
built from the Coding Challenges spec:
https://codingchallenges.fyi/challenges/challenge-uptime-monitoring

It monitors URLs on a schedule (HTTP HEAD by default, GET on
request), records up/down history with latency (and TTFB for GET),
prints historical reports with an ASCII latency graph, exports
history as JSON/CSV, and fires alerts after N consecutive failures
or when a target is too slow — via a log file, a webhook POST, or
an email-hook file (no real SMTP; see `docs/SPEC.md`).

## Usage

```bash
# Add a target (checked every 60 s by default, HEAD)
python3 uptime_monitor.py add --url http://127.0.0.1:8000/health --interval 60

# GET checks with a slow threshold + alerts after 2 failures
python3 uptime_monitor.py add --url http://127.0.0.1:8000/ --method GET \
  --slow-threshold-ms 1000 --alert-after 2 \
  --alert-log alerts.log --webhook http://127.0.0.1:9000/hook \
  --email-hook email-outbox.txt

python3 uptime_monitor.py list
python3 uptime_monitor.py check                 # one immediate cycle
python3 uptime_monitor.py run --cycles 10       # monitor loop (omit --cycles to run until Ctrl-C)
python3 uptime_monitor.py report --url http://127.0.0.1:8000/health
python3 uptime_monitor.py report --from 2026-10-25T00:00:00 --to 2026-10-26T00:00:00
python3 uptime_monitor.py export --format csv --out history.csv
python3 uptime_monitor.py alerts
python3 uptime_monitor.py remove --url http://127.0.0.1:8000/health
```

All commands accept `--store PATH` (default `uptime-store.json` in
the current directory).

## Files

- `uptime_monitor.py` — the whole monitor (CLI, checker, store, alerts, reports)
- `docs/SPEC.md` — challenge-step coverage, divergences, scope limits
- `docs/DESIGN.md` — store format, checking, alert rules
- `docs/TEST_PLAN.md` — what the suite covers
- `tests/test_uptime_monitor.py` — unittest suite (local fake servers only)

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Scope limits (honest)

No hosted/cloud monitoring, no dashboard UI (CLI + ASCII graph
only), no SMS/pager alerts, no real email sending, no content
matching, no SSL expiry checks, no auth/multi-user support. Full
list in `docs/SPEC.md`.

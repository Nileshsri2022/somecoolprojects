# SPEC — Uptime Monitoring Service

Source: https://codingchallenges.fyi/challenges/challenge-uptime-monitoring
(read 2026-10-25; page live, not a 404. Challenge text is brief and
step-based; there is no API contract, wire format, or reference
implementation to conform to, so this spec pins the local CLI behaviour.)

## What it does

A command-line uptime monitor (Python 3 standard library only) that:

- Stores monitored URLs ("targets") with a check frequency.
- Checks each target on its interval with HTTP HEAD by default
  (Step 2), or HTTP GET when configured (Step 4).
- Records every check: timestamp, HTTP status, up/down, latency,
  and for GET checks time-to-first-byte (TTFB) and total time.
- Reports historical uptime and response-time data over a date
  range, as text/ASCII output (Step 3, Step 5).
- Fires alerts when a target is unresponsive for N consecutive
  attempts (N configurable), or is too slow, via a log sink and/or
  a webhook POST (Step 6). Email is an *alert hook only* (see
  divergences) — no real mail is sent.
- Exports history as JSON or CSV (Step 5 export for a CLI tool).

## Challenge steps — coverage

| Step | Page requirement | Built |
|------|------------------|-------|
| Step 0 | Pick language/project | Python 3 stdlib, single main file |
| Step 1 | Enter URLs + frequency, store in a database | `add` command; targets stored in a JSON store file (flat file — explicitly allowed by the page: "as simple as a flat file") |
| Step 2 | HTTP HEAD at the configured frequency, store result + relevant data | Monitor loop sends HEAD, records status/latency/error per check |
| Step 3 | View historic data: select URLs + date range, graph of uptime and ideally round-trip time | `report` command: date-range filter, uptime %, avg/min/max latency, per-check list, ASCII latency sparkline |
| Step 4 | Optional GET mode storing TTFB + whole-response time | `--method GET` per target; GET checks record `ttfb_ms` and `total_ms` |
| Step 5 | View new data via UI; API or export for a CLI tool | `report` shows TTFB/total for GET checks; `export` writes JSON or CSV |
| Step 6 | Alerts via email or webhook, firing after N unresponsive attempts (N configurable) | `alert_after` per target; alert sinks: log file, webhook POST, email-hook file. One alert per incident (deduped until recovery); recovery notice on return to up |
| Going Further | Signup/auth/payment, text matching, SSL expiry | NOT built (see "Not built") |

## CLI

All commands take `--store PATH` (default `uptime-store.json` in the
current directory) so tests and users never touch a fixed location.

```
python3 uptime_monitor.py add --url URL [--interval SECONDS] [--method HEAD|GET]
    [--slow-threshold-ms MS] [--alert-after N]
    [--alert-log PATH] [--webhook URL] [--email-hook PATH]
python3 uptime_monitor.py list
python3 uptime_monitor.py remove --url URL
python3 uptime_monitor.py check [--url URL]        # one immediate check cycle
python3 uptime_monitor.py run [--cycles N] [--max-seconds S]
    # monitor loop: each target checked when its interval elapses
python3 uptime_monitor.py report [--url URL] [--from ISO] [--to ISO]
python3 uptime_monitor.py export [--url URL] --format json|csv --out PATH
python3 uptime_monitor.py alerts [--url URL]       # recorded alert events
```

Target fields: `url`, `interval_seconds` (default 60, minimum 1),
`method` (`HEAD` default, `GET` optional), `slow_threshold_ms`
(optional; 0/absent = no slow alert), `alert_after` (default 3),
`alert_log`, `webhook`, `email_hook` (any combination; at least
one sink is required only when alerts are expected — a target with
no sinks simply records alerts in the store's alert history).

Check record fields: `url`, `timestamp` (UTC ISO-8601), `status`
(int or null), `ok` (bool: 2xx/3xx with no transport error),
`latency_ms` (total round-trip; for GET also `ttfb_ms`,
`total_ms`), `method`, `error` (string or null).

Alert rules:

- DOWN alert: `alert_after` consecutive failed checks (transport
  error or non-2xx/3xx status). Fires once per incident; while the
  incident continues, no repeat alert is emitted. A RECOVERY alert
  fires on the first successful check after an incident.
- SLOW alert: a successful check whose latency exceeds
  `slow_threshold_ms` fires a SLOW alert (once per check; slow
  checks do not count as failures for the DOWN counter).
- Alert event fields: `url`, `timestamp`, `kind` (`DOWN`, `SLOW`,
  `RECOVERY`), `message`, `consecutive_failures` (DOWN only).

Uptime % in a report = successful checks / total checks in range
× 100 (0 checks → "n/a", never a fabricated 100%).

## Deliberate divergences (honest, not silent)

1. **Flat JSON file instead of SQL/NoSQL.** The page explicitly
   allows a flat file; a single JSON store keeps the tool stdlib-
   only and inspectable. No hosted database.
2. **CLI + text/ASCII graphs instead of a web UI / plotted graphs.**
   The page allows "a simple command line tool, just for your own
   use". `report` prints an ASCII latency sparkline, not a PNG chart.
3. **Email is a hook file, not SMTP delivery.** Step 6 says "via
   email or via a webhook". Real SMTP needs user credentials and a
   server; instead `--email-hook PATH` appends a formatted alert
   message to that file (the exact payload a mailer would send),
   and the webhook sink does a real HTTP POST. No SMTP credentials
   are ever requested or stored.
4. **No multi-user accounts.** The page's "one or more users" is
   read as "one or more URLs" in practice for a local CLI tool;
   there is no signup/login. The "Going Further" SaaS extension
   (signup, auth, payment) is explicitly out of scope.
5. **"Too slow to respond with a full page"** is implemented as
   total latency > `slow_threshold_ms` (GET) / round-trip > threshold
   (HEAD), since a HEAD response has no body to time separately.
6. **Status codes:** 2xx and 3xx count as UP; 4xx/5xx count as DOWN
   (a responding server returning 500 is not "up" for monitoring
   purposes). Redirects are NOT followed for HEAD (a 3xx is UP as
   returned); GET uses urllib's default redirect handling, and the
   recorded status is the final status.

## Not built (scope limits)

- Hosted/cloud monitoring, multi-region checks, public status page
  or dashboard UI, SMS/pager alerts, real SMTP email sending.
- Content/text matching on pages, SSL certificate expiry checks
  (both named only under "Going Further").
- Authentication, multi-user isolation, signup/payment.
- Persistent daemon/service install (systemd etc.); `run` is a
  foreground loop the user starts and stops.
- Probing real public sites in tests: tests use only local fake
  HTTP servers on ephemeral ports.

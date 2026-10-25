# SPEC — Build Your Own Port Scanner

Source page: https://codingchallenges.fyi/challenges/challenge-port-scanner/
Slug used: `challenge-port-scanner` — first guess, no 404, no correction needed.
Page steps implemented: Step 1, Step 2, Step 3, Step 4. Step 5 NOT implemented
(see Divergence below).

## Step 1 — Single-port TCP connect scan
CLI accepts a host and a port, tries a full TCP connection, reports open:

```
% ccscan -host=localhost -port=5000
Scanning host: localhost port: 5000
Port: 5000 is open
```

This tool uses `--host` / `--port` (argparse, `--host=...` form also works)
instead of the page's `-host=` form; output lines match the page.

## Step 2 — Vanilla scan
With no single port, scan ports 1–65535 (default range when `--ports`
is omitted and `--port` is omitted):

```
% ccscan -host=localhost
Scanning host: localhost
Port: 5000 is open
Port: 8080 is open
```

Only open ports are printed by default (closed/filtered are counted
in the summary, not listed, unless `--show-all` is given).

## Step 3 — Speed: timeout + concurrency
`--timeout` (seconds, default 0.5) and `--workers` (default 100) are
command-line options with reasonable defaults, per the page's suggestion.
A few hundred milliseconds to a second is the page's suggested timeout
range; 0.5 s is inside it.

## Step 4 — Sweep scan
`--host` accepts:
- a single host: `localhost`, `127.0.0.1`
- a comma-separated list: `localhost,127.0.0.1`
- a wildcard last octet: `127.0.0.*` (expands to 127.0.0.1–127.0.0.254)
- CIDR notation: `127.0.0.0/30` (expands via `ipaddress`, host addresses
  only — network and broadcast addresses excluded)

A sweep tests the same port(s) across each host and reports open ports
per host.

## Port states (TCP connect scan)
- `open` — TCP connection succeeds.
- `closed` — connection refused (RST, `ECONNREFUSED`).
- `filtered` — connection attempt times out (no response within timeout).
- `error` — anything else that is not a clean open/refused/timeout
  (e.g. DNS failure, unreachable network). DNS failure aborts the scan
  for that host with an error, since no port result is meaningful.

## Port ranges
`--ports` accepts: `80`, `80,443`, `1-1024`, `80,8000-8010`.
Ports are validated to 1–65535 (port 0 is reserved and rejected, per
the page). `--port` (single) and `--ports` are mutually exclusive;
`--port` wins the Step-1 form, `--ports` the range form.

## Divergence — Step 5 (SYN / half-open scan) NOT built
Step 5 needs raw sockets to send SYN packets without completing the
handshake. That requires root/CAP_NET_RAW, is OS-specific, and is
outside a Python-stdlib-only, unprivileged tool. Building it would
also make the tool harder to run safely in tests. The scanner is
therefore a TCP connect (vanilla) scanner only. This is a deliberate,
documented omission, not an oversight: the connect scan covers Steps
1–4, which are the task's required scope (TCP connect scan, ranges,
concurrency, open/closed/filtered reporting).

## Safety
Only scan hosts you own or have explicit permission to scan (page
warning). The test suite scans only loopback addresses and local
test servers on ephemeral ports — never external hosts or networks.

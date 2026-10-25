# port-scanner — Build Your Own Port Scanner

Coding Challenges port scanner, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

TCP connect (vanilla) port scanner: single port, port ranges, full
1–65535 scan, concurrent scanning with a configurable timeout, and
sweep scans across a host list, wildcard, or CIDR range. Reports
`open` / `closed` / `filtered` per port.

⚠️ Only scan hosts you own or have explicit permission to scan.

## Usage

```sh
# Step 1: single port
python3 scanner.py --host localhost --port 5000
# Scanning host: localhost port: 5000
# Port: 5000 is open

# Step 2: vanilla scan (all ports 1-65535, open ports only)
python3 scanner.py --host localhost

# Step 3: range, faster timeout, more workers
python3 scanner.py --host localhost --ports 1-1024 --timeout 0.5 --workers 100

# Step 4: sweep — same port across hosts
python3 scanner.py --host localhost,127.0.0.1 --port 8080
python3 scanner.py --host 127.0.0.* --port 8080
python3 scanner.py --host 127.0.0.0/30 --port 8080

# Also show closed/filtered ports, not just open ones
python3 scanner.py --host localhost --ports 80,443 --show-all
```

`--ports` accepts `80`, `80,443`, `1-1024`, `80,8000-8010`.
Defaults: `--timeout 0.5`, `--workers 100`, ports 1–65535 when
neither `--port` nor `--ports` is given.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests scan only localhost test servers on ephemeral ports — never
external hosts or networks.

## Files

- `scanner.py` — connect scan, range/host parsing, sweep, CLI.
- `docs/SPEC.md` — challenge spec and port-state definitions.
- `docs/DESIGN.md` — design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_scanner.py` — the test suite.

## Divergence

Step 5 of the challenge (SYN / half-open scan) is NOT implemented:
it needs raw sockets and root privileges, outside a stdlib-only,
unprivileged tool. See `docs/SPEC.md`.

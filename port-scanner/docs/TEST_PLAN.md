# TEST_PLAN — Port Scanner

All tests scan ONLY localhost / loopback. Test servers are bound to
`127.0.0.1` on port 0 (ephemeral, OS-assigned) and shut down in
`tearDown`. No external host or network is ever scanned.

## Unit tests (tests/test_scanner.py)
1. `scan_port` open: listening loopback server -> `open`.
2. `scan_port` closed: a port with nothing listening (a just-closed
   ephemeral port) -> `closed`.
3. `scan_port` filtered: `socket.create_connection` monkeypatched to
   raise `TimeoutError` -> `filtered`.
4. `scan_port` error: `socket.create_connection` monkeypatched to
   raise `socket.gaierror` -> `error` (DNS failure, not `filtered`).
   Mocked deliberately: this sandbox's resolver intercepts even
   `.invalid` names and resolves them to the egress proxy, so a live
   DNS failure cannot be produced here.
5. `parse_ports`: single, list, range, mixed, dedup+sort; invalid
   inputs (0, 65536, reversed range, empty, non-numeric) raise
   `ValueError`.
6. `expand_hosts`: single host passthrough; comma list; wildcard
   `127.0.0.*` -> 254 hosts, first `127.0.0.1`, last `127.0.0.254`;
   CIDR `127.0.0.0/30` -> `127.0.0.1`, `127.0.0.2`; oversized CIDR
   (prefix < /24) raises `ValueError`.
7. `scan_host`: two open servers + one closed port in one call ->
   correct per-port states, all ports present in the result dict.

## CLI tests (same file, subprocess-free via main() + capsys-style capture)
8. Single-port CLI: `--host 127.0.0.1 --port <open>` prints
   `Scanning host: 127.0.0.1 port: <port>` and `Port: <port> is open`,
   exit 0.
9. Range CLI: `--host 127.0.0.1 --ports <open>,<closed>` prints only
   the open line by default.
10. `--show-all` CLI: closed line also printed.
11. Sweep CLI: `--host 127.0.0.1,127.0.0.1 --port <open>` prints a
    header per host.
12. Bad args: `--port 0` and `--port 70000` exit non-zero (argparse).

## Command
```sh
cd ~/workspace/somecoolprojects/port-scanner
python3 -m unittest discover -s tests -v
```

Pass criterion: every test passes; no test opens a socket to a
non-loopback address (verified by inspection: live connections are
only to `127.0.0.1` test servers; filtered/DNS-error cases are
monkeypatched and make no connection at all).

# TEST_PLAN — netcat

All tests use localhost sockets on ephemeral ports only
(port 0 → OS-assigned, read back via `getsockname`).
No external hosts are contacted. System `nc` (present at
`/usr/bin/nc` on this machine) is used only for the
interoperability tests; those tests skip cleanly if `nc`
is absent, so the suite passes without it.

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

Environment caveat (2026-10-25): this sandbox blocks UDP
loopback `sendto` with `EPERM`, so the two UDP integration
tests skip there (probe in `tests/test_netcat.py`). They
should be re-run on a host where UDP loopback works.

## Unit tests (no subprocess, in-process where possible)

1. `format_hexdump` — the page's Step 5 example, byte for
   byte: 22-byte "Hello from the client\n" and 25-byte
   "Response from the server\n" chunks, including the
   short-line padding and ASCII columns. Also: empty
   input → no lines; non-printable bytes → `.`; exactly
   16 bytes → one full line, no padding line.
2. Argument parser — `-l -p 8888`; `-l -p -u 8888` (the
   page's Step 2 ordering); `-p8888`; `-lv`; `-z host
   8880-8890` range parsing; `-e /bin/cat`; missing port
   → error; bad range (`8890-8880`, port 0, port 99999)
   → error; unknown flag → error.

## Integration tests (subprocess `netcat.py` + sockets)

3. TCP listen + client (both directions): start
   `netcat.py -l -p <port>` with stdin piped, connect a
   raw socket, send "Hello from the client\n", assert the
   server's stdout contains it, feed "Response from the
   server\n" on the server's stdin, assert the socket
   receives it. Then EOF both sides and assert clean exit.
4. TCP client mode: a raw-socket echo server in the test
   process; run `netcat.py 127.0.0.1 <port>` with piped
   stdin, assert round-trip bytes.
5. UDP listen + client: same round-trip as (3)/(4) over
   UDP, both directions (server replies to the last
   sender, client uses a connected UDP socket).
6. Scan: open a raw listening socket on an ephemeral
   port; run `-z 127.0.0.1 <port>` → success line on
   stderr, exit 0. Run `-z` on a closed port → no success
   line, exit 1; with `-v` a failure line appears.
   Range scan covering the open port plus closed
   neighbours → only the open port announced.
7. Execute: `netcat.py -l -p <port> -e /bin/cat`, connect
   a raw socket, send bytes, assert the identical bytes
   come back (cat echoes through the child process).
   Also `-e` prints its security warning to stderr.
8. Hex dump: TCP listen with `-x`; send the page's
   22-byte message; assert stderr contains
   `Received 22 bytes from the socket` and the exact
   first dump line from the page's example.
9. System `nc` interop (skipped if `nc` missing):
   - `nc` client → our TCP listener: message arrives.
   - Our TCP client → `nc -l` listener: message arrives.
   - Our `-z` scan against an `nc -l` listener: open.
   Each `nc` process is started with `subprocess.Popen`,
   killed by explicit PID (`proc.terminate()`), never
   `pkill`.
10. Errors: no arguments → usage error, exit 2;
    client to a closed port → exit 1; `-p 0` → exit 2.

## Cleanup

Every test that spawns a process terminates it explicitly
and waits for it; no background servers survive the suite
(check with `ps` if a test fails mid-run). `__pycache__`
directories are removed after the final run.

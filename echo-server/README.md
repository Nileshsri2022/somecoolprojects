# Echo Server

An echo server implementing the Echo Protocol (RFC 862), from Coding
Challenge #101 (John Crickett). The server echoes back to the
originating client any data it receives, until the connection is
terminated (TCP) or per datagram (UDP).

Challenge source (read in full before building):
`https://codingchallenges.substack.com/p/coding-challenge-101-echo-server`
— also listed on codingchallenges.fyi under the `beginner` and
`networking` tags. The fyi per-challenge URL was not returned verbatim
by search, so it is not guessed here; see `docs/SPEC.md`.

## Run

```sh
python3 echo_server.py --port 7007          # TCP (default)
python3 echo_server.py --port 7007 --udp    # UDP (also accepts -udp)
```

Defaults: all local interfaces, port 7 (the protocol port; use a high
port without elevated privileges). Python 3 standard library only.

Test manually with `nc localhost 7007` (or `nc -u localhost 7007` for
UDP): whatever you type is echoed back. Ctrl+C shuts the server down
cleanly, closing all connections.

## Files

- `echo_server.py` — the whole server (TCP thread-per-client, UDP loop)
- `docs/SPEC.md` — challenge steps, resolved URL, divergences, scope limits
- `docs/DESIGN.md` — design notes
- `docs/TEST_PLAN.md` — test plan
- `tests/test_echo_server.py` — unittest suite

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Result in this sandbox: **9 tests, 8 passed, 1 skipped, 0 failed.**
The skipped test is the UDP round-trip: UDP loopback is blocked here
(UDP `sendto` on `127.0.0.1` fails with `PermissionError: [Errno 1]
Operation not permitted`, while TCP loopback works). The UDP code is
fully implemented, but UDP is **not** verified end-to-end here — re-run
that test on a normal machine before claiming UDP verified. See
`docs/SPEC.md` for the honest scope limits.

This is a standalone echo server; it is not merged into any netcat or
web-server project.

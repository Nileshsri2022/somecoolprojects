# Build Your Own Socat

A Python 3 standard-library clone of the Unix `socat` tool — a version
of `cat` that works over sockets. It establishes two bidirectional byte
streams and transfers data between them.

Challenge page: https://codingchallenges.fyi/challenges/challenge-socat
(Coding Challenge #79). See `docs/SPEC.md` for the steps, the exact
supported subset, and everything deliberately not built.

## Usage

```
python3 socat.py [-u | -U] [-v] address1 address2
python3 socat.py -h
```

- `-u`: unidirectional, left → right only.
- `-U`: unidirectional, right → left only.
- Default: bidirectional.

## Examples (from the challenge page)

```sh
# Step 1: stdio <-> TCP (hand-craft an HTTP request, read the response)
python3 socat.py - TCP4:eu.httpbin.org:80

# Step 2: stdio -> file
python3 socat.py -u STDIO FILE:test.txt,create

# Step 3: TCP log collector (one handler per connection, append to log)
python3 socat.py -u TCP4-LISTEN:3333,reuseaddr,fork OPEN:./test.log,creat,append

# Step 4: tail a log file into the collector
python3 socat.py -u EXEC:'tail -f test.txt' TCP4:localhost:3333
```

## Supported addresses

| Address | Notes |
|---------|-------|
| `-`, `STDIO`, `STDIN`, `STDOUT` | Standard I/O |
| `FILE:path`, `OPEN:path` | Options: `create`/`creat`, `append`, `trunc`, `excl` |
| `TCP:host:port`, `TCP4:`, `TCP6:` | TCP client |
| `TCP-LISTEN:port`, `TCP4-LISTEN:`, `TCP6-LISTEN:` | Options: `reuseaddr`, `fork`, `bind=addr`, `backlog=n` |
| `UDP:host:port`, `UDP4:`, `UDP6:` | Connected UDP (Going Further extension) |
| `UDP-LISTEN:port` | UDP server; first datagram fixes the peer |
| `EXEC:'command'` | Command run without a shell (no pipes/redirects/globs inside) |

## Scope limits (stated plainly)

This is a documented subset, **not** full socat compatibility. NOT built:
SSL/TLS, proxy CONNECT/SOCKS, UNIX-domain sockets, raw IP sockets,
serial devices, PTYs, and the rest of real socat's option catalogue.
`fork` is implemented with threads, not OS `fork()` — same observable
behaviour for the log-collector use case. Full details in
`docs/SPEC.md`.

## Tests

```
python3 -m unittest discover -s tests -v
```

23 tests, loopback only, ephemeral ports only. One honest sandbox
caveat: a UDP echo round-trip is not asserted in this VM because the
sandbox blocks the UDP reply direction (`PermissionError` on the
returning datagram); the UDP send direction and UDP listen direction
are both tested. See `docs/TEST_PLAN.md`.

## Files

- `socat.py` — the implementation (single file, stdlib only)
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md`
- `tests/test_socat.py`

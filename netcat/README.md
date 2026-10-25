# netcat — Build Your Own Netcat

Coding Challenges, "Build Your Own Netcat"
(https://codingchallenges.fyi/challenges/challenge-netcat/,
slug `challenge-netcat`). Docs first, then code — see `docs/`.

A minimal `nc` clone in one Python 3 stdlib file. It covers
all five steps on the challenge page: TCP listen, UDP listen,
port scan, execute, and hex dump, plus the client mode those
steps imply.

## Usage

```sh
python3 netcat.py -l -p 8888            # TCP listen (Step 1)
python3 netcat.py -l -p 8888 -u         # UDP listen (Step 2)
python3 netcat.py -l -p -u 8888         # same, page's Step 2 ordering
python3 netcat.py -z localhost 8888     # scan one port (Step 3)
python3 netcat.py -z localhost 8880-8890  # scan a range (Step 3)
python3 netcat.py -l -p 8888 -e /bin/cat  # execute (Step 4)
python3 netcat.py -x -l -p 8888         # hex dump (Step 5)
python3 netcat.py [-v] [-u] host port   # client mode
```

In listen/client mode, stdin is sent to the peer and peer
data is written to stdout, in both directions. EOF on stdin
shuts down the TCP write side; EOF from the peer ends the
program. UDP has no EOF on the wire, so a UDP session ends
with Ctrl-C (or by terminating the process).

With `-v`, connection success is announced, e.g.
`Connection to localhost port 8888 [tcp] succeeded!`
With `-z`, only open ports are announced unless `-v` is
also given, in which case failures are reported too.

## Divergences from the page (all documented in docs/)

- Status, verbose, scan, and hex-dump output goes to
  **stderr**, not stdout, so piped data is never mixed
  with status lines. On a terminal both appear together,
  exactly as in the page's examples.
- Hex-dump offsets restart at 0 for each chunk, matching
  the page's Step 5 example (both its chunks start at
  `00000000`).
- `-e` takes a single program path, not a shell command
  line (no shell splitting); it prints a security warning
  to stderr on startup — `-e` is unauthenticated remote
  code execution, so use it only on localhost or a
  trusted network.
- `-z -u` cannot prove a UDP listener exists (no
  handshake); it reports the connect result only. TCP
  scanning is the reliable path and is what the tests cover.
- Listen mode serves one connection per invocation (the
  page's examples show a single session); there is no `-k`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use localhost sockets on ephemeral ports only, never
external hosts, and compare against system `nc` where it is
installed (those tests skip cleanly if it is absent).
Note: in this sandbox UDP loopback `sendto` is blocked
(`EPERM`), so the two UDP integration tests skip there with
that reason; the UDP code path (same pumps, UDP sockets)
is implemented and parser-covered, but its live round-trip
could not be exercised in this environment — it needs a
host where UDP loopback is allowed.

## Files

- `netcat.py` — the whole clone: argument parser, TCP/UDP
  listen and client, scan, execute, hex dump.
- `docs/SPEC.md` — the challenge steps, verbatim scope.
- `docs/DESIGN.md` — assumptions, parser, pumps, dump format.
- `docs/TEST_PLAN.md` — test cases and cleanup rules.
- `tests/test_netcat.py` — the test suite.

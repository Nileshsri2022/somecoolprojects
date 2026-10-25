# SPEC — Build Your Own Netcat

Source: Coding Challenges, "Build Your Own Netcat" (John Crickett).
Page: https://codingchallenges.fyi/challenges/challenge-netcat/
Slug used: `challenge-netcat` — this was the first guess and it
loaded directly (no 404, no correction needed). Page read
2026-10-25. All steps below are taken from that page, not memory.

## Step 0 — Setup

Python 3 standard library only. The program is `netcat.py`
(invoked as `ccnc` on the page; here `python3 netcat.py ...`).
No third-party packages, no external hosts in tests.

## Step 1 — TCP listen mode

```
ccnc -l -p 8888
```

Listens for TCP connections on port 8888 (`-l` = listen,
`-p` = port). Data received from the client is written to
stdout; data typed on stdin is sent back to the client.
Sending EOF (Ctrl-D) from either side ends the connection
and the program exits. Only one connection is served per
invocation (the page's examples show a single session).

## Step 2 — UDP listen mode

```
ccnc -l -p 8888 -u
```

Same as Step 1 over UDP (`-u`). The page prints this example
as `ccnc -l -p -u 8888` (port after the `-u` flag); this
implementation accepts that ordering too, as well as the
conventional `-l -p 8888 -u`. UDP is connectionless, so the
server replies to the address of the last datagram received,
and both directions are supported, as the page requires
("you can send messages from both sides").

Client mode also supports UDP: `ccnc -u host port` connects
a UDP socket to the peer and pumps stdin/stdout the same way.

## Step 3 — Port scan (`-z`)

```
ccnc -z localhost 8888
ccnc -z localhost 8880-8890
```

Attempts to connect without sending data. A single port or a
`lo-hi` range is accepted. Only open ports are announced:

```
Connection to localhost port 8888 [tcp] succeeded!
```

With `-v` (verbose), closed/refused ports are also reported:

```
Connection to localhost port 8889 [tcp] failed: Connection refused
```

Scan messages go to stderr (see DESIGN.md). UDP scanning is
not reliable: UDP has no handshake, so a successful
`connect()` says nothing about a listener. `-z -u` therefore
reports each port as reached via connect only, and this
limitation is documented rather than hidden. Tests cover
TCP scanning only.

## Step 4 — Execute (`-e`)

```
ccnc -l -p 8888 -e /bin/bash
```

Runs the given program and pipes its stdin/stdout to/from
the connected client, so the client effectively talks to the
program (the page's example: `ls` from an `nc` client lists
the server's files).

SECURITY: `-e` is unauthenticated remote code execution for
anyone who can connect. This implementation therefore:
- prints a warning to stderr on startup when `-e` is used,
- is intended for localhost / trusted-network testing only,
- never enables `-e` by default, and merges the child's
  stderr into its stdout so errors are visible to the client
  (no separate channel is invented).
The page asks for `-e` explicitly, so it is implemented, not
omitted; the warning is the mitigation, not a removal.

## Step 5 — Hex dump (`-x`)

```
ccnc -x -l -p 8888
```

When `-x` is given, every chunk sent and received is dumped
in the page's format (16 bytes per line, bytes grouped in
fours, printable ASCII on the right, `.` for non-printable):

```
Received 22 bytes from the socket
00000000  48 65 6C 6C  6F 20 66 72  6F 6D 20 74  68 65 20 63  Hello from the c
00000010  6C 69 65 6E  74 0A                                  lient.
Sent 25 bytes to the socket
00000000  52 65 73 70  6F 6E 73 65  20 66 72 6F  6D 20 74 68  Response from th
00000010  65 20 73 65  72 76 65 72  0A                        e server.
```

Dumps go to stderr, not stdout (divergence, documented in
DESIGN.md), so piped data is not corrupted by the dump.
Offsets restart at 0 for each chunk, matching the page's
example where both the received and the sent chunk start at
`00000000`.

## Client mode (implied by Steps 1, 4, 5)

```
ccnc [-v] [-u] [-x] [-e program] host port
```

Connects to `host:port` (TCP by default, UDP with `-u`),
pumps stdin to the socket and socket data to stdout until
either side closes. With `-v`, a successful connection is
announced on stderr:

```
Connection to localhost port 8888 [tcp] succeeded!
```

## Going Further

The page invites `man nc` extras. None are added: per the
ponytail rule (minimum code, nothing speculative), only the
page's five steps plus the client mode they imply are built.
In particular there is no `-k` (stay listening), no file
transfer flag, and no DNS lookup beyond what `socket` does
for a hostname argument.

## Errors / exit codes

- Usage errors (missing port, bad range, unknown flag):
  message to stderr, exit code 2.
- Connection refused / unreachable host in client or scan
  mode: message to stderr, exit code 1 (scan mode still
  reports every port in the range before exiting 1 if none
  was open, 0 if at least one was open).
- Listen on an already-bound port: message to stderr,
  exit code 1.

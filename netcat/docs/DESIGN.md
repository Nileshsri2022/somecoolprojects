# DESIGN — netcat

## Assumptions (stated before coding, per ponytail rules)

1. Single file, Python 3 stdlib only: `socket`, `threading`,
   `subprocess`, `sys`. No `selectors` complexity — two
   pump threads (stdin→socket, socket→stdout) are simpler
   and correct for a byte stream, and are the same shape
   for TCP, UDP, listen, and client modes.
2. Binary-safe throughout: `sys.stdin.buffer` /
   `sys.stdout.buffer`. No decoding of payload bytes; only
   the hex-dump ASCII column interprets printability
   (0x20–0x7E printable, everything else `.`).
3. One connection per listen invocation. The page never
   asks for repeated accepts, and adding `-k` would be
   speculative scope. Tests spawn a fresh server per case.
4. EOF semantics: stdin EOF shuts down the socket's write
   side (TCP `SHUT_WR`) so the peer sees EOF; socket EOF
   ends the pumps and the program exits 0. For UDP there is
   no EOF on the wire, so the program ends on stdin EOF or
   on Ctrl-C; a UDP server with no peer yet simply waits.
5. Verbose/scan/dump messages go to stderr. Rationale:
   the page shows them on the terminal, and in real use
   stdout is the data channel (piping `ccnc ... > file`
   must not mix status lines into the file). The one
   exception the page itself shows — scan success lines —
   also goes to stderr here, for the same reason; a test
   that checks scan output must therefore read stderr.
   This is the only deliberate output-channel divergence
   from a literal reading of the page, and it is flagged
   in SPEC.md and README.md.

## Argument parsing

`argparse` is deliberately NOT used: it cannot accept the
page's Step 2 ordering `ccnc -l -p -u 8888`, where `-p`
is followed by another flag and the port comes last. A
small hand-rolled parser handles:

- combined short flags: `-lv`, `-lu`, `-vz`, `-lx`
- attached values: `-p8888`, `-e/bin/cat`
- separated values: `-p 8888`, `-e /bin/cat`
- deferred port: `-p` followed by a flag leaves the port
  unset; the next bare numeric positional fills it
  (this is what makes `-l -p -u 8888` work)
- positionals: listen mode takes an optional bare port
  (`ccnc -l 8888`); client mode takes `host port`;
  scan mode takes `host port-or-range`
- `-p` with no port anywhere, or a non-numeric port:
  usage error, exit 2

Ports are validated 1–65535; ranges must satisfy lo <= hi
and both ends in range.

## Data pumps — two buffering traps found by testing

- Stdin is read with raw `os.read(0, ...)` in its pump
  thread, not `sys.stdin.buffer.read`: a daemon thread
  blocked in `BufferedReader.read` holds the reader lock
  at interpreter shutdown and Python aborts with SIGABRT
  ("could not acquire lock ... at interpreter shutdown").
- Child stdout in `-e` mode is read with
  `BufferedReader.read1(...)`, not `.read(...)`: `.read(n)`
  on a pipe waits to fill `n` bytes or reach EOF, so a
  short reply from the child never arrived until the
  child exited. `read1` returns whatever is available.

## Data pumps

- `pump(src, dst, direction)`: read up to 4096 bytes,
  optionally hex-dump (see below), write, flush. On EOF
  or error, stop. The main thread joins the pumps and
  shuts the socket down; daemon threads ensure Ctrl-C /
  EOF cannot hang the process.
- TCP listen: `SO_REUSEADDR`, bind `0.0.0.0`, accept one
  connection. With `-v`, print listening address and the
  peer address on accept.
- TCP client: `create_connection` (handles hostnames and
  IPv4/IPv6 via getaddrinfo) with a 10 s timeout for the
  initial connect only; the socket is then blocking.
- UDP listen: bound datagram socket. The first datagram
  fixes the peer address; stdin bytes are sent to that
  peer, received datagrams go to stdout. Before any
  datagram arrives, stdin data is held (there is nowhere
  to send it) — in practice tests always send first.
- UDP client: `socket.connect()` on a datagram socket so
  `send`/`recv` work and only the peer's datagrams arrive.

## Hex dump

`format_hexdump(data)` returns one line per 16 bytes:
`%08x  ` + hex groups + padding + ASCII column. Hex
groups are 4 bytes joined by a single space, groups
separated by two spaces; a short final line is padded
with spaces so the ASCII column aligns at the same
column as a full line. Offsets restart per chunk (see
SPEC.md Step 5). Dump header lines are exactly
`Received N bytes from the socket` /
`Sent N bytes to the socket`, matching the page.

## Execute (`-e`)

`subprocess.Popen([program], stdin=PIPE, stdout=PIPE,
stderr=STDOUT)`. Two pump threads connect socket↔child
instead of socket↔terminal stdio. The child's stdin is
closed when the socket hits EOF, so programs like `cat`
terminate; the program exits when the child exits or the
socket closes, whichever comes first. No shell is used:
the program string is passed as a single argv[0] (the
page's examples are single binaries such as `/bin/bash`;
a command line with arguments is NOT split — splitting
would be shell-like behaviour the page does not ask for).
Documented in README.md.

## Scan (`-z`)

For each port in order: `create_connection` with a short
(1 s) timeout, close immediately on success. Success is
reported even without `-v` (the page's Step 3 example
shows the success line with no `-v`); failures are
reported only with `-v`. Exit 0 iff at least one port
was open.

## Success criteria (verifiable)

See TEST_PLAN.md. In short: TCP echo both directions,
UDP echo both directions, TCP scan single + range,
`-e /bin/cat` echo via a child process, `-x` dump format
byte-for-byte against the page's example, system-`nc`
interoperability in both directions where `nc` is
installed, and CLI usage/connection errors with the
documented exit codes.

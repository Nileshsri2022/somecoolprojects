# Socat — Design

## Implementation

- Single file: `socat.py`, Python 3 standard library only
  (`socket`, `threading`, `subprocess`, `shlex`, `os`, `sys`, `argparse`-free
  hand-rolled parsing so socat-style `-u` flags and bare addresses parse
  exactly as documented).
- Run as `python3 socat.py …`. The file has a `#!/usr/bin/env python3`
  shebang and is executable.

## Address parsing

An address spec is split on commas that are not inside single/double
quotes. The first token is `TYPE:args`; the remaining tokens are options
(`name` or `name=value`). Unknown options are an error.

- `TCP4:host:port`: split on `:` — exactly host + decimal port.
  `TCP` uses the default address family (name resolution decides);
  `TCP4` forces `AF_INET`, `TCP6` forces `AF_INET6`.
- `TCP4-LISTEN:port` / `TCP4-LISTEN:host:port`: the two-part form sets
  `bind` implicitly; the one-part form uses `bind=` or all interfaces.
- `FILE:path` / `OPEN:path`: the path is everything after the first
  colon, so paths containing `:` still work (options are comma-separated
  and are stripped first, so a comma in a filename is not supported —
  documented limitation, same trade-off as real socat's syntax).
- `EXEC:'cmd'`: surrounding single or double quotes are stripped, then
  `shlex.split`. No shell is used.

## Endpoint abstraction

Every address produces an `Endpoint` with:

- `read(n) -> bytes` — `b""` on EOF.
- `write(data) -> None`
- `shutdown_write()` — best effort: `socket.shutdown(SHUT_WR)` for TCP,
  process-stdin close for EXEC, no-op for files/stdio (you cannot
  half-close a pipe or a file).
- `close()` — idempotent.

Concrete endpoints:

- `StdioEndpoint` — reads with `os.read(0, …)`, writes with `os.write(1, …)`.
  Raw fds (not buffered `sys.stdin`/`sys.stdout`) so binary data and
  half-close/EOF behaviour are exact and tests driving the process
  through pipes see output promptly.
- `FileEndpoint` — one `os.open` fd. Flags: `O_RDWR` normally (so the same
  file can serve either direction), `O_CREAT` for `create`, `O_APPEND`
  for `append`, `O_TRUNC` for `trunc`, `O_EXCL` for `excl`. Missing file
  without `create` is an error at open time. `read` is `os.read`,
  `write` loops on `os.write` (partial writes are retried).
- `TcpConnectEndpoint` — `socket.create_connection((host, port))`, with
  optional `SO_REUSEADDR`-irrelevant client bind via `bind=` (binds the
  local address before connecting).
- `TcpListenEndpoint` — bound socket with `SO_REUSEADDR` when requested.
  `accept_one()` returns a socket endpoint for one connection. The relay
  driver, not the endpoint, owns the accept loop for `fork` mode.
- `UdpConnectEndpoint` — `socket.socket` + `connect()`; `recv`/`send`
  behave like a stream of datagrams (each `read` returns at most one
  datagram, up to 65535 bytes).
- `UdpListenEndpoint` — bound socket; the first `recvfrom` fixes the
  peer address; later sends go to that peer and datagrams from other
  senders are dropped. This mirrors how the Step-3 collector would use
  UDP: one peer at a time.
- `ExecEndpoint` — `subprocess.Popen(argv, stdin=PIPE, stdout=PIPE)`.
  The child's stderr is inherited (so `tail -f` errors are visible).
  `shutdown_write` closes the child's stdin; `close` terminates the
  child if it is still running (after the relay ends, e.g. the TCP side
  closed while `tail -f` would run forever).

## Relay driver

- `relay_one(src, dst)`: loop `data = src.read(65536)`; on `b""` stop;
  `dst.write(data)`; on source EOF call `dst.shutdown_write()`.
- Bidirectional: two daemon threads, one per direction; the main thread
  joins both. Joining both (rather than exiting on the first EOF) is
  what makes the Step-1 pattern work: closing stdin half-closes the TCP
  write side, but the response direction keeps running until the server
  closes.
- Unidirectional (`-u`/`-U`): a single `relay_one` in the main thread.
- `fork` listen mode: the listen socket stays open in the main thread;
  each accepted connection spawns a daemon thread that opens a FRESH
  right-hand endpoint (via a factory closure) and relays. The main thread
  blocks on `accept()` until SIGINT/SIGTERM, which closes the listener
  and exits. The per-connection fresh open is load-bearing for Step 3:
  opening the log file once and sharing one fd across connections would
  interleave writes at a shared offset; `O_APPEND` per connection
  appends atomically per write.
- Non-fork listen mode: accept exactly one connection, relay, exit 0.
- Errors in either direction are reported to stderr and cause exit 1
  (after closing both endpoints). KeyboardInterrupt closes endpoints
  and exits 130.

## Why threads, not fork()

The page says "fork a new instance for every incoming connection". Real
socat uses `fork()`; threads give the same observable behaviour for the
log-collector use case (independent per-connection relay, fresh file
open) without the complexity of reaping children, and they keep the
program a single Python file. The difference is documented in SPEC.md
and is not hidden.

## Limitations carried over from the syntax

- Filenames containing commas cannot be expressed (commas separate
  options). Filenames containing colons can.
- `EXEC` has no shell: no pipes/redirects/globs inside the command.
- UDP relay is datagram-shaped: a `read` returns one datagram, so a
  sender that splits a message across datagrams will relay it as
  separate datagrams, not a merged stream.

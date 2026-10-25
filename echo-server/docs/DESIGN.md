# Echo Server — DESIGN

## Files

```
echo-server/
  echo_server.py   # the whole server (stdlib only)
  README.md
  docs/SPEC.md, docs/DESIGN.md, docs/TEST_PLAN.md
  tests/test_echo_server.py
```

One file is enough: the server is a socket loop plus a per-client thread
plus argument parsing. No helpers are needed.

## Components

### TCP server (`TCPServer` class)

- `socket.socket(AF_INET, SOCK_STREAM)`, `SO_REUSEADDR` set so a quick
  restart after shutdown does not fail with "address already in use".
- `bind((host, port))` with host `""` by default (all local interfaces,
  per Step 2), then `listen()`.
- Accept loop runs in its own thread (so `start()` returns and tests /
  `main()` can drive shutdown). It uses a 0.5 s accept timeout so the
  loop can notice the stop event promptly without signals.
- Each accepted connection spawns a daemon=False handler thread, tracked
  in a set guarded by a lock. Handler loop:
  - `recv(65536)`; empty bytes = client closed -> log
    `Client disconnected`, break.
  - otherwise `sendall(chunk)` — verbatim, binary-safe, no framing.
  - on `OSError`, break (covers reset/aborted clients and sockets closed
    by shutdown).
  - on exit, remove the socket from the tracked set and `close()` it.
- Startup log: `TCP Echo server listening on :<port>`. Accept log:
  `Accepted connection from: <ip>:<port>` (the peer address from
  `accept()`). Disconnect log: `Client disconnected`.

### UDP server (`UDPServer` class)

- `socket.socket(AF_INET, SOCK_DGRAM)`, `SO_REUSEADDR`, `bind((host,
  port))`.
- One loop with a 0.5 s receive timeout so it can notice the stop event:
  `recvfrom(65535)` then `sendto(data, addr)` — the whole datagram,
  unchanged, back to its sender.
- Startup log: `UDP Echo server listening on :<port>`.
- No per-client state: UDP has no connections, so there is nothing to
  track or close per client; closing the one socket is the whole cleanup.

### Shutdown (`stop()`)

Shared shape for both servers:

1. Set the stop event (accept/recv loops exit at their next timeout).
2. Close the listening/bound socket (unblocks a pending accept/recv
   immediately on most platforms; the timeout is the backstop).
3. TCP only: snapshot the tracked client sockets and `shutdown()` +
   `close()` each, which unblocks handlers stuck in `recv`.
4. Join the accept thread and all handler threads (bounded: handler
   threads are unblocked by step 3, so they finish).
5. Print `Server shutting down` (exact wording is ours, not the
   challenge's — the challenge specifies no shutdown line).

Because handlers echo synchronously, there is no queue of unsent echoes
to drain: `sendall` completes before the next `recv`. "In-flight" at
shutdown therefore means at most the one `sendall` in progress, which
either completes or fails when its socket is closed.

### CLI (`main()`)

`argparse` with:

- `--host` (default `""` — all interfaces)
- `--port` / `-p` (default `7`, type int)
- `--udp` / `-udp` (flag; `-udp` matches the challenge's example
  invocation — argparse accepts both spellings for the same option)
- `--tcp` (flag, default mode; accepted so `--tcp` is explicit and so a
  `--udp`/`--tcp` mix resolves to UDP only if `--udp` is given)

`main()` builds the chosen server, installs SIGINT/SIGTERM handlers that
call `stop()`, starts the server, then waits on the stop event until a
signal arrives or the server thread ends. Exit code 0 on clean shutdown.
Invalid ports (argparse type error, or bind failure) exit non-zero with
the error on stderr — no silent fallback to another port.

## Decisions and trade-offs

- **Threads, not asyncio.** The challenge explicitly allows threads or
  async tasks; threads keep the code in plain blocking-socket style and
  make "close the socket to unblock the handler" trivially correct.
- **No `socketserver` framework.** Hand-rolling the accept loop is
  ~40 lines and makes the shutdown path (tracked sockets, stop event)
  explicit instead of fighting `serve_forever`/`shutdown` semantics.
- **Chunk size 65536 (TCP) / 65535 (UDP).** Large enough that ordinary
  messages echo in one chunk; larger payloads still echo correctly
  because the handler loops — tests cover a 1 MiB payload to prove
  chunking does not corrupt or truncate.
- **Timeout-based loops instead of `select`.** A 0.5 s timeout is
  simple, portable, and bounds shutdown latency to ~0.5 s without any
  extra wake-up socket.

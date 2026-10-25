# DESIGN — Realtime Chat Client and Server

## Assumptions (stated before coding, per ponytail rules)

1. Plain TCP + line framing is what the page asks for. No websockets:
   the page says "TCP version" (Step 1, citing RFC 862) and never
   mentions HTTP/WebSocket upgrade, so no handshake/framing code is
   added. A TCP equivalent is not a fallback here — it *is* the spec.
2. Python 3 stdlib only: `socket`, `threading`, `select`, `argparse`,
   `sys`. No third-party packages, no async framework — threads are
   the page's first suggested option ("multithreaded or async").
3. One file, two subcommands (`server`, `client`), plus importable
   classes (`ChatServer`, and a small `TestClient`-free client core)
   so tests can drive a real server in-process on an ephemeral port
   without subprocesses for every case.
4. Tests must not depend on port 7007 being free: the server binds
   port `0` in tests and reports the assigned port via
   `server.port`.
5. The interactive client must work from a terminal *and* from a
   pipe (tests drive it via subprocess stdin), so it uses `select`
   on `sys.stdin` + socket and never assumes a TTY.

## Layout

```
realtime-chat/
  chat.py            # server + client, subcommands; importable
  docs/SPEC.md       # challenge steps + wire protocol + non-goals
  docs/DESIGN.md     # this file
  docs/TEST_PLAN.md  # test cases and how to run them
  tests/test_chat.py # unittest, real server on ephemeral port
  README.md          # usage
```

## Server

- `ChatServer(host, port, echo=False)`:
  - `socketserver`-free, hand-rolled on purpose (minimum code, and
    it keeps the broadcast registry explicit): a listening socket
    with `SO_REUSEADDR`, an accept loop thread, and one daemon
    thread per client.
  - Registry: `dict[socket, name]` guarded by one `threading.Lock`.
    All sends under the lock snapshot the peer list first, then send
    outside per-socket failure handling so one dead peer cannot block
    broadcast to the rest. A failed send removes that peer.
  - Per-client handler: send welcome, read the first line as the
    nickname, register + broadcast the join notice, then loop
    `readline()` broadcasting `Name: body` to all except self
    (or echoing to self in `--echo` mode). On EOF/error, unregister
    and broadcast the leave notice. `finally` always unregisters,
    so a crashed client cannot leak a registry entry.
  - `start()` binds/listens and spawns the accept thread;
    `stop()` closes the listener and all client sockets, then joins
    the accept thread briefly. Daemon client threads mean `stop()`
    never hangs on a blocked reader.
- `main()` argparse: `server` / `client` subcommands; server runs
  until Ctrl-C (`KeyboardInterrupt` → `stop()`).

## Client

- `run_client(host, port, name, stdin, stdout)`:
  - Connects, reads the welcome line, sends the nickname as the
    first line, then loops on `select.select([stdin, socket])`:
    stdin ready → read line; `quit`/`exit` (case-insensitive) or
    EOF → break; otherwise print `Name: text` locally and send
    the raw body. Socket ready → read a line and print it verbatim;
    EOF from the server → break.
  - Local echo is deliberate (see SPEC.md): in chat mode the server
    excludes the sender, so without local echo the user would never
    see their own message — matching the page's Step 4 transcript,
    where each own message appears exactly once.
  - `select` on a socket object works on all platforms here; `select`
    on `sys.stdin` requires a real fd (terminal/pipe), which is all
    this CLI targets. No `curses`, no readline tricks.

## What was deliberately not built

- No length-prefix / JSON framing: line framing is enough for a
  chat transcript and is telnet-testable exactly as Step 1 suggests
  (`telnet localhost 7007`). Binary messages are out of scope.
- No rate limiting, message size cap, or auth: not on the page,
  speculative for a teaching chat server. A pathological client
  sending a never-ending line will block its own handler thread
  only; other clients are unaffected (thread-per-client).
- No separate echo-server file: `--echo` on the same server covers
  Steps 1–2 with ~5 lines, instead of duplicating accept/loop code.

# TEST_PLAN — Realtime Chat Client and Server

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests use a real `ChatServer` bound to `127.0.0.1:0`
(ephemeral port) in a background thread, and real socket clients.
No mocks of the network path, no fixed test ports.

## Cases (tests/test_chat.py)

1. **Echo mode** — server with `echo=True` sends each line back to
   its sender, verbatim, for two lines in a row.
2. **Welcome message** — a newcomer receives `Welcome to the
   chatroom!` as its first line.
3. **Broadcast reaches others, not the sender** — A sends a line;
   B receives `A: ...`; A receives nothing (within a short drain
   window). Then B sends; A receives `B: ...`, B receives nothing.
4. **Three-way broadcast** — a message from A reaches B and C.
5. **Join notice** — when B connects with a nickname, A (already
   connected) receives `B has joined the chatroom.`
6. **Disconnect / leave notice** — closing B delivers
   `B has left the chatroom.` to A, and A and C can still exchange
   messages afterwards; the server's client count drops.
7. **Empty lines ignored** — an empty line from A produces nothing
   at B (no blank broadcast).
8. **CLI client end-to-end (subprocess)** — `chat.py client` against
   a real server: piped stdin `name`, a message, then `exit`;
   the process exits 0 and its output contains the local
   `Name: message` line. (A second scripted client is not needed:
   broadcast is already covered at socket level above.)
9. **Server stop** — after `stop()`, the port refuses new
   connections (or the listener is closed); no thread is left
   accepting.

## Not tested (out of scope, per SPEC.md)

- Private/direct messages, rooms, history, auth: not on the page.
- Telnet interop is manual: `telnet 127.0.0.1 7007`, type a name,
  then messages — covered by the documented line protocol, not
  automated (no telnet client in stdlib test scope).
- Concurrency stress (dozens of clients): thread-per-client plus
  the lock is the page's suggested shape; the 3-client tests above
  exercise the broadcast registry paths. A load test would add
  flakiness, not coverage of the spec.

## Manual smoke test

```sh
# terminal 1
python3 chat.py server
# terminal 2
python3 chat.py client   # name: John
# terminal 3
python3 chat.py client   # name: OtherJohn
# type in either client; the other sees "Name: ..." lines.
# type exit in a client to leave.
```

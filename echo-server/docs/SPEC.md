# Echo Server — SPEC

## Challenge source (resolved, read before writing anything)

- Canonical challenge page read in full:
  `https://codingchallenges.substack.com/p/coding-challenge-101-echo-server`
  ("Coding Challenge #101 - Echo Server", John Crickett, published 2025-11-01).
- The codingchallenges.fyi site lists the same challenge ("Build Your Own Echo
  Server") on its `beginner` and `networking` tag pages
  (`https://codingchallenges.fyi/challenges/tags/beginner/`,
  `https://codingchallenges.fyi/challenges/tags/networking/`), and the fyi
  pages mirror the Substack challenge text. The fyi site's own per-challenge
  URL for Echo Server was not returned verbatim by search, so it is **not**
  guessed here; the Substack URL above is the resolved, read source, and its
  step text matches the fyi tag-page summary (RFC 862 echo, TCP + UDP).
- Protocol reference cited by the challenge: RFC 862 (Echo Protocol).

## What the challenge asks for

An echo server implementing the Echo Protocol (RFC 862): the server echoes
back to the originating client any data it receives, until the connection
is terminated. It is presented as a debugging/measurement tool and a first
network server, teaching the sockets API, TCP and UDP, and how Internet
standards are defined.

### Steps, as written on the page

1. **Setup.** Pick a language, set up the project, read RFC 862, and have
   `netcat` or `telnet` available for manual testing.
2. **Single TCP connection.** Build a server that starts up, binds to all
   local IP addresses, listens on port 7, accepts a TCP connection, prints a
   log message showing the connection was accepted, then shuts down.
   Example server output:
   ```
   Accepted connection from: 127.0.0.1:63798
   ```
3. **Multiple concurrent connections.** Keep the main thread listening for
   incoming connections and spawn a new thread (or async task — the page
   puts "thread" in quotes and explicitly allows either) per client. The
   server stays running after accepting connections, e.g.:
   ```
   Accepted connection from: 127.0.0.1:63243
   Accepted connection from: 127.0.0.1:63245
   ```
4. **Echo.** Read data from the client and write that same data back, and
   keep doing so until the client terminates the connection. Server logs
   `Client disconnected` when a client goes away. Client example (`nc`):
   ```
   Hello, Coding Challenges
   Hello, Coding Challenges
   ```
5. **UDP mode.** Add a command-line flag so the server can be started using
   either TCP or UDP on port 7. Example:
   ```
   % ccecho -udp
   UDP Echo server listening on :7
   ```
   and `nc -u localhost 7` echoes datagrams back the same way.
6. **Clean shutdown.** On shutdown, ensure all connections are closed and
   any in-flight echo messages are sent before shutdown.

### Suggested follow-ups (not part of this build)

The page suggests, after the echo server, building a web server, Redis,
Memcached, or a load balancer. Those are separate challenges and are
**not** built here.

## This implementation

- Language: Python 3, standard library only.
- Main file: `echo_server.py` (single file, no helpers needed).
- Run: `python3 echo_server.py [--host HOST] [--port PORT] [--udp]`
  - Default host: all local interfaces (empty bind address), as Step 2 asks.
  - Default port: 7, as the challenge specifies. Ports below 1024 need
    elevated privileges on most systems, so for ordinary use and for all
    tests an explicit `--port` above 1024 (or an ephemeral port) is used.
  - Default mode is TCP. `--udp` (also accepted as `-udp`, matching the
    challenge's `ccecho -udp` example) selects UDP mode.
  - TCP server prints `TCP Echo server listening on :<port>` on startup
    (the challenge only shows the UDP form of this line; the TCP form is
    the obvious analogue and is documented here as an addition, not as
    challenge text).
  - UDP server prints `UDP Echo server listening on :<port>`, matching the
    challenge example exactly when the host is the default.
  - TCP accept prints `Accepted connection from: <ip>:<port>` and client
    disconnect prints `Client disconnected`, matching the challenge.
- Echo semantics: raw bytes, verbatim, no framing, no line handling, no
  transformation. TCP echoes each `recv` chunk back with `sendall` until
  the client closes (empty read) or errors. UDP echoes each received
  datagram back to its sender address, unchanged. This is RFC 862: any
  data received is sent back.
- Concurrency: TCP uses one thread per client connection (the page's
  first option), with the main thread accepting. UDP is a single loop
  (datagrams are independent; no per-client state exists), which is the
  standard shape for a UDP echo server.
- Clean shutdown: SIGINT (Ctrl+C) or SIGTERM stops accepting, closes the
  listening socket, closes all tracked client sockets, and waits for
  handler threads to finish before exiting. Because TCP handlers echo
  synchronously with `sendall`, there is no outbound queue: a message is
  fully sent before the next read, so no buffered echo is lost at
  shutdown. Data arriving after shutdown has begun is not echoed — that
  is the honest limit of "in-flight" here (see Divergences).

## Deliberate divergences

1. **Default port kept at 7, but tests/manual use use high ports.** The
   challenge's port 7 requires privileges; nothing else about the
   behaviour changes with the port number. Tests bind ephemeral ports.
2. **Step 2's "shutdown after one connection" is superseded, not built
   as a mode.** Step 2 is a stepping stone; the final server (Steps 3–6)
   stays running and handles many connections. There is no
   `--one-connection` mode, because the finished challenge does not ask
   for one.
3. **Shutdown closes idle client sockets rather than waiting for them.**
   A handler blocked in `recv` on an idle client cannot otherwise exit.
   Closing the socket unblocks it; the handler then exits. This is the
   only way to honour "all connections are closed" without hanging.
4. **No `telnet`/`netcat` client is shipped.** The challenge uses them
   only as manual test tools, not as deliverables. Tests use Python
   sockets instead.

## Scope limits / NOT built

- **No UDP round-trip test passes in this sandbox.** UDP loopback is
  blocked here: a plain Python UDP server binds on `127.0.0.1` fine,
  but a UDP `sendto` to it fails with `PermissionError: [Errno 1]
  Operation not permitted`, while the equivalent TCP loopback probe
  succeeds. The UDP server code is fully implemented (same file,
  `--udp` flag, datagram echo), and the UDP test attempts a real
  round-trip and **skips itself** with that reason when the sandbox
  blocks the send — it does not fake a UDP round-trip. On a normal
  machine the UDP test should run and pass; re-run it there before
  claiming UDP verified end-to-end.
- No TLS, no authentication, no rate limiting, no logging to file, no
  daemon mode, no IPv6-specific handling beyond what the OS socket
  defaults provide (binding the empty host binds per the platform's
  default address family; tests use IPv4 loopback explicitly).
- No chat, broadcast, or multi-client messaging: this is an echo server
  only, and is deliberately **not** merged into any netcat or web-server
  project, even though the scopes overlap.
- The "try next" challenges (web server, Redis, Memcached, load
  balancer) are not built here.

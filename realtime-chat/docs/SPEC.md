# SPEC — Realtime Chat Client and Server

Source: https://codingchallenges.fyi/challenges/challenge-realtime-chat/
(slug: `challenge-realtime-chat`, fetched 2026-10-25; no 404, no slug correction needed.
The page is Coding Challenge #24 in its Substack numbering.)

## Challenge steps (as specified on the page)

- **Step 0** — Set up environment / language of choice. Here: Python 3
  standard library only.
- **Step 1 — Echo server.** A TCP server listening on port 7007 that
  sends every received message back to the same client. Single client
  at a time is enough for this step. (RFC 862 TCP echo, port 7
  substituted with 7007 to avoid privileged ports.)
- **Step 2 — Simple network client.** Prompts for input, sends a line,
  prints the response. Terminates when `quit` or `exit` is entered.
- **Step 3 — Chat client.** Asks for the user's name on startup, sends
  messages prefixed with that name, and waits on user input *and*
  network messages at the same time (the page suggests `select`).
  The page's transcript shows the client's own message twice against
  the echo server (local echo + server echo).
- **Step 4 — Chat server.** Multiple concurrent clients (multithreaded
  or async). Every message from one client is broadcast to **all other
  clients, except the sender**. On connect the page's transcript shows
  `Welcome to the chatroom!`.

## What this build implements

- `chat.py server [--host HOST] [--port PORT] [--echo]`
  - Default host `127.0.0.1`, default port `7007` (the page's port).
    Tests bind port `0` (ephemeral) instead.
  - Chat mode (default): multi-client broadcast, except sender.
  - `--echo` mode: Step 1/2 behaviour — each line is sent back only
    to its sender. Single-client-at-a-time is *not* enforced; echo
    mode still accepts concurrent clients, which is a superset of
    Step 1 and simpler than a separate server.
- `chat.py client [--host HOST] [--port PORT] [--name NAME]`
  - Without `--name`, prompts `name: ` on stdin.
  - Sends each input line, prints its own message locally as
    `Name: text` (so it appears once in chat mode, where the server
    does not echo to the sender), prints lines received from the
    server as they arrive (via `select` on stdin + socket).
  - `quit` / `exit` (exact line, case-insensitive) or EOF ends it.

## Wire protocol (line-based, UTF-8, `\n`-terminated)

This is the one place the build makes a documented choice the page
leaves open: the page never specifies a wire format.

1. On connect the server sends: `Welcome to the chatroom!`
2. The client's **first line is its nickname** (bare, e.g. `John`).
   Empty nicknames are replaced with `Anonymous`.
3. Every later line is a message body. The server broadcasts it to
   every *other* connected client as: `Name: body`
4. Join/leave notices (small extension beyond the page, needed for
   the "join/leave" requirement): on nickname receipt the server
   broadcasts `Name has joined the chatroom.` to the other clients;
   on disconnect it broadcasts `Name has left the chatroom.`
5. Empty lines are ignored (not broadcast). Lines are stripped of
   trailing `\r\n` only; other whitespace is preserved.
6. Disconnect is a clean socket close / EOF; there is no logout
   command on the wire. The interactive client's `quit`/`exit`
   just closes its connection.

Why server-side prefixing instead of the page's Step 3 wording
("send messages prefixed with the users name")? Receivers see
exactly the same `Name: body` lines, but the server owns the name:
sender exclusion, join/leave notices, and no mid-session
impersonation by a client sending a forged prefix. The Step 3
client behaviour (prompt for a name, show `Name: text` locally)
is preserved.

## Explicitly NOT in the page — and not built

- **No private / direct messages.** The page specifies broadcast-only;
  no `/msg`, `/whisper`, or DM command exists. Tests do not cover DMs.
- **No websockets, rooms/channels, history, or authentication.**
  The page specifies plain TCP sockets; none of these are added.
- **No nickname uniqueness enforcement.** The page never requires it;
  two clients may share a name. No error or rename is invented.
- **No message persistence.** Undelivered messages are lost on
  disconnect/restart, as on the page.

## Success criteria

- Echo mode returns each line to its sender.
- Two (or more) clients on one server: a message from A reaches B
  but not A, prefixed `A: ...`; a message from B reaches A but not B.
- A newcomer receives `Welcome to the chatroom!`.
- After a client disconnects, the remaining clients keep chatting
  and the server stays up.
- The interactive client quits on `quit` / `exit` and handles
  server messages arriving while the user is typing (select loop).

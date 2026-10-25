# realtime-chat — Build Your Own Realtime Chat Client and Server

Coding Challenges #24 (page slug `challenge-realtime-chat`), worked
in `somecoolprojects/`. Docs first, then code — see `docs/`.

A multi-client chat server and client in one Python 3 stdlib file.
The server broadcasts each message to every other connected client;
the client asks for a name, shows its own messages locally, and
prints other clients' messages as they arrive (via `select`).

## Usage

```sh
# terminal 1 — server (default 127.0.0.1:7007, the page's port)
python3 chat.py server

# terminal 2 and 3 — clients
python3 chat.py client
python3 chat.py client --name OtherJohn

# Step 1/2 echo behaviour instead of chat:
python3 chat.py server --echo
```

In a client, type messages and press Enter; type `quit` or `exit`
(or Ctrl-D) to leave. The first line a client sends is its nickname;
the server replies `Welcome to the chatroom!` and broadcasts
`Name has joined the chatroom.` / `Name has left the chatroom.`
to the other clients. Messages arrive as `Name: message`.

Wire protocol, design choices, and what the page does *not* ask for
(no private messages, no websockets, no rooms/history/auth) are
documented in `docs/SPEC.md` and `docs/DESIGN.md`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests spin up a real server on an ephemeral port and exercise
connect/welcome, broadcast (to others, never the sender),
join/leave, disconnect-then-keep-chatting, empty lines, echo mode,
and the CLI client end to end via subprocess.

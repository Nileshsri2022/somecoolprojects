# video-chat — SPEC

Coding Challenges: Build Your Own Video Chat Application
(https://codingchallenges.fyi/challenges/challenge-video-chat/)
— page slug used: `challenge-video-chat`. No correction needed;
the first-guess slug resolved on the first fetch.

## What it is

A WebRTC-style **signalling server** plus a local test-harness
client, in Python 3 standard library only. Two peers find each
other in a named room and relay the messages WebRTC needs to
establish a peer connection — `offer`, `answer`, and ICE
`candidate` — plus a `chat` message (the page's own Step 3
fallback: prove the connection with text) and `bye`.

Actual audio/video transport is NOT built: no WebRTC media, no
codecs, no camera/microphone capture, no STUN/TURN server, no
browser client. See "Out of scope" below and README.md. Nothing
here pretends to carry audio or video.

## Challenge steps (from the page)

- **Step 0 — setup:** Python 3 stdlib only, one main file
  (`video_chat.py`), tests in `tests/`. No dependencies to install.
- **Step 1 — signalling server:** "a way for two users to find
  each other", normally a regular HTTP-based Web API. Built as
  exactly that: a JSON-over-HTTP API (see "API" below).
- **Step 2 — capture audio/video locally:** NOT built. Requires
  camera/mic capture and a browser or native media stack, which
  the Python-stdlib format cannot honestly provide. Recorded as
  out of scope, not faked with placeholder frames.
- **Step 3 — peer-to-peer connection:** the WebRTC half (ICE,
  STUN, TURN) is NOT built — it needs a real WebRTC stack. What
  IS built is the page's own fallback for a from-scratch
  solution: a working signalling-mediated exchange, proven end
  to end with `chat` messages relayed between two peers through
  the server. The offer/answer/candidate payloads themselves are
  relayed opaquely, exactly as a signalling server must, so a
  real WebRTC client could use this server unchanged for Step 1.
- **Step 4 — play remote audio/video:** NOT built, for the same
  reason as Step 2. No fake video is rendered.

## API

Base: `http://HOST:PORT`. All bodies and responses are JSON.
All endpoints return `{"error": ...}` with an HTTP error status
on failure, never an HTML error page.

- `GET /` — health/help: `{"service": "video-chat-signalling",
  "version": 1, "rooms": N}`.
- `GET /rooms` — `{"rooms": ["room-a", ...]}` (sorted).
- `POST /rooms` — join/create a room.
  Request: `{"room": "room-a", "user": "alice"}`.
  Response: `{"room": "room-a", "user": "alice",
  "peers": ["bob"]}` — the other current members, sorted.
  Joining an existing room is idempotent for the same user
  (re-join returns the current peer list, no duplicate member,
  no duplicate `peer-joined` notification).
  Joining broadcasts a `peer-joined` message to existing members.
- `POST /rooms/{room}/leave` — leave a room.
  Request: `{"user": "alice"}`.
  Response: `{"room": ..., "user": ..., "left": true}`.
  Leaving broadcasts `peer-left` to remaining members. An empty
  room is deleted. Leaving a room you are not in is a 404.
- `POST /rooms/{room}/messages` — send one signalling message.
  Request: `{"from": "alice", "to": "bob", "type": "offer",
  "payload": {...}}`. `to` may be omitted/`null` for a broadcast
  to all other members. `payload` may be any JSON value (an SDP
  blob, an ICE candidate, a chat string); the server never
  interprets it, it only relays it.
  Response: `{"seq": N}` — the room-wide sequence number.
- `GET /rooms/{room}/messages?user=alice&since=0` — poll for
  messages. Returns `{"room": ..., "user": ..., "since": S,
  "messages": [...]}` where each message is `{"seq": N,
  "from": ..., "to": ...|null, "type": ..., "payload": ...}`.
  Only messages with `seq > since` are returned, only those
  addressed to `user` or broadcast by someone else. Polling is
  non-destructive and idempotent: the same `since` returns the
  same messages, so a client can re-poll after a failure without
  losing or duplicating anything. `since` defaults to 0.

## Message types

Client-sent: `offer`, `answer`, `candidate`, `chat`, `bye`.
Server-generated: `peer-joined`, `peer-left` (payload
`{"user": ...}`). Any other `type` is rejected with 400.

## Names and limits

- Room and user names: 1–64 chars, `[A-Za-z0-9_-]` only.
  Anything else is a 400.
- Request bodies must be JSON objects, at most 64 KiB.
  Malformed JSON, a non-object body, or an oversized body is
  a 400. Unknown fields are ignored.
- `from` must be a current member of the room, else 403.
  `to`, when given, must be a current member, else 404.
  Sending to an unknown room, or polling/leaving an unknown
  room, is a 404. Polling as a non-member is a 403.
- Rooms, members and messages live in memory only. Restarting
  the server loses all state. There is no authentication, no
  encryption, and no persistence — this is a local signalling
  harness, not a production service.

## CLI

- `python3 video_chat.py serve [--host HOST] [--port PORT]`
  — start the server. Port 0 picks an ephemeral port and the
  chosen port is printed on startup.
- `python3 video_chat.py demo [--host HOST] [--port PORT]`
  — start an ephemeral server in-process and run a scripted
  two-peer call through it (join, offer, answer, candidates
  both ways, chat both ways, bye, leave), printing each step
  and its verification. Exits non-zero if any step fails.
- `python3 video_chat.py --help` — usage.

## Out of scope (deliberate)

No WebRTC media, codecs, or peer-connection code; no camera or
microphone capture; no STUN/TURN/ICE connectivity checks; no
browser/HTML client; no auth, TLS, persistence, or multi-server
operation; no media relay (the server relays signalling only,
never audio/video — by design, as in WebRTC). Each of these
would need a real media stack or a browser, which is outside
the stdlib-only format; they are documented here rather than
simulated.

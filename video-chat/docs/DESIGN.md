# video-chat — DESIGN

## Assumptions (stated before coding)

1. The challenge page specifies *what* the signalling step must
   do ("allow the client applications to relay the necessary
   information to find and establish a peer connection") but not
   a wire protocol, so the protocol below is our own minimal
   choice, documented in SPEC.md — not something the page
   dictates.
2. The intended stack for this repo (Python 3 stdlib only, one
   main file) cannot run WebRTC media. The honest build is
   therefore the signalling server (Step 1) done completely,
   plus the page's Step 3 text fallback as the end-to-end
   proof. Media steps are declared out of scope, not stubbed
   with fake frames that would mislead a reader into thinking
   a call works.
3. Clients poll rather than holding a WebSocket open: the
   stdlib has no WebSocket server, and hand-rolling one would
   be speculative complexity for a signalling harness. Polling
   with a `since` cursor gives the same observable behaviour
   (ordered, lossless, idempotent delivery) with plain HTTP.
4. Rooms are identified by client-chosen names, not server
   IDs: that matches "a simple server at a well known address"
   and lets two test clients agree on a room out of band.

## Architecture

One file, `video_chat.py`, three layers:

- **Store** (`SignallingStore`): plain dicts under one
  `threading.Lock`. A room is `{"members": set,
  "messages": [...]}`; each message is a dict with a room-wide
  monotonically increasing `seq`. All validation of names,
  membership and recipients happens here and raises `ApiError`
  (status + message), so the HTTP layer never embeds policy.
- **HTTP layer** (`SignallingHandler`, `ThreadingHTTPServer`):
  translates requests to store calls. Only routing, JSON
  parsing, the 64 KiB body cap, and error mapping live here.
  `log_message` is silenced so test/demo output stays clean.
  `GET /rooms/{room}/messages` is a plain GET with query
  params — no body needed, so `urllib` and `curl` both work.
- **Client** (`Client`): thin `urllib` wrapper — `join`,
  `leave`, `send`, `poll`, `list_rooms` — raising `ClientError`
  on any non-2xx response. The demo and the tests both use
  this client, so the CLI exercises the same code paths the
  tests verify.
- **Demo** (`run_demo`): spins up a server on port 0 in a
  background thread, runs two clients through the full call
  flow, and asserts each delivery. It is a scripted scenario,
  not a media call — its output says so.

## Why polling + sequence numbers

A signalling relay must not lose or reorder messages: an
`answer` delivered before its `offer`, or a dropped ICE
candidate, breaks call setup. One `seq` per room gives a total
order; the client's `since` cursor makes delivery resumable
and re-polling safe. Broadcasts exclude the sender (a peer
never needs its own message echoed back), and directed
messages go only to their recipient — the server never leaks
one call's signalling into another room, since messages are
stored per room.

## Concurrency and failure behaviour

`ThreadingHTTPServer` serves concurrent clients; the single
store lock makes join/send/poll atomic, so two simultaneous
joins cannot create duplicate members or duplicate seqs.
Malformed input fails with a JSON error and a 4xx status and
leaves no partial state (validation precedes mutation). The
server binds `SO_REUSEADDR` via `allow_reuse_address` so a
restarted demo/test server rebinds promptly. State is
in-memory: a restart is a clean slate, which the tests rely
on (each test class gets a fresh server).

## Alternatives considered and rejected

- WebSocket signalling: no stdlib server; would add a
  hand-rolled protocol for no observable benefit here.
- UDP/TCP custom protocol: harder to inspect with curl and
  further from the page's "regular HTTP-based Web APIs".
- Storing SDP/ICE as typed objects: the server must not
  interpret payloads — opaque relay keeps it usable by any
  real WebRTC client and keeps validation to one allow-list
  of message types.
- A fake "video frame" generator: rejected as dishonest —
  it would demonstrate nothing about video chat.

# video-chat — Build Your Own Video Chat Application

Coding Challenges: Build Your Own Video Chat Application
(https://codingchallenges.fyi/challenges/challenge-video-chat/,
slug `challenge-video-chat`), worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

## What this is — and is not

This is a **WebRTC-style signalling server** plus a local
test-harness client, in Python 3 standard library only. Two
peers join a named room and relay `offer`, `answer`, and ICE
`candidate` messages — the exact information WebRTC needs to
establish a peer connection — plus `chat` messages and `bye`.

**It is not a working video call.** Actual audio/video
transport (WebRTC media, codecs, camera/microphone capture,
STUN/TURN) is not built: the stdlib-only format has no media
stack, and faking it with placeholder frames would be
dishonest. The page's Step 3 fallback — prove the connection
with text — is what the end-to-end demo exercises. A real
WebRTC client could use this server unchanged for signalling.

## Usage

Start the server:

```sh
python3 video_chat.py serve --port 8000
```

Run the scripted two-peer call against an ephemeral server
(join, offer, answer, candidates both ways, chat both ways,
bye, leave — each step verified):

```sh
python3 video_chat.py demo
```

Or drive it with curl:

```sh
curl -s -X POST localhost:8000/rooms \
  -d '{"room": "room-a", "user": "alice"}'
curl -s -X POST localhost:8000/rooms \
  -d '{"room": "room-a", "user": "bob"}'
curl -s -X POST localhost:8000/rooms/room-a/messages \
  -d '{"from": "alice", "to": "bob", "type": "offer",
       "payload": {"sdp": "v=0...", "type": "offer"}}'
curl -s 'localhost:8000/rooms/room-a/messages?user=bob&since=0'
```

Polling uses a `since` sequence cursor: re-polling with the
same cursor returns the same messages, so nothing is lost on
a retry. Names are 1–64 chars of `[A-Za-z0-9_-]`; bodies are
capped at 64 KiB; state is in-memory only.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start a real server on an ephemeral port and verify the
full call flow, broadcasts, room isolation, polling cursors,
and every error case above, over HTTP.

## Files

- `video_chat.py` — signalling server, client, demo, CLI.
- `docs/SPEC.md` — challenge spec and API.
- `docs/DESIGN.md` — design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_video_chat.py` — the test suite.

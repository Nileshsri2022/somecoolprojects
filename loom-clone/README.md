# Loom Clone — local core

A simplified Loom (screen-recording / video-messaging tool) built to
the Coding Challenges spec: https://codingchallenges.fyi/challenges/challenge-loom

**Read this first — honest scope.** This is a *local core*, not a real
screen recorder. It does NOT capture your screen, webcam, or
microphone, does NOT encode video, and does NOT upload anything to a
cloud. What it does, working and tested:

- Local home page + JSON API (Python 3 standard library only)
- Recordings-folder selection, microphone/camera device selection
  (detected Linux nodes, or names you register explicitly)
- Mic-mute / camera-enable / screen-mode toggles, snapshotted into
  each recording at start time, plus a screen-source label
- Recording sessions: create → start → stop, with wall-clock duration
- Chunked upload of recording bytes to the local server, stored raw
  as `<id>.loomdata` (NOT a playable MP4/WebM — do not rename it)
- Listing (newest first), download, local share links (`/s/<token>`),
  and chunk-range trimming into a new recording
- Full metadata per recording: times, duration, devices, toggles,
  screen source, chunks, bytes, SHA-256, notes, trim provenance

See `docs/SPEC.md` for the step-by-step mapping to the challenge,
every divergence, and everything NOT built. `docs/DESIGN.md` explains
the implementation; `docs/TEST_PLAN.md` maps the tests.

## Run

```
python3 loom_clone.py serve --folder recordings
# open the printed http://127.0.0.1:<port>/ URL
```

## Example API flow (replace PORT)

```
curl -s -X POST localhost:PORT/api/recordings \
  -H 'Content-Type: application/json' -d '{"title":"Demo"}'
# -> {"id": "rec-...", ...}

curl -s -X POST localhost:PORT/api/recordings/<id>/start -d ''
curl -s -X POST localhost:PORT/api/recordings/<id>/chunks \
  -H 'X-Chunk-Index: 0' --data-binary 'hello '
curl -s -X POST localhost:PORT/api/recordings/<id>/chunks \
  -H 'X-Chunk-Index: 1' --data-binary 'world'
curl -s -X POST localhost:PORT/api/recordings/<id>/stop -d ''
curl -s localhost:PORT/api/recordings/<id>/download   # -> hello world
curl -s -X POST localhost:PORT/api/recordings/<id>/share -d ''
# -> {"token": "...", "url_path": "/s/..."}
curl -s -X POST localhost:PORT/api/recordings/<id>/trim \
  -H 'Content-Type: application/json' -d '{"start_chunk":0,"end_chunk":1}'
```

Chunks must arrive in order (0, 1, 2, …); out-of-order chunks get 400.

## CLI

```
python3 loom_clone.py devices --folder recordings
python3 loom_clone.py list --folder recordings
python3 loom_clone.py info <id> --folder recordings
python3 loom_clone.py share <id> --folder recordings
python3 loom_clone.py trim <id> 0 2 --folder recordings
```

## Tests

```
python3 -m unittest discover -s tests -v
```

Stdlib only. Test servers use ephemeral localhost ports and are shut
down by the test teardown. No real capture hardware is required: device
tests register named devices explicitly.

## Layout

```
loom_clone.py            # the whole app: settings, devices, sessions,
                         # chunked upload, trim, shares, server, CLI
tests/test_loom_clone.py # unittest suite
docs/SPEC.md docs/DESIGN.md docs/TEST_PLAN.md
```

## Security note

No authentication; the server binds `127.0.0.1` by default. Anyone who
can reach it can list/download/share recordings. Do not expose it
publicly.

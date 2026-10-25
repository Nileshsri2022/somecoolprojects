# SPEC — Loom Clone (local core)

Source challenge: https://codingchallenges.fyi/challenges/challenge-loom
(read 2026-10-25; page live, Steps 0–6 + "Going Further".)
Implementation: Python 3 standard library only, single main file
`loom_clone.py` + `tests/test_loom_clone.py`. No third-party packages.

## What this is

A simplified Loom: a locally served home page + JSON API for setting up
a recording (folder, microphone, camera, toggles, screen mode), running
a recording session (start/stop), uploading its bytes in ordered chunks
to the local server, and listing / downloading / sharing / trimming
recordings. Run it with:

```
python3 loom_clone.py serve --folder recordings   # prints a local URL
python3 loom_clone.py devices --folder recordings
python3 loom_clone.py list --folder recordings
```

## Challenge steps — status

| Step | Challenge asks | Built here |
|---|---|---|
| Step 0 | Choose platform/language | Done: Python 3 stdlib, local web app (the challenge allows web or desktop). |
| Step 1 | Home page; browse/select a destination folder, selection reflected in UI | Done: `GET /` shows the recordings folder; `--folder` / `set_folder()` selects (and creates) it. No OS folder-picker dialog — a local web page cannot open one without browser APIs; the folder is chosen on the command line. See Divergence 1. |
| Step 2 | Detect available mic/camera devices, list them, let user select | Done, honestly: `detect_devices()` scans `/dev/video*` and `/dev/snd` on Linux and returns an empty list elsewhere/when nothing is present. Users may register a known device name (`register_device`); selection of an unknown device is rejected. Friendly device labels are NOT invented. See Divergence 2. |
| Step 3 | Mute/unmute mic, enable/disable camera, before and during recording | Done as persisted settings + `POST /api/settings/toggle` (`mic`/`camera`/`screen`). Settings snapshot into the recording at start time. Toggling affects metadata only — there is no live audio/video stream to mute. See Divergence 3. |
| Step 4 | Start/stop recording, save to selected folder with name/timestamp | Done: `create/start/stop` lifecycle; each recording is `<id>.loomdata` + `<id>.json` in the folder, id contains a timestamp. Duration is measured wall-clock between start and stop. The saved bytes are the uploaded chunks, not captured media. See Divergence 4. |
| Step 5 | Screen sharing/recording: choose screen/window, screen is main focus, alongside mic/camera | Partially done, honestly: `screen_mode` + `screen_source` (e.g. "Display 1") are stored per recording and shown on the home page, and screen mode can be toggled. NO real screen/window capture, no window picker, no compositing. See Divergence 5. |
| Step 6 | Home page lists previous recordings; click to play back audio+video | Partially done: home page lists all recordings in the folder (newest first) with status/bytes/chunks; each has a detail page and a download of its `.loomdata` bytes. There is NO in-browser playable video/audio player, because the stored format is raw concatenated chunks, not a codec container. "Playback" = download of the stored bytes. See Divergence 6. |

## "Going Further" — status

- Recording preview: NOT built as live video. The home page shows the
  current device/toggle/screen choices (a settings preview only).
- Trimming and editing: BUILT, chunk-range only (`trim_recording`,
  `POST .../trim`). New recording, `trimmed_from` link, `trim_chunks`
  recorded. Time-based trimming is NOT built (no codec timestamps).
- Multiple simultaneous captures / compositing: NOT built. One
  recording carries mic + camera + screen *settings* simultaneously,
  but no streams are captured or composited.
- Recording metadata: BUILT — creation/start/stop times, duration,
  devices, toggles, screen source, chunk count, byte count, SHA-256,
  title, notes, trim provenance.
- Share functionality: BUILT locally — `POST .../share` returns a
  random token and `/s/<token>` view; revoke supported. NOT cloud
  upload, NOT a public URL, NOT export to other formats.
- Keyboard shortcuts: NOT built.

## Data model

Recordings folder contains, per recording `<id>`:
`<id>.loomdata` (raw concatenated chunk bytes), `<id>.json` (metadata),
`<id>.chunks.json` (per-chunk byte sizes, needed for honest trimming).
Plus `settings.json` (folder/device/toggle choices + registered device
names) and `shares.json` (token → recording id).

Chunk upload contract: `POST /api/recordings/<id>/chunks` with
`X-Chunk-Index` header and raw body. Chunks MUST arrive in order
0, 1, 2, …; an out-of-order chunk is rejected with 400, not silently
reordered. Unknown recordings give 404; invalid JSON/toggles give 400.

## Divergences and scope limits (all deliberate, none silent)

1. No OS folder-picker dialog; folder via `--folder` (CLI) and shown
   on the home page. A stdlib server cannot pop a native dialog.
2. No friendly device names, no guaranteed device list: stdlib has no
   portable capture-device enumeration. Linux node paths only; empty
   list when nothing is detected. Registered names are user-supplied.
3. Toggles are metadata, not live stream controls (no stream exists).
4. NO real screen capture, camera capture, microphone capture, or
   video/audio encoding. Nothing here records your screen or webcam.
   "Recording" = session metadata + bytes a client uploads in chunks.
   A real capture client (browser MediaRecorder, ffmpeg, etc.) could
   POST its chunks to this API unchanged — that client is out of scope.
5. NO cloud hosting/storage, accounts, or public share URLs. Sharing
   is a local token on the local server only.
6. NO playable media player, NO MP4/WebM output, NO format export.
   `.loomdata` is not a media container; do not rename it to `.mp4`.
7. NO authentication. Anyone who can reach the local server can list,
   download, and share recordings. Bind is `127.0.0.1` by default;
   do not expose it publicly.
8. Trimming is chunk-range only and requires the chunk-size sidecar;
   a recording whose sidecar is missing cannot be trimmed (refused,
   not guessed).
9. No preview window, no compositing, no keyboard shortcuts (see above).

## Verifying manually

```
python3 loom_clone.py serve --folder /tmp/loom-demo
# open the printed URL, then in another shell:
curl -X POST localhost:PORT/api/recordings -d '{"title":"Demo"}' ...
# (see README for the full curl flow; tests cover the same flow)
```

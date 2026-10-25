# DESIGN — Loom Clone (local core)

## Choice of stack

Python 3 standard library only, one file (`loom_clone.py`), as required
for this wave. `http.server.ThreadingHTTPServer` serves both the HTML
home page and the JSON API, so there is no frontend build step and no
dependency to install. The challenge permits a web app; a local web app
is the only honest stdlib route to a "home page" without a GUI toolkit
or a capture framework.

## Layers (all in `loom_clone.py`)

1. **Settings** (`load/save_settings`, `set_folder`, `toggle`,
   `set_screen_source`): a single `settings.json` in the recordings
   folder. Defaults: no mic/camera selected, mic unmuted, camera on,
   screen mode off. Settings are merged over defaults on load, so a
   hand-edited or older file never crashes the server.
2. **Devices** (`detect_devices`, `register_device`, `list_devices`,
   `select_device`): detection is a filesystem scan (`/dev/video*`,
   `/dev/snd` `pcmC*c` nodes) — the only portable-ish thing stdlib can
   do. Registration is explicit and user-supplied; selection validates
   against the known list, so typos fail loudly instead of recording
   under a phantom device.
3. **Recordings** (`create/start/stop/list/load/save_recording`):
   metadata is one JSON file per recording. `start` snapshots the
   current settings into the recording (so later toggle changes do not
   rewrite history); `stop` requires state `recording` and stamps a
   wall-clock duration. States: `created → recording → completed`.
   Invalid transitions raise `ValueError` (mapped to HTTP 400).
4. **Chunks** (`upload_chunk`, `read_media`): bytes are appended to
   `<id>.loomdata`; the SHA-256 is recomputed over the whole file after
   each chunk (simple and verifiable; files here are small). Per-chunk
   sizes go to `<id>.chunks.json` so trimming can find byte boundaries
   without guessing. Strict in-order chunks: the server keeps no
   reordering buffer, so a broken uploader surfaces immediately.
5. **Trim** (`trim_recording`): slices the stored bytes between chunk
   boundaries into a *new* recording (original untouched), copying the
   device/toggle/screen settings and recording `trimmed_from` +
   `trim_chunks`. Refuses when the size sidecar is incomplete.
6. **Shares** (`create/resolve/revoke_share`): `secrets.token_urlsafe`
   tokens in `shares.json`; `/s/<token>` renders a shared detail page.
   No expiry is implemented (documented limit); revocation deletes
   the token.
7. **Server** (`Handler`, `make_server`): `BaseHTTPRequestHandler`
   subclass, `HTTP/1.1`, explicit `Content-Length` on every response
   (required for keep-alive correctness). Routes are plain prefix
   matches; unknown paths → 404, `KeyError` → 404, `ValueError` →
   400. HTML is escaped with `html.escape` on every interpolated
   value (titles/notes are user input). `log_message` is silenced so
   test output stays readable.
8. **CLI** (`main`): `serve` (ephemeral port when `--port 0`, printed
   on startup), `devices`, `list`, `info`, `share`, `trim`. `serve`
   binds `127.0.0.1` by default.

## Why raw `.loomdata` instead of a fake `.mp4`

Writing uploaded bytes under a video extension would imply a playable
file that no player could open. A distinct extension plus a SPEC that
says "raw bytes, not a codec" keeps the local core honest and lets a
future real capture client (e.g. browser MediaRecorder producing WebM)
reuse the same chunk API — the server does not care what the bytes are,
only that they arrive in order.

## Concurrency / safety notes

- `ThreadingHTTPServer` handles concurrent chunk uploads; chunk
  appends for one recording are not locked, so two simultaneous
  uploaders for the same recording could interleave — documented as
  single-uploader-per-recording in practice; tests upload serially.
- No auth (see SPEC §7). Localhost-only default binding mitigates
  this; do not bind `0.0.0.0` with real recordings in the folder.
- Filenames are server-generated ids, never user input, so no path
  traversal via recording ids (ids are stripped of `/` in routing and
  then looked up as `<id>.json` in the folder).

## What would change for real capture

Replace/augment the chunk producer (not this server): a browser page
using `getDisplayMedia` + `getUserMedia` + `MediaRecorder` posting
chunks, or an ffmpeg process posting its output. The server, metadata,
trim-by-chunk, listing, and share-token design all survive unchanged;
only the media container (then genuinely WebM/MP4) and a real
`<video>` player would be added.

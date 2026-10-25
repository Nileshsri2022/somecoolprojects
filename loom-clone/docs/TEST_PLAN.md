# TEST_PLAN — Loom Clone (local core)

Run: `python3 -m unittest discover -s tests -v` from `loom-clone/`
(or `python3 tests/test_loom_clone.py`). Stdlib only; no network beyond
localhost; test servers bind `127.0.0.1` on an ephemeral port
(`port 0`) and are shut down in `tearDown` (explicit `shutdown()` +
`server_close()`, thread joined — no `pkill`, no stray servers).

## Coverage map

| Area | Tests |
|---|---|
| Folder selection | creates folder, returns absolute path, empty folder rejected |
| Settings defaults + toggles | defaults (mic unmuted, camera on, screen off), mic/camera/screen toggle round-trips, bad toggle rejected, screen source enables screen mode, empty source rejected |
| Devices | detection returns mic/camera lists; register + select; unknown device rejected; bad kind rejected; registration deduplicates |
| Lifecycle | create → list → load; unknown id → KeyError; start/stop + duration ≥ 0; double-start rejected; stop-without-start rejected; stop-after-completed rejected; start snapshots current settings; newest-first listing; `settings.json`/`shares.json` never listed as recordings |
| Chunks | concatenation + byte count + 64-hex SHA-256; out-of-order rejected (gap and repeat); unknown recording rejected; non-bytes rejected |
| Trim | middle chunk range produces exact bytes, `trimmed_from`/`trim_chunks`/completed status; empty, reversed, negative, and over-range trims all rejected |
| Shares | create → resolve → revoke → resolve fails; share of unknown recording rejected; revoke of unknown token rejected |
| HTTP API (live server) | home page contains title + folder line; full flow create → start → 2 chunks → stop → download bytes match → list count → share → shared page; out-of-order chunk → 400; unknown recording/share → 404; trim via API; devices/settings/toggle endpoints |

## Manual checks (not in the suite, done by reading the flow)

- `serve` prints a reachable `http://127.0.0.1:<port>/` URL; Ctrl-C
  stops it cleanly.
- CLI `devices` / `list` / `info` / `share` / `trim` print JSON or a
  `/s/...` path and exit 0 on valid input.

## Explicitly NOT tested (because not built)

Real screen/camera/mic capture, video encoding/decoding, in-browser
playback of media, cloud upload, format export, keyboard shortcuts,
live preview video, multi-user auth. Any test claiming those would be
fake coverage; they are listed as scope limits in SPEC.md instead.

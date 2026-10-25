# Spotify Playlist Backup Service — DESIGN

## Layout

```
spotify-playlist-backup/
  spotify_backup.py   # the whole implementation (stdlib only)
  tests/test_spotify_backup.py
  docs/{SPEC,DESIGN,TEST_PLAN}.md
  README.md
```

One main file by design (Wave convention). No third-party dependency:
`urllib.request` for HTTP, `json`, `csv`, `zipfile`, `argparse`,
`http.server` only in tests.

## Components

- `SpotifyApiError` — HTTP/API failure carrying status + body text.
- `parse_playlist_id(text)` — bare id, `spotify:playlist:<id>`, or
  `https://open.spotify.com/playlist/<id>[?...]` → bare id. Anything else
  raises `ValueError`. Query strings and fragments are stripped.
- `SpotifyClient(api_base, auth_base, client_id, client_secret,
  access_token=None)` — pluggable API client. The base URLs are constructor
  arguments, which is what makes the fake-server tests possible without
  touching the real API. All requests go through `_request()` (GET/POST,
  JSON in/out, `Authorization: Bearer <token>` when a token is set).
  - `get_client_credentials_token()` — POST `/api/token` with
    `grant_type=client_credentials`, HTTP Basic auth
    (`base64(client_id:client_secret)`), form-encoded body. Stores the
    token on the client and returns it.
  - `exchange_code(code, redirect_uri)` — POST `/api/token` with
    `grant_type=authorization_code`; same Basic auth.
  - `build_auth_url(client_id, redirect_uri, scope, state)` — static
    helper, `https://accounts.spotify.com/authorize` (or the configured
    auth base) with `response_type=code`, URL-encoded query.
  - `get_playlist(playlist_id)` — `GET /v1/playlists/{id}`.
  - `get_playlist_tracks(playlist_id)` — `GET
    /v1/playlists/{id}/tracks?limit=100&offset=N`, following `next`
    until exhausted; returns the flat item list.
  - `fetch_playlist(playlist_id)` — metadata + all tracks, normalised by
    `normalize_track_item()` into the backup track record (see SPEC).
  - `get_user_playlists()` — `GET /v1/me/playlists?limit=50&offset=N`,
    following `next`; returns playlist summaries.
  - `create_playlist(user_id, name, description, public)` —
    `POST /v1/users/{user_id}/playlists`; `add_tracks(playlist_id, uris)`
    batches URIs in groups of 100, `POST /v1/playlists/{id}/tracks`.
- Backup store (plain functions, no class needed):
  - `backup_path(backup_dir, playlist_id)` → `<dir>/<id>/`.
  - `next_version(folder)` — reads `manifest.json` (tolerates a missing
    or corrupt manifest by scanning `v*.json`) and returns the next
    version number.
  - `write_backup(backup_dir, backup)` — writes `vNNN.json` (zero-padded
    to 3, grows naturally past 999), rewrites `manifest.json`
    (`{playlist_id, versions: [{version, file, backed_up_at, tracks}]}`)
    and `latest.json` (a copy of the newest backup).
  - `load_backup(backup_dir, playlist_id, version=None)` — latest or a
    numbered version; raises `FileNotFoundError` with a clear message.
  - `list_backups(backup_dir)` — one row per playlist folder with its
    versions, from manifests (falls back to scanning files).
- `diff_backups(old, new)` — compares by track URI (falling back to
  track id, then `artist - name` key); returns
  `{added, removed, unchanged}` track-record lists.
- `export_csv(backup, path)` — columns:
  `position, track_name, artists, album, track_id, uri, duration_ms,
  added_at`. Artists joined with `; `. `export_zip_csv()` writes the
  same CSV into a zip with a `<playlist-id>.csv` entry.
- `restore_plan(backup)` — `{playlist_id, playlist_name, track_count,
  tracks: [{uri, track_name, artists}]}` for offline recreation.
- CLI (`main(argv)`, `argparse` subcommands listed in SPEC/README).
  `--backup-dir` defaults to `./backups`. `--api-base` /
  `--auth-base` default to the real Spotify endpoints. Credential flags
  fall back to the `SPOTIFY_*` env vars; missing credentials for a
  network command produce a plain error message and exit code 2, never
  a traceback dump of secrets. The CLI never prints a token.

## Versioning choice

Sequential `vNNN` files (not timestamps alone) because diffs and exports
need a short, stable, user-sayable version handle, and because two
backups in the same second must not collide. `backed_up_at` is still
recorded inside each file and in the manifest.

## Error handling

- Bad playlist reference → `ValueError`, exit 2.
- Missing credentials → exit 2 with a message naming the env var.
- HTTP error → `SpotifyApiError`, exit 1, message includes status only
  (body truncated, never a token).
- Missing backup/version on disk → `FileNotFoundError`, exit 1.

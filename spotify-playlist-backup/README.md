# Spotify Playlist Backup Service

Back up Spotify playlists to versioned JSON files on disk, export them as
CSV (or zipped CSV), diff two versions, and produce or execute a restore
plan. CLI only, Python 3 standard library only.

Challenge: https://codingchallenges.fyi/challenges/challenge-spotify-backup
(Steps 0–5; see `docs/SPEC.md` for the full step mapping, divergences,
and scope limits.)

## ⚠️ Live use was NOT tested here

No real Spotify account, developer app, or user credentials were created
or used for this build, and no real credential exists in this repo. Live
backup needs **your own** Spotify developer credentials:

1. Create a Spotify account and register an app at
   https://developer.spotify.com (challenge Step Zero).
2. Set the placeholder env names — never hard-code real values:
   ```sh
   export SPOTIFY_CLIENT_ID="your-client-id"
   export SPOTIFY_CLIENT_SECRET="your-client-secret"
   export SPOTIFY_REDIRECT_URI="your-redirect-uri"   # only for user login
   export SPOTIFY_ACCESS_TOKEN="your-user-token"     # only for backup-all / restore
   ```
   Public-playlist backup uses the client-credentials flow
   (`SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`); backing up *all* of a
   user's playlists and restoring require a user token (get the login URL
   with `auth-url`, complete the login in a browser, exchange the code).

All automated tests use a local fake Spotify API server on an ephemeral
port and never contact the real Spotify API.

## Usage

```sh
python3 spotify_backup.py token
python3 spotify_backup.py backup <playlist-id-or-URL-or-URI>
python3 spotify_backup.py backup-all            # needs SPOTIFY_ACCESS_TOKEN
python3 spotify_backup.py list
python3 spotify_backup.py show <playlist-id> [--version N]
python3 spotify_backup.py diff <playlist-id> <old-version> <new-version>
python3 spotify_backup.py export <playlist-id> [--version N] [--zip] [--out FILE]
python3 spotify_backup.py restore-plan <playlist-id> [--format json|csv] [--out FILE]
python3 spotify_backup.py restore <playlist-id> --user-id <id> [--name NAME]
python3 spotify_backup.py auth-url --redirect-uri <uri> [--scope SCOPE]
```

Options: `--backup-dir` (default `./backups`), `--api-base`,
`--auth-base` (defaults: the real Spotify endpoints),
`--client-id`, `--client-secret`, `--access-token` (each falls back to
the matching `SPOTIFY_*` env var). The `token` command never prints the
token value itself, only its type and expiry.

Backups live at `<backup-dir>/<playlist-id>/vNNN.json`, with
`manifest.json` (version list) and `latest.json` (newest backup) beside
them. Each backup records playlist metadata plus, per track: track id,
URI, name, artists, album, duration_ms, added_at, added_by.

## Tests

```sh
python3 -m unittest discover -s tests -v
# 23 tests, all passing (fake local API server, ephemeral port)
```

## What is NOT built

- No web UI (CLI instead — explicitly permitted by the challenge page).
- No other music services (Going Further a).
- Moving a playlist to another service (Going Further b, beyond the
  Spotify `restore` command, which itself is not live-tested).
- No token persistence / refresh-token flow, no rate-limit retry.
- See `docs/SPEC.md` for the complete honest list.

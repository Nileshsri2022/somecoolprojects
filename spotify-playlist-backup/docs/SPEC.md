# Spotify Playlist Backup Service — SPEC

Source challenge: https://codingchallenges.fyi/challenges/challenge-spotify-backup
(Read 2026-10-25; page live, not a 404. Challenge: "Build Your Own Spotify
Playlist Backup Service".)

## What the challenge asks for

- **Step Zero** — Set up the environment; create a Spotify account and register
  an app on the Spotify Developer website to get a client id and secret.
- **Step 1** — Authenticate with the Spotify API. For public playlists, client
  id + secret are enough (client-credentials flow); credentials must be stored
  securely.
- **Step 2** — Download a public playlist via the Spotify Web API playlist
  functionality. Suggested fields: artist, album, track name; anything else
  useful may be added.
- **Step 3** — A UI that takes a playlist id from the user and fetches the
  playlist from Spotify.
- **Step 4** — Export / download the public playlist as a CSV (or zipped CSV
  if it is large).
- **Step 5** — Let a Spotify user log in as themselves and back up ALL of
  their playlists, then download / export all of them, not just public ones.
- **Going Further** — (a) Export playlists from other music services.
  (b) Upload / create the same playlist in Spotify and/or another service,
  to make moving between services easy.

## What this build does

CLI-driven local backup service, Python 3 standard library only
(`spotify_backup.py`):

- `auth-url` — build the user-login (Authorization Code) URL for Step 5.
- `token` — obtain a client-credentials access token (Step 1). It reports
  only the token type and expiry, never the token value itself.
- `backup <playlist>` — fetch one playlist (metadata + all tracks, following
  track pagination) and write a versioned JSON backup under
  `--backup-dir/<playlist-id>/vNNN.json`, updating `manifest.json` and
  `latest.json` in that folder. Accepts a bare id, a Spotify URI
  (`spotify:playlist:<id>`), or a full `open.spotify.com/playlist/<id>` URL.
- `backup-all` — fetch the current user's playlists (paginated
  `GET /v1/me/playlists`) and back up each one (Step 5).
- `list` — list backed-up playlists and their versions from disk.
- `show` — print a backup's track listing.
- `diff <playlist> <v1> <v2>` — added / removed / unchanged tracks between
  two backup versions of the same playlist.
- `export <playlist>` — write a backup as CSV (Step 4); `--zip` writes a
  zipped CSV instead; `--version` picks a version, default latest.
- `restore-plan <playlist>` — write the track list (URIs + names) needed to
  recreate a playlist, as JSON or CSV, from a backup on disk (no API call).
- `restore <playlist> --user-id <id>` — create a new playlist on Spotify
  from a backup and add its tracks in batches of 100 (the API's batch
  limit). Requires a user access token (see below).

Backup record fields per track: track id, URI, track name, artists (list),
album name, duration_ms, added_at, added_by where the API supplies it.
Playlist record: playlist id, name, description, owner id, public flag,
snapshot_id, track count, version, backed_up_at (UTC ISO-8601).

Credentials are placeholder env names ONLY: `SPOTIFY_CLIENT_ID`,
`SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`,
`SPOTIFY_ACCESS_TOKEN` (optional pre-obtained user token, for `backup-all`
and `restore`). They are never written into backup files, never hard-coded,
and never logged. The token endpoint is configurable via
`--api-base` / `--auth-base` so tests (and self-hosted proxies) can point
the client at a fake server; defaults are the real Spotify endpoints
(`https://api.spotify.com`, `https://accounts.spotify.com`).

## Deliberate divergences / scope limits (honest)

1. **CLI instead of a web UI (Step 3).** The challenge page itself says a
   command-line application is acceptable ("you can still build this as a
   command line application if you prefer"), so this is a permitted form,
   not a silent skip. No HTML/JS frontend is built.
2. **No live Spotify test.** Live backup was NOT tested against the real
   Spotify API: no real Spotify account, developer app, or user credentials
   were created or used here, and no real credential exists in this repo.
   Live use needs the user's own Spotify developer credentials
   (see README). All automated tests use a local fake Spotify API server
   on an ephemeral port; the real API is never contacted by tests.
3. **Authorization Code flow is implemented but not live-verified.**
   `auth-url` builds the standard authorize URL and the client can
   exchange a code for tokens (`--code` path in the client library), but
   the redirect/callback round-trip against real Spotify accounts was not
   performed. `backup-all` / `restore` therefore work in tests with a
   supplied user token and are unproven against a live user account.
4. **Going Further (a) NOT built.** No other music service (Apple Music,
   YouTube Music, etc.) is supported; export is Spotify-only.
5. **Going Further (b) only partially built.** `restore-plan` (offline
   listing) and `restore` (create playlist + add tracks via the Spotify
   API, user token required) are implemented, but moving a playlist to
   another service is not, and `restore` itself is not live-tested (see 2).
6. **No token persistence, no refresh-token store.** Tokens live only in
   memory / the invoking process's environment. A refresh-token flow is
   not implemented; re-running `token` / re-supplying
   `SPOTIFY_ACCESS_TOKEN` is the documented path.
7. **No rate-limit retry / backoff beyond surfacing HTTP errors.**
   A 429 / 5xx from the API raises a clear `SpotifyApiError` with status
   and body; automatic retry is not implemented.
8. **Step Zero account/app creation is a user-side action**, not something
   code can do; it is documented in README, not performed here.

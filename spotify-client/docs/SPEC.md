# SPEC — Spotify Client (somecoolprojects entry 19)

Source challenge: "Build Your Own Spotify Client",
https://codingchallenges.fyi/challenges/challenge-spotify
(slug `challenge-spotify` — see the 404 caveat in the README).

The page is frontend-oriented (React + Spotify Web Playback SDK).
This project is the command-line adaptation of the same steps, in
Python 3 standard library only, per the somecoolprojects rules.
No real Spotify credentials are used anywhere in this project.

## Page steps (verbatim intent)

- Step 0 — Set up the language of choice; create a Spotify account
  and register an app on the Spotify Developer dashboard. A client
  id/secret is needed for personal data (profile, playlists).
- Step 1 — Authenticate the user. For a single-page web app the page
  recommends Authorization Code with PKCE. Then call `GET /me` and
  verify the returned `id` field matches the expected user.
- Step 2 — Fetch the authenticated user's playlists (`Get Playlist`
  API) and display each playlist's title and image.
- Step 3 — Let the user select a playlist, then play and pause it
  (page: via the Web Playback SDK, with the right scopes set).
- Step 4 — Get the client `device_id` and use the Player API to
  transfer playback to this client automatically.

## Implemented surface (this CLI)

Auth (accounts base, default `https://accounts.spotify.com`):

- PKCE: random code verifier (43–128 chars, URL-safe), S256
  code challenge = base64url(SHA-256(verifier)), no padding.
- Authorization URL: `GET {accounts}/authorize` with
  `response_type=code`, `client_id`, `redirect_uri`, `scope`,
  `code_challenge`, `code_challenge_method=S256`, optional `state`.
- Token exchange: `POST {accounts}/api/token`, form-encoded:
  - `grant_type=authorization_code` + `code`, `redirect_uri`,
    `code_verifier`, `client_id` (PKCE, no secret — public client).
  - `grant_type=client_credentials` with HTTP Basic
    `base64(client_id:client_secret)` (server-to-server only;
    this flow cannot read a user's private profile/playlists).
  - `grant_type=refresh_token` + `refresh_token`, `client_id`.
- Token response fields kept: `access_token`, `token_type`,
  `expires_in`, `refresh_token`, `scope`. Expiry is computed as
  receipt time + `expires_in` (a small safety margin is subtracted).

Web API (API base, default `https://api.spotify.com/v1`),
all calls send `Authorization: Bearer <token>`:

- `GET /me` — current user profile (`id`, `display_name`, `email`).
- `GET /me/playlists?limit=&offset=` — user's playlists, paginated
  by following the response `next` field until it is null.
- `GET /playlists/{id}/tracks` — playlist tracks, paginated.
- `GET /search?q=&type=&limit=&offset=` — search; `type` is one or
  more of `track`, `artist`, `album`, `playlist` (comma-separated).
- `GET /tracks/{id}`, `GET /artists/{id}`,
  `GET /artists/{id}/top-tracks?market=` — track / artist lookup.
- `GET /me/player/devices` — available devices (`id`, `name`, `type`,
  `is_active`).
- `PUT /me/player` with `{"device_ids": [...], "play": bool}` —
  transfer playback (page Step 4).
- `PUT /me/player/play` with optional `{"device_id": ...}` and
  `PUT /me/player/pause` — play / pause (page Step 3, Player-API
  form; see DESIGN.md for the Web Playback SDK divergence).

## Pagination

Spotify list responses carry `items`, `limit`, `offset`, `total`
and `next` (a full URL, or null on the last page). The client
follows `next` verbatim (it may be a full URL against the
configured API base) and stops when `next` is null, when a page
returns no items, or when `offset + len(items) >= total` if
`total` is present. A caller-supplied `max_items` caps the yield.

## Errors

All API/token failures raise `SpotifyError` carrying the HTTP
status, the Spotify error message when the body is JSON of the
form `{"error": {"status": ..., "message": ...}}`, and the
`Retry-After` value (seconds) for HTTP 429. Non-JSON bodies are
reported by status alone, never by crashing on a decode error.
Client-side validation (empty query, limit outside 1–50 for
search/playlists, unknown search type, empty token) raises
`ValueError` before any network call.

## Scopes used (defaults)

`user-read-private user-read-email playlist-read-private
playlist-read-collaborative user-read-playback-state
user-modify-playback-state`
Playback transfer/play/pause need the `user-modify-playback-state`
scope; reading the profile needs `user-read-private` /
`user-read-email`. The scope string is overridable on the CLI.

## Out of scope (page features not built here)

- Actual audio playback and the Web Playback SDK: a CLI cannot
  host the browser SDK. Play/pause/transfer are done through the
  Player API against a real Spotify app/device instead.
- No browser is launched by the tool itself; `auth-url` prints the
  URL and the user opens it, then pastes back the `code`.
- No token persistence to disk: tokens are printed / passed via
  environment variables only, so no secret is written to a file.

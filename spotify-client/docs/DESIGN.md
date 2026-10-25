# DESIGN — Spotify Client

## Assumptions

1. Python 3.8+ standard library only (`urllib`, `json`, `hashlib`,
   `secrets`, `base64`, `argparse`). No `requests`, no SDK.
2. The tool is a CLI, not a web app. The challenge page's React /
   Web Playback SDK front end is therefore adapted, not copied:
   playback is driven through the Spotify Player API
   (`PUT /me/player`, `/me/player/play`, `/me/player/pause`),
   which is the API the page itself points at in Step 4 and
   works against any Spotify device (phone, desktop app, speaker).
3. Credentials come only from environment variables or CLI flags,
   never from the source:
   - `SPOTIFY_CLIENT_ID` — app client id (placeholder name only;
     no real value is stored, requested, or shipped here).
   - `SPOTIFY_CLIENT_SECRET` — only for the client-credentials
     flow; never used with PKCE.
   - `SPOTIFY_REDIRECT_URI` — default
     `http://127.0.0.1:8888/callback` (loopback, matching the
     usual local-dev redirect for this kind of client).
   - `SPOTIFY_ACCESS_TOKEN` — a user-supplied bearer token for
     direct API commands, so `me` / `playlists` / `search` can
     run without re-doing the auth flow in the same process.
   - `SPOTIFY_ACCOUNTS_BASE` / `SPOTIFY_API_BASE` — overrides
     used by the tests to point at the local fake server; a user
     would never need to set these against real Spotify.
4. The fake server in the tests speaks the same wire shapes as
   Spotify (form-encoded token POST, JSON API responses with
   `items`/`next`/`total`, `{"error": {...}}` bodies), so passing
   tests mean the request construction and response parsing are
   right. They do NOT prove anything against live Spotify —
   that needs the user's own app credentials (see README).
5. One main file, `spotify_client.py`: pure helpers (PKCE,
   URL building, formatting, pagination logic) are kept separate
   from I/O (`urllib` calls) so the pure parts are testable
   without any server at all.

## Structure

- `build_auth_url(client_id, redirect_uri, challenge, scope, state)`
  — pure URL construction, query params URL-encoded.
- `generate_pkce_pair()` — `(verifier, challenge)` via
  `secrets.token_urlsafe(64)` trimmed to the 128-char max, and
  `code_challenge(verifier)` = base64url(SHA-256) without padding.
- `Token` — dataclass-ish plain class: `access_token`,
  `token_type`, `expires_in`, `refresh_token`, `scope`,
  `expires_at` (monotonic-ish wall time + margin). `expired()`
  reports True only when `expires_in` is known and passed.
- `SpotifyError(Exception)` — `status`, `message`, `retry_after`.
- `SpotifyClient(api_base, access_token)` — `_get(path_or_url,
  params)`, `_put(path, body)`, and one method per endpoint.
  `_get` accepts a full `next` URL verbatim, which is what makes
  pagination work against both Spotify and the fake server.
- `iter_pages(client, first_page)` — generator following `next`
  until null / empty / total reached / `max_items` reached.
- `format_track / format_playlist / format_artist / format_device`
  — pure one-line renderers used by the CLI and the tests.
- `main(argv)` — `argparse` subcommands: `auth-url`, `exchange`,
  `refresh`, `token-client-credentials`, `me`, `playlists`,
  `tracks`, `search`, `track`, `artist`, `devices`, `play`,
  `pause`, `transfer`. Every API subcommand accepts
  `--api-base` and `--token` overrides for testing.

## Divergences from the challenge page (deliberate)

1. **CLI instead of React + Web Playback SDK.** The page's Steps
   3–4 are about an in-browser player. A Python CLI cannot embed
   that SDK, so play/pause/transfer go through the Player API.
   The user-visible behaviour (select a playlist/device, play,
   pause, move playback) is preserved; the audio renders on a
   real Spotify device, not in this process.
2. **Extra endpoints beyond the page.** The page only requires
   `/me`, playlists, and playback. `search`, `track`, and
   `artist` are added because a "client" that cannot look up a
   track or artist is barely usable, and because they exercise
   the same request/response machinery with no extra auth model.
   They are clearly marked as additions in SPEC.md / README.md.
3. **No automatic browser launch / local callback server.**
   `auth-url` prints the URL; the user completes login in their
   own browser and pastes the `code` to `exchange`. This avoids
   a background HTTP server, a port conflict, and any token
   being written to disk — at the cost of one manual paste.
   (A callback server would be a small, safe follow-up.)
4. **No token storage.** Tokens live in the process / env only.
   Re-running `exchange` after expiry is the refresh path today
   (`refresh` subcommand covers the refresh-token grant).

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes, with all
  tests against a local fake server on an ephemeral port — zero
  calls to `spotify.com` / `accounts.spotify.com` in tests.
- PKCE challenge matches the RFC 7636 S256 definition for a
  known verifier (test pins an exact vector).
- Playlist pagination returns items from every page of the fake
  server, in order, and stops at the null `next`.
- 401 / 404 / 429 responses surface as `SpotifyError` with the
  right status, message, and (for 429) `retry_after`.
- CLI `auth-url` output contains `code_challenge_method=S256`
  and the given client id / redirect URI, URL-encoded.

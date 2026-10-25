# TEST_PLAN — Spotify Client

Runner (from the project directory):

```sh
python3 -m unittest discover -s tests -v
```

No network beyond localhost. Every HTTP test runs against a
`ThreadingHTTPServer` bound to `127.0.0.1` on port `0`
(ephemeral, OS-chosen) in a background thread, shut down in
`tearDown`. The fake server records requests (method, path,
headers, body) so tests can assert on what the client sent, and
serves canned JSON per route. No test contacts `spotify.com`.

## Pure (no server) cases

- PKCE: known verifier `dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk`
  (RFC 7636 Appendix B) gives challenge
  `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`.
- PKCE pair: verifier length 43–128, URL-safe alphabet only;
  challenge equals `code_challenge(verifier)` recomputed.
- Auth URL: contains `response_type=code`, the client id,
  URL-encoded redirect URI, `code_challenge_method=S256`,
  the scope string, and `state` when given; no `client_secret`
  ever appears in the URL.
- Formatting: `format_track` renders `name — artist (album)`;
  `format_playlist` renders `name (N tracks) — owner`;
  `format_artist` renders `name (genres, followers)`;
  missing optional fields degrade to empty strings, not crashes.
- Validation: empty search query, empty token, limit 0 / 51,
  unknown search type, and empty device list for transfer all
  raise `ValueError` before any request is made.
- Token expiry: a token with `expires_in=3600` is not expired
  at creation; one with `expires_in=0` is expired; a token
  with no `expires_in` is treated as not expired (unknown).

## Fake-server cases

- Token exchange (authorization_code): client POSTs form-encoded
  `grant_type=authorization_code&code=...&redirect_uri=...&
  code_verifier=...&client_id=...` to `/api/token` and parses
  `access_token` / `refresh_token` / `expires_in`.
- Client credentials: client POSTs with `Authorization: Basic
  base64(id:secret)` and `grant_type=client_credentials`.
- Refresh: `grant_type=refresh_token` POST returns a new token.
- Token error: fake returns 400 `{"error": "invalid_grant"}`
  and the client raises `SpotifyError` with status 400.
- `GET /me`: returns `id`/`display_name`/`email`; client
  returns them unchanged; a missing `Authorization: Bearer`
  header makes the fake return 401 (asserted via a direct call
  with an empty token is rejected client-side first, so the
  401 path is tested by pointing the fake at a bad-token route).
- Playlists pagination: fake serves page 1 (`items` A, B,
  `next` = page-2 URL, `total` 3) and page 2 (`items` C,
  `next` null); `get_all_playlists` returns [A, B, C] in order
  and `max_items=2` returns [A, B] after only the first page.
- Playlist tracks pagination: same two-page shape for
  `/playlists/{id}/tracks`.
- Search: `q`/`type`/`limit` arrive URL-encoded on the fake;
  results under `tracks.items` / `artists.items` are returned.
- Track / artist / top-tracks / devices: single-object routes
  parse and return the canned payloads unchanged.
- Play / pause / transfer: fake records the PUT body; play
  sends `device_id` when given, pause sends an empty body, and
  transfer sends `{"device_ids": [...], "play": true}`.
- Errors: 401 with `{"error": {"status": 401, "message":
  "Bad OAuth token"}}` raises `SpotifyError(status=401,
  message="Bad OAuth token")`; 404 likewise; 429 returns
  `Retry-After: 5` and the exception carries `retry_after=5`;
  a 500 with a non-JSON body raises `SpotifyError` with the
  status and no crash on body parsing.

## Not tested (requires live Spotify + user credentials)

- Real authorization-code flow in a browser, real `/me` id
  verification against a real account, real playback on a
  real device, and real rate-limit backoff timing. These are
  documented as manual steps in the README.

# Spotify Playlist Backup Service — TEST_PLAN

Runner: `python3 -m unittest discover -s tests -v` from the project
directory. Python 3 stdlib only; no network beyond localhost.

## Fake Spotify API server (tests only)

`tests/test_spotify_backup.py` starts a `ThreadingHTTPServer` on an
ephemeral port (`port 0`, OS-assigned) in `setUpClass` and shuts it down
in `tearDownClass`. It implements just enough of the Spotify surface:

- `POST /api/token` — client-credentials grant returns a fake token
  (verifies Basic auth is present); authorization_code grant returns a
  fake user token. Any other grant → 400.
- `GET /v1/playlists/<id>` — one fixed playlist (2 tracks' metadata).
- `GET /v1/playlists/<id>/tracks` — paginated: honours `limit`/`offset`,
  returns `next` until the 3-track fixture is exhausted (exercises the
  pagination loop with `limit=2`).
- `GET /v1/me/playlists` — paginated list of 2 playlist summaries.
- `POST /v1/users/<uid>/playlists` — records the body, returns a new
  playlist id. `POST /v1/playlists/<id>/tracks` — records added URIs.
- Unknown playlist id → 404; unknown path → 404.

No test ever contacts `api.spotify.com` or `accounts.spotify.com`.

## Coverage (all in one unittest file, by area)

1. **Playlist-id parsing** — bare id, URI, full URL with query string,
   URL with fragment, garbage input raises `ValueError`.
2. **Client-credentials token** — token returned and stored on the client;
   wrong-grant path not exercised against the fake (it only serves the
   two real grants).
3. **Fetch playlist** — metadata fields, all 3 tracks collected across
   pages, artist/album/name normalisation, missing-track item skipped.
4. **User playlists** — both summaries returned across pagination.
5. **Backup store** — first write is `v001.json`, second is `v002.json`,
   manifest lists both, `latest.json` matches the newest, loading a
   specific version and latest, loading a missing playlist/version
   raises `FileNotFoundError`.
6. **Diff** — added, removed, unchanged computed by URI between two
   backups of the same playlist.
7. **CSV export** — header + rows, multi-artist join, round-trip read;
   zip export contains exactly one CSV with the same content.
8. **Restore** — restore-plan shape from a backup on disk;
   create-playlist + add-tracks against the fake records the right
   name and URIs (batched; 3 tracks = 1 batch).
9. **Auth URL** — contains `response_type=code`, client id, redirect URI,
   and scope.
10. **CLI end-to-end (subprocess-free, via `main()`)** — `backup`,
    `list`, `show`, `diff`, `export` against the fake server into a
    temporary directory; `backup` with a bad id exits non-zero;
    `backup` with no credentials exits non-zero without a traceback
    leaking a token.
11. **API error surfacing** — fetching an unknown playlist raises
    `SpotifyApiError` with status 404.

## Not covered (stated honestly)

- Live Spotify API behaviour (token expiry, real pagination shapes
  beyond the documented contract, real 429 handling).
- The browser redirect round-trip for Authorization Code login.
- CSV content for tracks whose names contain newlines/commas beyond
  what `csv` module quoting already guarantees (covered indirectly by
  the round-trip test).

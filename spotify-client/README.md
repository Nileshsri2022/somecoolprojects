# spotify-client — Build Your Own Spotify Client

Coding Challenges #19, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A Python 3 standard-library-only CLI client for the Spotify Web
API, built from the challenge page
(https://codingchallenges.fyi/challenges/challenge-spotify).
It covers the page's steps — PKCE authentication, `GET /me`,
listing the user's playlists, play/pause, and Player-API
playback transfer — plus search, track, and artist lookup
(additions beyond the page, noted in `docs/DESIGN.md`).

**No real credentials are included, requested, or stored here.**
Credentials are placeholder environment-variable names only
(`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`,
`SPOTIFY_REDIRECT_URI`, `SPOTIFY_ACCESS_TOKEN`). Live API
testing needs the user's own Spotify Developer app credentials;
all automated tests run against a local fake server and make
zero calls to `spotify.com`.

## Usage

```sh
# 1. Print the PKCE authorization URL (and the verifier to keep)
python3 spotify_client.py auth-url

# 2. Open the URL, approve, paste back the code from the redirect
python3 spotify_client.py exchange <code> --verifier <verifier>

# 3. Use the printed access token for API commands
export SPOTIFY_ACCESS_TOKEN=<token from step 2>
python3 spotify_client.py me
python3 spotify_client.py playlists
python3 spotify_client.py tracks <playlist_id>
python3 spotify_client.py search "song name" --type track
python3 spotify_client.py track <track_id>
python3 spotify_client.py artist <artist_id>
python3 spotify_client.py devices
python3 spotify_client.py transfer <device_id>
python3 spotify_client.py play --device-id <device_id>
python3 spotify_client.py pause
```

Server-to-server only (no user-private data):

```sh
python3 spotify_client.py token-client-credentials
```

Tokens are never written to disk by this tool. The page's
Web Playback SDK front end is deliberately not built: this CLI
drives playback through the Player API against a real Spotify
device instead (see `docs/DESIGN.md` for the divergence).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use a small in-process fake Spotify server on an
ephemeral localhost port — no public network, no hard-coded
ports. They cover the RFC 7636 PKCE vector, auth-URL
construction, token exchange / client-credentials / refresh,
`/me`, two-page playlist and playlist-track pagination
(including early stop at `max_items`), search, track/artist/
top-tracks/devices, play/pause/transfer request bodies, and
401 / 404 / 429 (with `Retry-After`) / non-JSON error handling.

## Files

- `spotify_client.py` — PKCE, token grants, API client, pagination,
  formatters, CLI.
- `docs/SPEC.md` — challenge spec and implemented surface.
- `docs/DESIGN.md` — assumptions and deliberate divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_spotify_client.py` — the test suite.

## Page slug / 404 caveat

The slug is `challenge-spotify`, **not** `challenge-spotify-client`:
that longer slug was not the page. The correct page was found
via the site's `tags/api/` index, which links "Build Your Own
Spotify Client" to `/challenges/challenge-spotify`. The sibling
challenge "Spotify Playlist Backup Service" lives at
`challenge-spotify-backup` and is a different project — it was
not built here.

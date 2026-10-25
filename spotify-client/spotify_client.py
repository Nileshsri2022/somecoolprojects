#!/usr/bin/env python3
"""Spotify Client — CLI scaffolding for the Spotify Web API.

Build Your Own Spotify Client (codingchallenges.fyi, slug
``challenge-spotify``), adapted to a Python 3 stdlib-only CLI.

Auth: Authorization Code with PKCE (public client, no secret),
client-credentials (server-to-server), and refresh-token grants.
API: /me, /me/playlists, playlist tracks, search, track, artist,
devices, and Player API play / pause / transfer.

No credentials are stored in this file. Credentials come from
environment variables (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
SPOTIFY_REDIRECT_URI, SPOTIFY_ACCESS_TOKEN) or CLI flags, and
tokens are never written to disk by this tool.

Live Spotify testing needs the user's own app credentials; all
automated tests run against a local fake HTTP server instead.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ACCOUNTS_BASE = "https://accounts.spotify.com"
DEFAULT_API_BASE = "https://api.spotify.com/v1"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_SCOPE = (
    "user-read-private user-read-email playlist-read-private "
    "playlist-read-collaborative user-read-playback-state "
    "user-modify-playback-state"
)
SEARCH_TYPES = ("track", "artist", "album", "playlist")


class SpotifyError(Exception):
    """An error response from Spotify (or the token endpoint)."""

    def __init__(self, status, message="", retry_after=None):
        super().__init__(message or "Spotify error %s" % status)
        self.status = status
        self.message = message
        self.retry_after = retry_after


def code_challenge(verifier):
    """RFC 7636 S256 challenge: base64url(SHA-256(verifier)), no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_pkce_pair():
    """Return (verifier, challenge); verifier is 43-128 URL-safe chars."""
    verifier = secrets.token_urlsafe(64)[:128]
    if len(verifier) < 43:  # pragma: no cover - token_urlsafe(64) is longer
        verifier = verifier + "A" * (43 - len(verifier))
    return verifier, code_challenge(verifier)


def build_auth_url(client_id, redirect_uri, challenge, scope=DEFAULT_SCOPE,
                   state=None, accounts_base=DEFAULT_ACCOUNTS_BASE):
    """Authorization URL for the Authorization Code + PKCE flow."""
    if not client_id:
        raise ValueError("client_id is required")
    if not redirect_uri:
        raise ValueError("redirect_uri is required")
    if not challenge:
        raise ValueError("code_challenge is required")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if state:
        params["state"] = state
    base = accounts_base.rstrip("/")
    return base + "/authorize?" + urllib.parse.urlencode(params)


class Token:
    """An access token plus its expiry bookkeeping."""

    def __init__(self, access_token, token_type="Bearer", expires_in=None,
                 refresh_token=None, scope=None):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.token_type = token_type
        self.expires_in = expires_in
        self.refresh_token = refresh_token
        self.scope = scope
        # 30 s safety margin so we refresh before the token actually dies.
        self.expires_at = (time.time() + expires_in - 30
                           if expires_in is not None else None)

    @classmethod
    def from_dict(cls, data):
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
        )

    def expired(self):
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at


def _read_error_body(response):
    """Best-effort Spotify error message from an HTTP error body."""
    try:
        raw = response.read()
    except Exception:
        return "", None
    retry_after = response.headers.get("Retry-After")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "", _as_int(retry_after)
    err = data.get("error")
    if isinstance(err, dict):
        return err.get("message", ""), _as_int(retry_after)
    if isinstance(err, str):  # token endpoint shape: {"error": "..."}
        return err, _as_int(retry_after)
    return "", _as_int(retry_after)


def _as_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _post_form(url, fields, basic_auth=None):
    """POST urlencoded form; return parsed JSON or raise SpotifyError."""
    body = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if basic_auth is not None:
        req.add_header("Authorization", "Basic " + basic_auth)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message, retry_after = _read_error_body(exc)
        raise SpotifyError(exc.code, message, retry_after) from exc


def exchange_code(code, client_id, redirect_uri, verifier,
                  accounts_base=DEFAULT_ACCOUNTS_BASE):
    """Authorization-code grant (PKCE). Returns a Token."""
    if not code or not verifier:
        raise ValueError("code and code_verifier are required")
    data = _post_form(
        accounts_base.rstrip("/") + "/api/token",
        {"grant_type": "authorization_code", "code": code,
         "redirect_uri": redirect_uri, "code_verifier": verifier,
         "client_id": client_id})
    return Token.from_dict(data)


def client_credentials_token(client_id, client_secret,
                             accounts_base=DEFAULT_ACCOUNTS_BASE):
    """Client-credentials grant. Cannot access user-private data."""
    if not client_id or not client_secret:
        raise ValueError("client_id and client_secret are required")
    basic = base64.b64encode(
        ("%s:%s" % (client_id, client_secret)).encode("utf-8")).decode("ascii")
    data = _post_form(
        accounts_base.rstrip("/") + "/api/token",
        {"grant_type": "client_credentials"}, basic_auth=basic)
    return Token.from_dict(data)


def refresh_token(token_refresh, client_id,
                  accounts_base=DEFAULT_ACCOUNTS_BASE):
    """Refresh-token grant. Returns a new Token."""
    if not token_refresh:
        raise ValueError("refresh_token is required")
    data = _post_form(
        accounts_base.rstrip("/") + "/api/token",
        {"grant_type": "refresh_token", "refresh_token": token_refresh,
         "client_id": client_id})
    return Token.from_dict(data)


def _check_limit(limit):
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ValueError("limit must be an integer between 1 and 50")


def _check_search_types(types):
    parts = [t.strip() for t in types.split(",") if t.strip()]
    if not parts or any(t not in SEARCH_TYPES for t in parts):
        raise ValueError("type must be one or more of: %s"
                         % ", ".join(SEARCH_TYPES))
    return ",".join(parts)


class SpotifyClient:
    """Minimal Spotify Web API client over urllib."""

    def __init__(self, access_token, api_base=DEFAULT_API_BASE):
        if not access_token:
            raise ValueError("access_token is required")
        self.access_token = access_token
        self.api_base = api_base.rstrip("/")

    def _url(self, path_or_url):
        if path_or_url.startswith("http://") or \
                path_or_url.startswith("https://"):
            return path_or_url
        return self.api_base + "/" + path_or_url.lstrip("/")

    def _request(self, method, path_or_url, params=None, body=None):
        url = self._url(path_or_url)
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(params)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.access_token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message, retry_after = _read_error_body(exc)
            raise SpotifyError(exc.code, message, retry_after) from exc

    def _get(self, path_or_url, params=None):
        return self._request("GET", path_or_url, params=params)

    def _put(self, path, body=None):
        return self._request("PUT", path, body=body if body is not None else {})

    # -- profile / playlists (challenge Steps 1-2) --
    def get_me(self):
        return self._get("/me")

    def get_playlists(self, limit=20, offset=0):
        _check_limit(limit)
        return self._get("/me/playlists",
                         {"limit": limit, "offset": offset})

    def get_playlist_tracks(self, playlist_id, limit=20, offset=0):
        _check_limit(limit)
        if not playlist_id:
            raise ValueError("playlist_id is required")
        return self._get("/playlists/%s/tracks" % playlist_id,
                         {"limit": limit, "offset": offset})

    # -- search / lookup (additions beyond the page) --
    def search(self, query, types="track", limit=20, offset=0):
        if not query or not query.strip():
            raise ValueError("query is required")
        _check_limit(limit)
        return self._get("/search", {"q": query,
                                     "type": _check_search_types(types),
                                     "limit": limit, "offset": offset})

    def get_track(self, track_id):
        if not track_id:
            raise ValueError("track_id is required")
        return self._get("/tracks/%s" % track_id)

    def get_artist(self, artist_id):
        if not artist_id:
            raise ValueError("artist_id is required")
        return self._get("/artists/%s" % artist_id)

    def get_artist_top_tracks(self, artist_id, market="US"):
        if not artist_id:
            raise ValueError("artist_id is required")
        return self._get("/artists/%s/top-tracks" % artist_id,
                         {"market": market})

    # -- playback (challenge Steps 3-4, Player API form) --
    def get_devices(self):
        return self._get("/me/player/devices")

    def transfer_playback(self, device_ids, play=True):
        if not device_ids:
            raise ValueError("at least one device_id is required")
        return self._put("/me/player",
                         {"device_ids": list(device_ids), "play": play})

    def play(self, device_id=None):
        body = {"device_id": device_id} if device_id else {}
        return self._put("/me/player/play", body)

    def pause(self):
        return self._put("/me/player/pause", {})


def iter_pages(client, first_page, max_items=None):
    """Yield items from a paginated Spotify response, following `next`.

    Stops at null `next`, an empty page, offset+len(items) >= total,
    or when max_items items have been yielded.
    """
    page = first_page
    yielded = 0
    while page is not None:
        items = page.get("items") or []
        for item in items:
            if max_items is not None and yielded >= max_items:
                return
            yield item
            yielded += 1
        if max_items is not None and yielded >= max_items:
            return
        nxt = page.get("next")
        if not nxt or not items:
            return
        total = page.get("total")
        offset = page.get("offset", 0)
        if total is not None and offset + len(items) >= total:
            return
        page = client._get(nxt)


def get_all_playlists(client, limit=20, max_items=None):
    return list(iter_pages(client, client.get_playlists(limit=limit),
                           max_items=max_items))


def get_all_playlist_tracks(client, playlist_id, limit=20, max_items=None):
    return list(iter_pages(
        client, client.get_playlist_tracks(playlist_id, limit=limit),
        max_items=max_items))


# -- pure formatters (used by the CLI and the tests) --

def _names(artists):
    return ", ".join(a.get("name", "") for a in (artists or []))


def format_track(track):
    album = track.get("album") or {}
    return "%s — %s (%s)" % (track.get("name", ""),
                              _names(track.get("artists")), album.get("name", ""))


def format_playlist(playlist):
    owner = playlist.get("owner") or {}
    return "%s (%d tracks) — %s" % (playlist.get("name", ""),
                                     playlist.get("tracks", {}).get("total", 0),
                                     owner.get("display_name", ""))


def format_artist(artist):
    followers = (artist.get("followers") or {}).get("total")
    genres = ", ".join(artist.get("genres") or [])
    suffix = " [%s]" % genres if genres else ""
    if followers is not None:
        suffix += " (%d followers)" % followers
    return "%s%s" % (artist.get("name", ""), suffix)


def format_device(device):
    active = " (active)" if device.get("is_active") else ""
    return "%s — %s [%s]%s" % (device.get("id", ""),
                                device.get("name", ""),
                                device.get("type", ""), active)


def _env(name, default=None):
    return os.environ.get(name, default)


def _client_from_args(args):
    token = args.token or _env("SPOTIFY_ACCESS_TOKEN")
    if not token:
        raise ValueError("no access token: pass --token or set "
                         "SPOTIFY_ACCESS_TOKEN")
    return SpotifyClient(token, api_base=args.api_base)


def _print_token(token):
    print("access_token: %s" % token.access_token)
    print("token_type: %s" % token.token_type)
    if token.expires_in is not None:
        print("expires_in: %s" % token.expires_in)
    if token.refresh_token:
        print("refresh_token: %s" % token.refresh_token)
    if token.scope:
        print("scope: %s" % token.scope)


def _add_api_args(parser):
    parser.add_argument("--api-base", default=_env("SPOTIFY_API_BASE",
                                                  DEFAULT_API_BASE))
    parser.add_argument("--token", default=None,
                        help="Bearer token (or SPOTIFY_ACCESS_TOKEN)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Spotify Client (Spotify Web API, stdlib only).")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth-url", help="Print the PKCE authorization URL.")
    p.add_argument("--client-id", default=_env("SPOTIFY_CLIENT_ID"))
    p.add_argument("--redirect-uri",
                   default=_env("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI))
    p.add_argument("--scope", default=DEFAULT_SCOPE)
    p.add_argument("--state", default=None)
    p.add_argument("--accounts-base",
                   default=_env("SPOTIFY_ACCOUNTS_BASE", DEFAULT_ACCOUNTS_BASE))
    p.add_argument("--verifier", default=None,
                   help="Use a given verifier instead of generating one.")

    p = sub.add_parser("exchange", help="Exchange an auth code for a token.")
    p.add_argument("code")
    p.add_argument("--client-id", default=_env("SPOTIFY_CLIENT_ID"))
    p.add_argument("--redirect-uri",
                   default=_env("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI))
    p.add_argument("--verifier", required=True)
    p.add_argument("--accounts-base",
                   default=_env("SPOTIFY_ACCOUNTS_BASE", DEFAULT_ACCOUNTS_BASE))

    p = sub.add_parser("refresh", help="Refresh an access token.")
    p.add_argument("refresh_token")
    p.add_argument("--client-id", default=_env("SPOTIFY_CLIENT_ID"))
    p.add_argument("--accounts-base",
                   default=_env("SPOTIFY_ACCOUNTS_BASE", DEFAULT_ACCOUNTS_BASE))

    p = sub.add_parser("token-client-credentials",
                       help="Client-credentials token (no user data).")
    p.add_argument("--client-id", default=_env("SPOTIFY_CLIENT_ID"))
    p.add_argument("--client-secret", default=_env("SPOTIFY_CLIENT_SECRET"))
    p.add_argument("--accounts-base",
                   default=_env("SPOTIFY_ACCOUNTS_BASE", DEFAULT_ACCOUNTS_BASE))

    p = sub.add_parser("me", help="Show the current user's profile.")
    _add_api_args(p)

    p = sub.add_parser("playlists", help="List the user's playlists.")
    _add_api_args(p)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-items", type=int, default=None)

    p = sub.add_parser("tracks", help="List a playlist's tracks.")
    _add_api_args(p)
    p.add_argument("playlist_id")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-items", type=int, default=None)

    p = sub.add_parser("search", help="Search tracks/artists/albums/playlists.")
    _add_api_args(p)
    p.add_argument("query")
    p.add_argument("--type", default="track")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("track", help="Show one track.")
    _add_api_args(p)
    p.add_argument("track_id")

    p = sub.add_parser("artist", help="Show one artist.")
    _add_api_args(p)
    p.add_argument("artist_id")

    p = sub.add_parser("devices", help="List playback devices.")
    _add_api_args(p)

    p = sub.add_parser("play", help="Resume playback (Player API).")
    _add_api_args(p)
    p.add_argument("--device-id", default=None)

    p = sub.add_parser("pause", help="Pause playback (Player API).")
    _add_api_args(p)

    p = sub.add_parser("transfer", help="Transfer playback to a device.")
    _add_api_args(p)
    p.add_argument("device_id")
    p.add_argument("--no-play", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "auth-url":
            verifier, challenge = ((args.verifier,
                                    code_challenge(args.verifier))
                                   if args.verifier else generate_pkce_pair())
            print("code_verifier: %s" % verifier)
            print("authorization_url: %s" % build_auth_url(
                args.client_id, args.redirect_uri, challenge,
                scope=args.scope, state=args.state,
                accounts_base=args.accounts_base))
            print("Open the URL, approve, then run: "
                  "exchange <code> --verifier %s" % verifier)
        elif args.command == "exchange":
            _print_token(exchange_code(
                args.code, args.client_id, args.redirect_uri, args.verifier,
                accounts_base=args.accounts_base))
        elif args.command == "refresh":
            _print_token(refresh_token(args.refresh_token, args.client_id,
                                       accounts_base=args.accounts_base))
        elif args.command == "token-client-credentials":
            _print_token(client_credentials_token(
                args.client_id, args.client_secret,
                accounts_base=args.accounts_base))
        elif args.command == "me":
            me = _client_from_args(args).get_me()
            print("%s (%s)" % (me.get("display_name", me.get("id", "")),
                                me.get("id", "")))
            if me.get("email"):
                print(me["email"])
        elif args.command == "playlists":
            for pl in get_all_playlists(_client_from_args(args),
                                        limit=args.limit,
                                        max_items=args.max_items):
                print(format_playlist(pl))
        elif args.command == "tracks":
            for item in get_all_playlist_tracks(
                    _client_from_args(args), args.playlist_id,
                    limit=args.limit, max_items=args.max_items):
                track = item.get("track") or {}
                print(format_track(track))
        elif args.command == "search":
            client = _client_from_args(args)
            data = client.search(args.query, types=args.type,
                                 limit=args.limit)
            for key in ("tracks", "artists", "albums", "playlists"):
                section = data.get(key)
                if not section:
                    continue
                for item in section.get("items", []):
                    if key == "tracks":
                        print(format_track(item))
                    elif key == "artists":
                        print(format_artist(item))
                    else:
                        print(item.get("name", ""))
        elif args.command == "track":
            print(format_track(_client_from_args(args).get_track(args.track_id)))
        elif args.command == "artist":
            print(format_artist(_client_from_args(args).get_artist(args.artist_id)))
        elif args.command == "devices":
            for dev in _client_from_args(args).get_devices().get("devices", []):
                print(format_device(dev))
        elif args.command == "play":
            _client_from_args(args).play(device_id=args.device_id)
            print("playing")
        elif args.command == "pause":
            _client_from_args(args).pause()
            print("paused")
        elif args.command == "transfer":
            _client_from_args(args).transfer_playback(
                [args.device_id], play=not args.no_play)
            print("playback transferred to %s" % args.device_id)
    except SpotifyError as exc:
        print("Spotify error %s: %s" % (exc.status, exc.message),
              file=sys.stderr)
        if exc.retry_after is not None:
            print("Retry-After: %s" % exc.retry_after, file=sys.stderr)
        return 1
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

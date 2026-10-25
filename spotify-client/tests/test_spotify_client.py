"""Tests for spotify_client.py — all HTTP against a local fake server.

No test contacts spotify.com or accounts.spotify.com. The fake
server binds 127.0.0.1 on an ephemeral port and records requests.
"""

import base64
import json
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import spotify_client as sc  # noqa: E402


def page(items, nxt, total, offset=0):
    return {"items": items, "next": nxt, "total": total,
            "limit": 20, "offset": offset}


TRACK_A = {"name": "Song A", "artists": [{"name": "Artist A"}],
           "album": {"name": "Album A"}}
TRACK_B = {"name": "Song B", "artists": [{"name": "Artist B"}],
           "album": {"name": "Album B"}}
TRACK_C = {"name": "Song C", "artists": [{"name": "Artist C"}],
           "album": {"name": "Album C"}}
PLAYLIST_A = {"name": "Chill", "tracks": {"total": 3},
              "owner": {"display_name": "me"}}
PLAYLIST_B = {"name": "Rock", "tracks": {"total": 1},
              "owner": {"display_name": "me"}}


class FakeHandler(BaseHTTPRequestHandler):
    requests = []  # class-level log, reset per test
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _send(self, status, payload, extra=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        FakeHandler.requests.append({
            "method": self.command, "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": raw.decode("utf-8", "replace"),
        })
        return raw

    def do_POST(self):
        raw = self._record()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/token":
            fields = urllib.parse.parse_qs(raw.decode())
            grant = fields.get("grant_type", [""])[0]
            if grant == "invalid":
                self._send(400, {"error": "invalid_grant"})
                return
            self._send(200, {"access_token": "tok-%s" % grant,
                             "token_type": "Bearer", "expires_in": 3600,
                             "refresh_token": "refresh-1",
                             "scope": "user-read-private"})
            return
        self._send(404, {"error": {"status": 404, "message": "not found"}})

    def do_GET(self):
        self._record()
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        base = "http://%s:%s" % self.server.server_address
        if parsed.path == "/v1/me":
            self._send(200, {"id": "user123", "display_name": "Test User",
                             "email": "test@example.com"})
        elif parsed.path == "/v1/me/playlists":
            if query.get("offset", ["0"])[0] == "0":
                self._send(200, page([PLAYLIST_A, PLAYLIST_B],
                                     base + "/v1/me/playlists?limit=20&offset=2",
                                     3, 0))
            else:
                self._send(200, page([{"name": "Jazz", "tracks": {"total": 5},
                                       "owner": {"display_name": "me"}}],
                                     None, 3, 2))
        elif parsed.path.startswith("/v1/playlists/") and parsed.path.endswith("/tracks"):
            if query.get("offset", ["0"])[0] == "0":
                self._send(200, page([{"track": TRACK_A}, {"track": TRACK_B}],
                                     base + "/v1/playlists/pl1/tracks?limit=20&offset=2",
                                     3, 0))
            else:
                self._send(200, page([{"track": TRACK_C}], None, 3, 2))
        elif parsed.path == "/v1/search":
            self._send(200, {"tracks": page([TRACK_A], None, 1),
                             "artists": page([], None, 0)})
        elif parsed.path.startswith("/v1/tracks/"):
            self._send(200, TRACK_A)
        elif parsed.path.startswith("/v1/artists/") and parsed.path.endswith("/top-tracks"):
            self._send(200, {"tracks": [TRACK_A, TRACK_B]})
        elif parsed.path.startswith("/v1/artists/"):
            self._send(200, {"name": "Artist A", "genres": ["rock"],
                             "followers": {"total": 42}})
        elif parsed.path == "/v1/me/player/devices":
            self._send(200, {"devices": [{"id": "dev1", "name": "Phone",
                                          "type": "Smartphone",
                                          "is_active": True}]})
        elif parsed.path == "/v1/bad-token":
            self._send(401, {"error": {"status": 401,
                                       "message": "Bad OAuth token"}})
        elif parsed.path == "/v1/missing":
            self._send(404, {"error": {"status": 404,
                                       "message": "Not found"}})
        elif parsed.path == "/v1/rate-limited":
            self._send(429, {"error": {"status": 429,
                                       "message": "Too many"}},
                       extra={"Retry-After": "5"})
        elif parsed.path == "/v1/broken":
            self._send(500, b"not json at all")
        else:
            self._send(404, {"error": {"status": 404, "message": "not found"}})

    def do_PUT(self):
        self._record()
        self._send(204, b"")


class SpotifyClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base = "http://%s:%s" % (host, port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeHandler.requests.clear()
        self.client = sc.SpotifyClient("test-token",
                                       api_base=self.base + "/v1")

    # -- pure helpers --
    def test_pkce_known_vector(self):
        # RFC 7636 Appendix B vector.
        self.assertEqual(
            sc.code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_pkce_pair_shape(self):
        verifier, challenge = sc.generate_pkce_pair()
        self.assertTrue(43 <= len(verifier) <= 128)
        self.assertEqual(challenge, sc.code_challenge(verifier))
        self.assertNotIn("=", challenge)
        self.assertNotIn("+", challenge)
        self.assertNotIn("/", challenge)

    def test_auth_url_contents(self):
        url = sc.build_auth_url("cid123", "http://127.0.0.1:8888/callback",
                                "chal", scope="user-read-private",
                                state="xyz", accounts_base=self.base)
        parsed = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["client_id"], ["cid123"])
        self.assertEqual(q["redirect_uri"],
                         ["http://127.0.0.1:8888/callback"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["state"], ["xyz"])
        self.assertNotIn("secret", url)

    def test_auth_url_validation(self):
        with self.assertRaises(ValueError):
            sc.build_auth_url("", "http://x/", "chal")
        with self.assertRaises(ValueError):
            sc.build_auth_url("cid", "", "chal")

    def test_formatters(self):
        self.assertEqual(sc.format_track(TRACK_A), "Song A — Artist A (Album A)")
        self.assertEqual(sc.format_playlist(PLAYLIST_A), "Chill (3 tracks) — me")
        self.assertEqual(sc.format_artist({"name": "Artist A",
                                           "genres": ["rock"],
                                           "followers": {"total": 42}}),
                         "Artist A [rock] (42 followers)")
        self.assertEqual(sc.format_device({"id": "dev1", "name": "Phone",
                                           "type": "Smartphone",
                                           "is_active": True}),
                         "dev1 — Phone [Smartphone] (active)")
        self.assertEqual(sc.format_track({"name": "X"}), "X —  ()")

    def test_validation_before_network(self):
        with self.assertRaises(ValueError):
            self.client.search("   ")
        with self.assertRaises(ValueError):
            self.client.search("x", types="bogus")
        with self.assertRaises(ValueError):
            self.client.search("x", limit=0)
        with self.assertRaises(ValueError):
            self.client.get_playlists(limit=51)
        with self.assertRaises(ValueError):
            self.client.transfer_playback([])
        with self.assertRaises(ValueError):
            sc.SpotifyClient("")
        self.assertEqual(FakeHandler.requests, [])

    def test_token_expiry(self):
        self.assertFalse(sc.Token("t", expires_in=3600).expired())
        self.assertTrue(sc.Token("t", expires_in=0).expired())
        self.assertFalse(sc.Token("t").expired())

    # -- token endpoints --
    def test_exchange_code(self):
        token = sc.exchange_code("code1", "cid", "http://127.0.0.1:8888/callback",
                                 "verifier", accounts_base=self.base)
        self.assertEqual(token.access_token, "tok-authorization_code")
        self.assertEqual(token.refresh_token, "refresh-1")
        self.assertFalse(token.expired())
        req = FakeHandler.requests[-1]
        fields = urllib.parse.parse_qs(req["body"])
        self.assertEqual(fields["grant_type"], ["authorization_code"])
        self.assertEqual(fields["code"], ["code1"])
        self.assertEqual(fields["code_verifier"], ["verifier"])

    def test_client_credentials_basic_auth(self):
        token = sc.client_credentials_token("cid", "sec",
                                            accounts_base=self.base)
        self.assertEqual(token.access_token, "tok-client_credentials")
        req = FakeHandler.requests[-1]
        expected = "Basic " + base64.b64encode(b"cid:sec").decode()
        self.assertEqual(req["auth"], expected)

    def test_refresh(self):
        token = sc.refresh_token("refresh-1", "cid", accounts_base=self.base)
        self.assertEqual(token.access_token, "tok-refresh_token")

    def test_token_error(self):
        with self.assertRaises(sc.SpotifyError) as ctx:
            sc._post_form(self.base + "/api/token",
                          {"grant_type": "invalid"})
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.message, "invalid_grant")

    # -- API endpoints --
    def test_get_me(self):
        me = self.client.get_me()
        self.assertEqual(me["id"], "user123")
        self.assertEqual(me["email"], "test@example.com")
        self.assertEqual(FakeHandler.requests[-1]["auth"], "Bearer test-token")

    def test_playlists_pagination(self):
        playlists = sc.get_all_playlists(self.client)
        self.assertEqual([p["name"] for p in playlists],
                         ["Chill", "Rock", "Jazz"])

    def test_playlists_max_items_stops_early(self):
        playlists = sc.get_all_playlists(self.client, max_items=2)
        self.assertEqual([p["name"] for p in playlists], ["Chill", "Rock"])
        # Only the first page was fetched.
        self.assertEqual(len(FakeHandler.requests), 1)

    def test_playlist_tracks_pagination(self):
        tracks = sc.get_all_playlist_tracks(self.client, "pl1")
        self.assertEqual([t["track"]["name"] for t in tracks],
                         ["Song A", "Song B", "Song C"])

    def test_search(self):
        data = self.client.search("song", types="track")
        self.assertEqual(data["tracks"]["items"][0]["name"], "Song A")
        req = FakeHandler.requests[-1]
        self.assertIn("q=song", req["path"])
        self.assertIn("type=track", req["path"])

    def test_track_artist_top_tracks_devices(self):
        self.assertEqual(self.client.get_track("t1")["name"], "Song A")
        artist = self.client.get_artist("a1")
        self.assertEqual(artist["followers"]["total"], 42)
        top = self.client.get_artist_top_tracks("a1")
        self.assertEqual(len(top["tracks"]), 2)
        devices = self.client.get_devices()["devices"]
        self.assertEqual(devices[0]["id"], "dev1")

    def test_play_pause_transfer_bodies(self):
        self.client.play(device_id="dev1")
        self.assertEqual(json.loads(FakeHandler.requests[-1]["body"]),
                         {"device_id": "dev1"})
        self.client.pause()
        self.assertEqual(json.loads(FakeHandler.requests[-1]["body"]), {})
        self.client.transfer_playback(["dev1", "dev2"])
        self.assertEqual(json.loads(FakeHandler.requests[-1]["body"]),
                         {"device_ids": ["dev1", "dev2"], "play": True})

    def test_errors(self):
        for path, status, message in (
                ("/bad-token", 401, "Bad OAuth token"),
                ("/missing", 404, "Not found")):
            with self.assertRaises(sc.SpotifyError) as ctx:
                self.client._get(path)
            self.assertEqual(ctx.exception.status, status)
            self.assertEqual(ctx.exception.message, message)
        with self.assertRaises(sc.SpotifyError) as ctx:
            self.client._get("/rate-limited")
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(ctx.exception.retry_after, 5)
        with self.assertRaises(sc.SpotifyError) as ctx:
            self.client._get("/broken")
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(ctx.exception.message, "")

    def test_cli_auth_url(self):
        out = []
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as buf:
            rc = sc.main(["auth-url", "--client-id", "cid123",
                          "--redirect-uri", "http://127.0.0.1:8888/callback",
                          "--accounts-base", self.base,
                          "--verifier", "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("code_challenge_method=S256", text)
        self.assertIn("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", text)


if __name__ == "__main__":
    unittest.main()

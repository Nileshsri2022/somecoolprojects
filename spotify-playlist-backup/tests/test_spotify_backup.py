#!/usr/bin/env python3
"""Tests for spotify_backup.py against a local fake Spotify API.

No test contacts the real Spotify API; the fake runs on localhost on
an ephemeral (OS-assigned) port.
"""

import csv
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
import zipfile
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spotify_backup import (  # noqa: E402
    SpotifyApiError, SpotifyClient, csv_text, diff_backups, export_csv,
    export_zip_csv, list_backups, load_backup, main, next_version,
    normalize_track_item, parse_playlist_id, restore_plan, write_backup)

TRACKS = [
    {"added_at": "2026-01-01T00:00:00Z",
     "track": {"id": "t1", "uri": "spotify:track:t1", "name": "Song One",
               "artists": [{"name": "Artist A"}],
               "album": {"name": "Album One"}, "duration_ms": 180000}},
    {"added_at": "2026-01-02T00:00:00Z",
     "track": {"id": "t2", "uri": "spotify:track:t2", "name": "Song Two",
               "artists": [{"name": "Artist B"}, {"name": "Artist C"}],
               "album": {"name": "Album Two"}, "duration_ms": 200000}},
    {"added_at": "2026-01-03T00:00:00Z",
     "track": {"id": "t3", "uri": "spotify:track:t3", "name": "Song Three",
               "artists": [{"name": "Artist A"}],
               "album": {"name": "Album Three"}, "duration_ms": 210000}},
    {"added_at": "2026-01-04T00:00:00Z", "track": None},  # removed track
]
METAS = {
    "pl1": {"id": "pl1", "name": "My Playlist", "description": "desc",
            "owner": {"id": "user1"}, "public": True,
            "snapshot_id": "snap1"},
    "pl2": {"id": "pl2", "name": "Second Playlist", "description": "",
            "owner": {"id": "user1"}, "public": False,
            "snapshot_id": "snap2"},
}
CREATED = []
ADDED = []


def _page(items, query):
    limit = int(query.get("limit", ["100"])[0])
    offset = int(query.get("offset", ["0"])[0])
    chunk = items[offset:offset + limit]
    nxt = None
    if offset + limit < len(items):
        nxt = f"?limit={limit}&offset={offset + limit}"
    return {"items": chunk, "next": nxt, "total": len(items)}


class FakeSpotify(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        if self.path == "/api/token":
            form = urllib.parse.parse_qs(raw)
            grant = form.get("grant_type", [""])[0]
            if not self.headers.get("Authorization", "").startswith("Basic "):
                self._send(401, {"error": "missing basic auth"})
                return
            if grant == "client_credentials":
                self._send(200, {"access_token": "fake-client-token",
                                 "token_type": "Bearer", "expires_in": 3600})
            elif grant == "authorization_code":
                self._send(200, {"access_token": "fake-user-token",
                                 "token_type": "Bearer", "expires_in": 3600})
            else:
                self._send(400, {"error": "unsupported_grant_type"})
            return
        if self.path.startswith("/v1/users/") and self.path.endswith(
                "/playlists"):
            CREATED.append(json.loads(raw or "{}"))
            self._send(201, {"id": "newpl", "name": "created"})
            return
        if self.path.startswith("/v1/playlists/") and self.path.endswith(
                "/tracks"):
            ADDED.extend(json.loads(raw or "{}").get("uris", []))
            self._send(201, {"snapshot_id": "snap-new"})
            return
        self._send(404, {"error": "not found"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/v1/me/playlists":
            summaries = [{"id": pid, "name": METAS[pid]["name"]}
                         for pid in ("pl1", "pl2")]
            page = _page(summaries, query)
            # _page's `next` is relative; client only checks truthiness.
            self._send(200, page)
            return
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "v1" and parts[1] == "playlists":
            meta = METAS.get(parts[2])
            if meta is None:
                self._send(404, {"error": "not found"})
            else:
                self._send(200, meta)
            return
        if len(parts) == 4 and parts[0] == "v1" and parts[1] == "playlists" \
                and parts[3] == "tracks":
            if parts[2] not in METAS:
                self._send(404, {"error": "not found"})
                return
            self._send(200, _page(TRACKS, query))
            return
        self._send(404, {"error": "not found"})


class FakeServerMixin:
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSpotify)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def client(self, **kw):
        kw.setdefault("api_base", self.base)
        kw.setdefault("auth_base", self.base)
        kw.setdefault("client_id", "cid")
        kw.setdefault("client_secret", "csecret")
        return SpotifyClient(**kw)


class TestParsing(unittest.TestCase):
    def test_bare_id(self):
        self.assertEqual(parse_playlist_id("pl1"), "pl1")

    def test_uri(self):
        self.assertEqual(parse_playlist_id("spotify:playlist:abc123"),
                         "abc123")

    def test_url_with_query(self):
        self.assertEqual(
            parse_playlist_id(
                "https://open.spotify.com/playlist/abc123?si=xyz"), "abc123")

    def test_url_with_fragment(self):
        self.assertEqual(
            parse_playlist_id(
                "https://open.spotify.com/playlist/abc123#frag"), "abc123")

    def test_garbage_raises(self):
        for bad in ("", "  ", "spotify:playlist:", "not a playlist",
                    "https://example.com/playlist/x"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_playlist_id(bad)


class TestClient(FakeServerMixin, unittest.TestCase):
    def test_client_credentials_token(self):
        client = self.client()
        payload = client.get_client_credentials_token()
        self.assertEqual(payload["access_token"], "fake-client-token")
        self.assertEqual(client.access_token, "fake-client-token")

    def test_exchange_code(self):
        client = self.client()
        payload = client.exchange_code("code123",
                                       "http://localhost:8000/cb")
        self.assertEqual(payload["access_token"], "fake-user-token")

    def test_auth_url(self):
        url = SpotifyClient.build_auth_url(
            "cid", "http://localhost:8000/cb",
            scope="playlist-read-private", state="s1",
            auth_base="https://accounts.spotify.com")
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["cid"])
        self.assertEqual(query["scope"], ["playlist-read-private"])

    def test_fetch_playlist_paginates_and_skips_null_track(self):
        client = self.client(access_token="fake-client-token")
        backup = client.fetch_playlist("pl1")
        self.assertEqual(backup["name"], "My Playlist")
        self.assertEqual(backup["track_count"], 3)
        self.assertEqual([t["track_name"] for t in backup["tracks"]],
                         ["Song One", "Song Two", "Song Three"])
        self.assertEqual(backup["tracks"][1]["artists"],
                         ["Artist B", "Artist C"])
        self.assertEqual(backup["tracks"][0]["album"], "Album One")

    def test_tracks_pagination_with_small_pages(self):
        client = self.client(access_token="fake-client-token")
        items = client.get_playlist_tracks("pl1", page_size=2)
        self.assertEqual(len(items), 4)  # 3 tracks + 1 null-track item

    def test_user_playlists(self):
        client = self.client(access_token="fake-user-token")
        playlists = client.get_user_playlists(page_size=1)
        self.assertEqual([p["id"] for p in playlists], ["pl1", "pl2"])

    def test_unknown_playlist_raises_404(self):
        client = self.client(access_token="fake-client-token")
        with self.assertRaises(SpotifyApiError) as ctx:
            client.fetch_playlist("nope")
        self.assertEqual(ctx.exception.status, 404)

    def test_normalize_null_track(self):
        self.assertIsNone(normalize_track_item({"track": None}))
        self.assertIsNone(normalize_track_item({"track": {}}))


class TestStore(unittest.TestCase):
    def _backup(self, tracks):
        return {"playlist_id": "pl1", "name": "My Playlist",
                "description": "", "owner_id": "user1", "public": True,
                "snapshot_id": "s", "track_count": len(tracks),
                "tracks": tracks}

    def test_versioning_manifest_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            track = {"track_id": "t1", "uri": "spotify:track:t1",
                     "track_name": "Song One", "artists": ["Artist A"],
                     "album": "Album One", "duration_ms": 1, "added_at": ""}
            v1, p1 = write_backup(tmp, self._backup([track]))
            v2, p2 = write_backup(tmp, self._backup([track]))
            self.assertEqual((v1, v2), (1, 2))
            self.assertTrue(p1.endswith("v001.json"))
            self.assertTrue(p2.endswith("v002.json"))
            self.assertEqual(load_backup(tmp, "pl1")["version"], 2)
            self.assertEqual(load_backup(tmp, "pl1", 1)["version"], 1)
            self.assertEqual(next_version(os.path.join(tmp, "pl1")), 3)
            rows = list_backups(tmp)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["versions"], [1, 2])
            self.assertEqual(rows[0]["name"], "My Playlist")

    def test_load_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_backup(tmp, "pl1")
            with self.assertRaises(FileNotFoundError):
                load_backup(tmp, "pl1", 9)
            self.assertEqual(list_backups(tmp), [])
            self.assertEqual(list_backups(os.path.join(tmp, "nope")), [])

    def test_diff(self):
        a = {"track_id": "t1", "uri": "spotify:track:t1",
             "track_name": "Song One", "artists": ["Artist A"]}
        b = {"track_id": "t2", "uri": "spotify:track:t2",
             "track_name": "Song Two", "artists": ["Artist B"]}
        result = diff_backups({"tracks": [a, b]}, {"tracks": [b]})
        self.assertEqual([t["track_name"] for t in result["removed"]],
                         ["Song One"])
        self.assertEqual(result["added"], [])
        self.assertEqual([t["track_name"] for t in result["unchanged"]],
                         ["Song Two"])

    def test_csv_and_zip_round_trip(self):
        backup = self._backup([
            {"track_id": "t1", "uri": "spotify:track:t1",
             "track_name": "Song, One", "artists": ["A", "B"],
             "album": "Alb", "duration_ms": 5, "added_at": "2026-01-01"}])
        text = csv_text(backup)
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0][0], "position")
        self.assertEqual(rows[1][1], "Song, One")
        self.assertEqual(rows[1][2], "A; B")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "out.csv")
            export_csv(backup, csv_path)
            self.assertTrue(os.path.exists(csv_path))
            zip_path = os.path.join(tmp, "out.zip")
            export_zip_csv(backup, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                self.assertEqual(zf.namelist(), ["pl1.csv"])
                self.assertEqual(zf.read("pl1.csv").decode(), text)

    def test_restore_plan(self):
        backup = self._backup([
            {"track_id": "t1", "uri": "spotify:track:t1",
             "track_name": "Song One", "artists": ["Artist A"]}])
        plan = restore_plan(backup)
        self.assertEqual(plan["track_count"], 1)
        self.assertEqual(plan["tracks"][0]["uri"], "spotify:track:t1")


class TestCli(FakeServerMixin, unittest.TestCase):
    def _run(self, args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(args)
        return code, buf.getvalue()

    def _base_args(self, tmp):
        return ["--backup-dir", tmp, "--api-base", self.base,
                "--auth-base", self.base, "--client-id", "cid",
                "--client-secret", "csecret"]

    def test_backup_list_show_diff_export_restore_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(self._base_args(tmp) + ["backup", "pl1"])
            self.assertEqual(code, 0, out)
            self.assertIn("version 1", out)
            code, out = self._run(self._base_args(tmp) + ["backup",
                                                          "spotify:playlist:pl1"])
            self.assertEqual(code, 0)
            code, out = self._run(self._base_args(tmp) + ["list"])
            self.assertEqual(code, 0)
            self.assertIn("pl1", out)
            code, out = self._run(self._base_args(tmp) + ["show", "pl1"])
            self.assertEqual(code, 0)
            self.assertIn("Song One", out)
            code, out = self._run(self._base_args(tmp) +
                                  ["diff", "pl1", "1", "2"])
            self.assertEqual(code, 0)
            self.assertIn("unchanged (3)", out)
            csv_out = os.path.join(tmp, "pl1.csv")
            code, out = self._run(self._base_args(tmp) +
                                  ["export", "pl1", "--out", csv_out])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(csv_out))
            zip_out = os.path.join(tmp, "pl1.zip")
            code, _ = self._run(self._base_args(tmp) +
                                ["export", "pl1", "--zip", "--out", zip_out])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(zip_out))
            plan_out = os.path.join(tmp, "plan.json")
            code, out = self._run(self._base_args(tmp) +
                                  ["restore-plan", "pl1", "--out", plan_out])
            self.assertEqual(code, 0)
            with open(plan_out) as fh:
                plan = json.load(fh)
            self.assertEqual(plan["track_count"], 3)

    def test_backup_all_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self._base_args(tmp) + ["--access-token",
                                           "fake-user-token", "backup-all"]
            code, out = self._run(args)
            self.assertEqual(code, 0, out)
            self.assertIn("backed up 2 playlist(s)", out)
            # Restore pl1 against the fake (records create + add).
            CREATED.clear()
            ADDED.clear()
            code, out = self._run(
                self._base_args(tmp) + ["--access-token", "fake-user-token",
                                        "restore", "pl1", "--user-id",
                                        "user1"])
            self.assertEqual(code, 0, out)
            self.assertEqual(len(CREATED), 1)
            self.assertEqual(len(ADDED), 3)

    def test_token_and_auth_url_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(self._base_args(tmp) + ["token"])
            self.assertEqual(code, 0)
            self.assertIn("token_type=Bearer", out)
            self.assertNotIn("fake-client-token", out)
            code, out = self._run(self._base_args(tmp) +
                                  ["auth-url", "--redirect-uri",
                                   "http://localhost:8000/cb"])
            self.assertEqual(code, 0)
            self.assertIn("response_type=code", out)

    def test_bad_id_and_missing_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(self._base_args(tmp) +
                                ["backup", "not a playlist"])
            self.assertEqual(code, 2)
            # No credentials at all: env scrubbed, no flags.
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("SPOTIFY_")}
            old = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                code, _ = self._run(["--backup-dir", tmp,
                                     "--api-base", self.base,
                                     "--auth-base", self.base,
                                     "backup", "pl1"])
            finally:
                os.environ.clear()
                os.environ.update(old)
            self.assertEqual(code, 2)

    def test_unknown_playlist_cli_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(self._base_args(tmp) + ["backup", "nope"])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

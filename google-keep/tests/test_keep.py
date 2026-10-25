import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout, redirect_stderr
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keep


def make_store(tmpdir):
    return keep.NoteStore(os.path.join(tmpdir, "notes.json"))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = make_store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_defaults(self):
        note = self.store.create({"title": "Hi", "content": "body"})
        self.assertEqual(len(note["id"]), 32)
        self.assertEqual(note["color"], "default")
        self.assertEqual(note["labels"], [])
        self.assertFalse(note["pinned"])
        self.assertFalse(note["archived"])
        self.assertTrue(note["created_at"].endswith("Z"))

    def test_create_validation(self):
        for bad in ({}, {"title": "   ", "content": ""},
                    {"title": "x" * 1001},
                    {"content": "x" * 50001},
                    {"title": "t", "color": "magenta"},
                    {"title": "t", "labels": "nope"},
                    {"title": "t", "labels": [1]},
                    {"title": "t", "pinned": "yes"},
                    {"title": "t", "surprise": 1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.store.create(bad)

    def test_labels_cleaned(self):
        note = self.store.create(
            {"title": "t", "labels": [" work ", "", "work", "home"]})
        self.assertEqual(note["labels"], ["work", "home"])

    def test_get_delete_unknown(self):
        with self.assertRaises(KeyError):
            self.store.get("nope")
        with self.assertRaises(KeyError):
            self.store.delete("nope")

    def test_update_merge_and_empty_guard(self):
        note = self.store.create({"title": "A", "content": "B", "color": "red"})
        updated = self.store.update(note["id"], {"content": "C"})
        self.assertEqual(updated["title"], "A")
        self.assertEqual(updated["content"], "C")
        self.assertEqual(updated["color"], "red")
        self.assertGreaterEqual(updated["updated_at"], note["updated_at"])
        with self.assertRaises(ValueError):
            self.store.update(note["id"], {"title": "", "content": "  "})
        with self.assertRaises(KeyError):
            self.store.update("nope", {"title": "x"})

    def test_delete_removes(self):
        note = self.store.create({"title": "t"})
        self.store.delete(note["id"])
        with self.assertRaises(KeyError):
            self.store.get(note["id"])

    def test_persistence_and_atomic_save(self):
        note = self.store.create({"title": "keep me", "pinned": True})
        self.assertFalse(os.path.exists(self.store.path + ".tmp"))
        reloaded = keep.NoteStore(self.store.path)
        self.assertEqual(reloaded.get(note["id"])["title"], "keep me")
        self.assertTrue(reloaded.get(note["id"])["pinned"])

    def test_corrupt_file_is_loud(self):
        path = os.path.join(self.tmp.name, "notes.json")
        with open(path, "w") as f:
            f.write("{not json")
        with self.assertRaises(ValueError):
            keep.NoteStore(path)
        with open(path, "w") as f:
            json.dump({"version": 1}, f)
        with self.assertRaises(ValueError):
            keep.NoteStore(path)

    def test_ordering_pinned_first_then_recent(self):
        a = self.store.create({"title": "old"})
        b = self.store.create({"title": "new"})
        self.store.update(a["id"], {"title": "old edited"})
        self.assertEqual([n["title"] for n in self.store.list_notes()],
                         ["old edited", "new"])
        self.store.update(b["id"], {"pinned": True})
        self.assertEqual(self.store.list_notes()[0]["title"], "new")

    def test_search_and_filters(self):
        self.store.create({"title": "Groceries", "content": "milk",
                           "labels": ["home"]})
        self.store.create({"title": "Work", "content": "deploy",
                           "archived": True})
        self.store.create({"title": "Other", "content": "MILK shake"})
        self.assertEqual(len(self.store.list_notes(q="milk")), 2)
        self.assertEqual(len(self.store.list_notes(q="HOME")), 1)
        self.assertEqual(self.store.list_notes(q="deploy"), [])
        self.assertEqual(len(self.store.list_notes(q="deploy",
                                                   include_archived=True)), 1)
        self.assertEqual(len(self.store.list_notes(archived=True)), 1)
        self.assertEqual(len(self.store.list_notes(label="home")), 1)
        self.assertEqual(len(self.store.list_notes(pinned=True)), 0)


def start_server(store, token=None):
    handler = keep.make_handler(store, token, threading.Lock())
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]


def request(base, path, method="GET", body=None, headers=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode()
                                 if body is not None else None,
                                 headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, raw


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = make_store(self.tmp.name)
        self.server, self.base = start_server(self.store)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_lifecycle(self):
        status, note = request(self.base, "/api/notes", "POST",
                               {"title": "A", "content": "B"})
        self.assertEqual(status, 201)
        nid = note["id"]
        status, got = request(self.base, "/api/notes/" + nid)
        self.assertEqual((status, got["title"]), (200, "A"))
        status, edited = request(self.base, "/api/notes/" + nid, "PUT",
                                 {"title": "A2"})
        self.assertEqual((status, edited["title"]), (200, "A2"))
        status, notes = request(self.base, "/api/notes")
        self.assertEqual([n["id"] for n in notes], [nid])
        status, _ = request(self.base, "/api/notes/" + nid, "DELETE")
        self.assertEqual(status, 204)
        status, body = request(self.base, "/api/notes/" + nid)
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_error_paths(self):
        status, _ = request(self.base, "/api/notes", "POST", {})
        self.assertEqual(status, 400)
        status, _ = request(self.base, "/api/notes", "POST",
                            {"title": "t", "nope": 1})
        self.assertEqual(status, 400)
        status, _ = request(self.base, "/api/notes/doesnotexist")
        self.assertEqual(status, 404)
        status, _ = request(self.base, "/api/notes", "DELETE")
        self.assertEqual(status, 404)
        status, _ = request(self.base, "/api/notes/abc", "POST",
                            {"title": "t"})
        self.assertEqual(status, 405)
        status, _ = request(self.base, "/api/unknown")
        self.assertEqual(status, 404)
        # malformed JSON and wrong content type
        req = urllib.request.Request(self.base + "/api/notes", method="POST",
                                     data=b"{oops",
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)
        req = urllib.request.Request(self.base + "/api/notes", method="POST",
                                     data=b"title=x",
                                     headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 415)

    def test_query_flags(self):
        self.store.create({"title": "Pinned", "pinned": True})
        self.store.create({"title": "Plain"})
        status, notes = request(self.base, "/api/notes?pinned=true")
        self.assertEqual([n["title"] for n in notes], ["Pinned"])
        status, _ = request(self.base, "/api/notes?pinned=maybe")
        self.assertEqual(status, 400)
        status, notes = request(self.base, "/api/notes?q=pinned")
        self.assertEqual(len(notes), 1)

    def test_ui_route(self):
        req = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers["Content-Type"])
            self.assertIn('id="grid"', resp.read().decode())

    def test_token_auth(self):
        server2, base2 = start_server(self.store, token="secret")
        try:
            status, _ = request(base2, "/api/notes")
            self.assertEqual(status, 401)
            status, _ = request(base2, "/api/notes", headers={
                "Authorization": "Bearer secret"})
            self.assertEqual(status, 200)
            status, _ = request(base2, "/api/notes", headers={
                "Authorization": "Bearer wrong"})
            self.assertEqual(status, 401)
        finally:
            server2.shutdown()
            server2.server_close()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "notes.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = keep.main(["--data", self.data] + argv)
        return code, out.getvalue(), err.getvalue()

    def test_cli_roundtrip(self):
        code, out, _ = self.run_cli(["add", "--title", "Shop",
                                    "--content", "eggs"])
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli(["list"])
        self.assertIn("Shop", out)
        store = keep.NoteStore(self.data)
        nid = store.list_notes()[0]["id"]
        code, out, _ = self.run_cli(["search", "shop"])
        self.assertIn("Shop", out)
        code, out, _ = self.run_cli(["pin", nid])
        self.assertIn("📌", out)
        code, out, _ = self.run_cli(["edit", nid, "--title", "Shop2"])
        self.assertIn("Shop2", out)
        code, out, _ = self.run_cli(["get", nid, "--json"])
        self.assertEqual(json.loads(out)["title"], "Shop2")
        code, out, _ = self.run_cli(["archive", nid])
        self.assertIn("archived", out)
        code, out, _ = self.run_cli(["list"])
        self.assertIn("(no notes)", out)
        code, out, _ = self.run_cli(["delete", nid])
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["get", nid])
        self.assertNotEqual(code, 0)
        self.assertIn("error", err)
        code, out, err = self.run_cli(["add"])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

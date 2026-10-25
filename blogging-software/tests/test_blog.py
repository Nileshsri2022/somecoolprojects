#!/usr/bin/env python3
"""Tests for blogging-software (stdlib unittest only)."""
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blog
from blog import BlogStore, make_handler, markdown_to_html, render_feed, render_index, render_post


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = BlogStore(self.tmp.name)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_create_get_round_trip(self):
        pid = self.store.create_post("Hello", "Sum", "Body text",
                                     published_at="2026-01-02T03:04:05Z")
        post = self.store.get_post(pid)
        self.assertEqual(post["title"], "Hello")
        self.assertEqual(post["summary"], "Sum")
        self.assertEqual(post["body"], "Body text")
        self.assertEqual(post["published_at"], "2026-01-02T03:04:05Z")

    def test_published_at_defaults_to_creation_time(self):
        pid = self.store.create_post("T", body="B")
        self.assertTrue(self.store.get_post(pid)["published_at"])

    def test_list_newest_first(self):
        self.store.create_post("Old", body="B", published_at="2026-01-01T00:00:00Z")
        self.store.create_post("New", body="B", published_at="2026-01-03T00:00:00Z")
        self.assertEqual([p["title"] for p in self.store.list_posts()],
                         ["New", "Old"])

    def test_update_changes_fields_and_published_at(self):
        pid = self.store.create_post("T", body="B",
                                     published_at="2026-01-01T00:00:00Z")
        updated = self.store.update_post(pid, title="T2",
                                         published_at="2026-02-01T00:00:00Z")
        self.assertEqual(updated["title"], "T2")
        self.assertEqual(updated["published_at"], "2026-02-01T00:00:00Z")

    def test_update_missing_raises(self):
        with self.assertRaises(LookupError):
            self.store.update_post(999, title="X")

    def test_empty_title_or_body_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create_post("", body="B")
        with self.assertRaises(ValueError):
            self.store.create_post("T", body="   ")
        pid = self.store.create_post("T", body="B")
        with self.assertRaises(ValueError):
            self.store.update_post(pid, title="")

    def test_delete(self):
        pid = self.store.create_post("T", body="B")
        self.store.delete_post(pid)
        self.assertIsNone(self.store.get_post(pid))
        with self.assertRaises(LookupError):
            self.store.delete_post(pid)

    def test_comments_newest_first_and_validation(self):
        pid = self.store.create_post("T", body="B")
        self.store.add_comment(pid, "Ana", "ana@example.com", "First")
        self.store.add_comment(pid, "Bo", "", "Second")
        names = [c["name"] for c in self.store.list_comments(pid)]
        self.assertEqual(names, ["Bo", "Ana"])
        with self.assertRaises(ValueError):
            self.store.add_comment(pid, "", body="x")
        with self.assertRaises(ValueError):
            self.store.add_comment(pid, "Ana", body="  ")
        with self.assertRaises(LookupError):
            self.store.add_comment(999, "Ana", body="x")

    def test_comment_email_stored_not_rendered(self):
        pid = self.store.create_post("T", body="B")
        self.store.add_comment(pid, "Ana", "ana@example.com", "Hi")
        post = self.store.get_post(pid)
        rendered = render_post(post, self.store.list_comments(pid))
        self.assertIn("ana@example.com", self.store.list_comments(pid)[0]["email"])
        self.assertNotIn("ana@example.com", rendered)
        self.assertIn("Ana", rendered)


class RenderTest(unittest.TestCase):
    def test_markdown_basics(self):
        out = markdown_to_html("# Head\n\nHello **bold** and *ital* and `code`.\n\n- one\n- two\n\n[link](https://example.com)")
        self.assertIn("<h1>Head</h1>", out)
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>ital</em>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn("<ul><li>one</li><li>two</li></ul>", out)
        self.assertIn('<a href="https://example.com">link</a>', out)

    def test_markdown_escapes_raw_html(self):
        out = markdown_to_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_markdown_rejects_javascript_link(self):
        out = markdown_to_html("[x](javascript:alert(1))")
        self.assertNotIn("javascript:", out)

    def test_index_links_and_empty(self):
        self.assertIn("No posts yet", render_index([]))
        posts = [{"id": 3, "title": "Third", "summary": "S",
                  "published_at": "2026-01-03T00:00:00Z"},
                 {"id": 1, "title": "First", "summary": "",
                  "published_at": "2026-01-01T00:00:00Z"}]
        out = render_index(posts)
        self.assertIn('<a href="/posts/3">Third</a>', out)
        self.assertLess(out.index("Third"), out.index("First"))

    def test_feed_shape(self):
        posts = [{"id": 1, "title": "A & B", "summary": "S",
                  "published_at": "2026-01-01T00:00:00Z"}]
        out = render_feed(posts)
        self.assertIn("<rss", out)
        self.assertIn("<item>", out)
        self.assertIn("A &amp; B", out)


class HttpTest(unittest.TestCase):
    PASSWORD = "testpw"

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = BlogStore(self.tmp.name)
        self.pid = self.store.create_post("First Post", "Summary here",
                                          "# Hello\n\nBody text.",
                                          published_at="2026-01-01T00:00:00Z")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.store, self.PASSWORD))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.store.close()
        os.unlink(self.tmp.name)

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self._url(path))
        if cookie:
            req.add_header("Cookie", cookie)
        opener = urllib.request.build_opener(NoRedirectHandler())
        try:
            with opener.open(req) as resp:
                return resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), e.headers

    def _post(self, path, data, cookie=None):
        req = urllib.request.Request(
            self._url(path), data=data.encode(), method="POST")
        if cookie:
            req.add_header("Cookie", cookie)
        opener = urllib.request.build_opener(NoRedirectHandler())
        try:
            with opener.open(req) as resp:
                return resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), e.headers

    def _login_cookie(self):
        _, _, headers = self._post("/login", "password=testpw")
        return headers.get("Set-Cookie", "").split(";")[0]

    def test_index_lists_post_as_link(self):
        status, body, _ = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(f'<a href="/posts/{self.pid}">First Post</a>', body)

    def test_post_page_shows_body_and_comments(self):
        self.store.add_comment(self.pid, "Ana", "", "Nice post")
        status, body, _ = self._get(f"/posts/{self.pid}")
        self.assertEqual(status, 200)
        self.assertIn("Body text", body)
        self.assertIn("Nice post", body)

    def test_missing_post_and_unknown_path_404(self):
        status, _, _ = self._get("/posts/99999")
        self.assertEqual(status, 404)
        status, _, _ = self._get("/nope")
        self.assertEqual(status, 404)

    def test_editor_requires_login(self):
        status, _, headers = self._get("/editor")
        self.assertEqual(status, 302)
        self.assertIn("/login", headers.get("Location", ""))

    def test_login_flow_wrong_and_right(self):
        status, body, _ = self._post("/login", "password=wrong")
        self.assertEqual(status, 200)
        self.assertIn("wrong password", body)
        cookie = self._login_cookie()
        self.assertTrue(cookie)
        status, body, _ = self._get("/editor", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("First Post", body)

    def test_editor_create_visible_on_index_and_post(self):
        cookie = self._login_cookie()
        status, _, headers = self._post(
            "/editor/post",
            "title=Second&summary=S2&body=Second+body&published_at=2026-01-05T00:00:00Z",
            cookie=cookie)
        self.assertEqual(status, 302)
        location = headers.get("Location", "")
        self.assertTrue(location.startswith("/posts/"))
        status, body, _ = self._get("/")
        self.assertIn("Second", body)
        # Newest first: Second before First.
        self.assertLess(body.index("Second"), body.index("First Post"))

    def test_editor_create_rejects_empty_title(self):
        cookie = self._login_cookie()
        status, body, _ = self._post("/editor/post", "title=&body=x", cookie=cookie)
        self.assertEqual(status, 400)

    def test_comment_post_flow(self):
        status, _, headers = self._post(
            f"/posts/{self.pid}/comments",
            "name=Bo&email=bo%40example.com&comment=Great")
        self.assertEqual(status, 302)
        _, body, _ = self._get(f"/posts/{self.pid}")
        self.assertIn("Great", body)
        self.assertNotIn("bo@example.com", body)

    def test_feed(self):
        status, body, headers = self._get("/feed.xml")
        self.assertEqual(status, 200)
        self.assertIn("<rss", body)
        self.assertIn("First Post", body)

    def test_index_newest_first_via_http(self):
        self.store.create_post("Newer", body="B", published_at="2026-06-01T00:00:00Z")
        _, body, _ = self._get("/")
        self.assertLess(body.index("Newer"), body.index("First Post"))


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmpdir.name, "test.db")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run(self, *args):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = blog.main(["--db", self.db, *args])
        return code, buf.getvalue()

    def test_cli_round_trip(self):
        code, out = self._run("create", "--title", "CLI Post",
                              "--summary", "S", "--body", "CLI body")
        self.assertEqual(code, 0)
        pid = out.strip()
        code, out = self._run("list")
        self.assertIn("CLI Post", out)
        code, out = self._run("show", pid)
        self.assertIn("CLI body", out)
        code, out = self._run("comment", pid, "--name", "Ana", "--text", "Hi")
        self.assertEqual(code, 0)
        code, out = self._run("edit", pid, "--title", "CLI Post 2")
        self.assertEqual(code, 0)
        code, out = self._run("list")
        self.assertIn("CLI Post 2", out)
        code, out = self._run("show", "99999")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

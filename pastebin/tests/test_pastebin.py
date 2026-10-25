"""Tests for pastebin.py: real server on an ephemeral localhost port."""

import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pastebin import make_server  # noqa: E402


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(method, url, data=None, headers=None):
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        resp = opener.open(req)
        return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


class PastebinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def create_form(self, content, expiry="never", language="plain"):
        data = urllib.parse.urlencode(
            {"content": content, "expiry": expiry,
             "language": language}).encode()
        return request("POST", self.base() + "/",
                       data=data,
                       headers={"Content-Type":
                                "application/x-www-form-urlencoded"})

    def test_home_page(self):
        status, _, body = request("GET", self.base() + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<form", body)
        self.assertIn(b"name='content'", body)

    def test_create_via_form_redirects_and_retrieves(self):
        status, headers, _ = self.create_form("hello pastebin")
        self.assertEqual(status, 303)
        location = headers["Location"]
        self.assertTrue(location.startswith("/"))
        self.assertEqual(len(location.strip("/")), 7)
        status, _, body = request("GET", self.base() + location)
        self.assertEqual(status, 200)
        self.assertIn(b"hello pastebin", body)

    def test_create_via_json(self):
        data = json.dumps({"content": "json paste",
                           "language": "plain"}).encode()
        status, _, body = request(
            "POST", self.base() + "/",
            data=data, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 201)
        payload = json.loads(body)
        self.assertIn("id", payload)
        status, _, body = request("GET", self.base() + payload["url"])
        self.assertEqual(status, 200)
        self.assertIn(b"json paste", body)

    def test_unknown_id_404(self):
        for path in ("/nosuchid", "/nosuchid/raw", "/nosuchid/delete"):
            status, _, _ = request("GET", self.base() + path)
            self.assertEqual(status, 404, path)

    def test_delete_flow(self):
        status, headers, _ = self.create_form("to be deleted")
        location = headers["Location"]
        status, _, body = request("GET", self.base() + location + "/delete")
        self.assertEqual(status, 200)
        self.assertIn(b"Are you sure", body)
        status, headers, _ = request("POST",
                                     self.base() + location + "/delete")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")
        status, _, _ = request("GET", self.base() + location)
        self.assertEqual(status, 404)
        # Deleting twice: second attempt is 404.
        status, _, _ = request("POST",
                               self.base() + location + "/delete")
        self.assertEqual(status, 404)

    def test_expiry(self):
        data = json.dumps({"content": "gone already",
                           "expiry_seconds": 0}).encode()
        status, _, body = request(
            "POST", self.base() + "/",
            data=data, headers={"Content-Type": "application/json"})
        self.assertEqual(status, 201)
        url = json.loads(body)["url"]
        status, _, _ = request("GET", self.base() + url)
        self.assertEqual(status, 404)
        # Never-expiring paste stays retrievable.
        status, headers, _ = self.create_form("stays forever")
        status, _, body = request("GET", self.base() + headers["Location"])
        self.assertEqual(status, 200)
        self.assertIn(b"stays forever", body)

    def test_python_highlighting_and_escaping(self):
        content = "def greet():\n    return '<script>alert(1)</script>'"
        status, headers, _ = self.create_form(content, language="python")
        status, _, body = request("GET", self.base() + headers["Location"])
        self.assertEqual(status, 200)
        self.assertIn(b'<span class="k">def</span>', body)
        self.assertIn(b"&lt;script&gt;", body)
        self.assertNotIn(b"<script>alert", body)

    def test_raw_view(self):
        status, headers, _ = self.create_form("line1\nline2 <b>raw</b>")
        status, headers2, body = request(
            "GET", self.base() + headers["Location"] + "/raw")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers2["Content-Type"])
        self.assertEqual(body, b"line1\nline2 <b>raw</b>")

    def test_empty_content_rejected(self):
        status, _, _ = self.create_form("   ")
        self.assertEqual(status, 400)

    def test_recent_list(self):
        status, headers, _ = self.create_form("listed paste")
        location = headers["Location"]
        status, _, body = request("GET", self.base() + "/")
        self.assertIn(location.encode(), body)
        request("POST", self.base() + location + "/delete")
        status, _, body = request("GET", self.base() + "/")
        self.assertNotIn(location.encode(), body)


if __name__ == "__main__":
    unittest.main()

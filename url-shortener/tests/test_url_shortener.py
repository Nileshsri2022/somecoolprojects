"""Tests for url_shortener.py.

Every HTTP test drives a real server on an ephemeral port over real
HTTP (http.client, so 302 responses are observed, not followed).
No port is hard-coded. Run from the project root:

    python3 -m unittest discover -s tests -v
"""

import http.client
import json
import os
import re
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from url_shortener import UrlStore, _key_for, create_server  # noqa: E402

KEY_RE = re.compile(r"^[0-9A-Za-z]{6}$")


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read().decode("utf-8")
        finally:
            conn.close()

    def create(self, url):
        status, _headers, body = self.request(
            "POST", "/",
            body=json.dumps({"url": url}),
            headers={"Content-Type": "application/json"})
        return status, json.loads(body) if status == 201 else body


class TestCreate(ServerTestCase):
    def test_valid_url_returns_201_with_key_and_short_url(self):
        status, data = self.create("https://www.example.com")
        self.assertEqual(status, 201)
        self.assertRegex(data["key"], KEY_RE)
        self.assertEqual(data["long_url"], "https://www.example.com")
        self.assertEqual(data["short_url"],
                         "http://127.0.0.1:%d/%s" % (self.port, data["key"]))

    def test_create_is_idempotent(self):
        status1, data1 = self.create("https://www.example.com/page")
        status2, data2 = self.create("https://www.example.com/page")
        self.assertEqual((status1, status2), (201, 201))
        self.assertEqual(data1["key"], data2["key"])
        self.assertEqual(len(self.server.store), 1)

    def test_different_urls_get_different_keys(self):
        _, data1 = self.create("https://www.example.com/a")
        _, data2 = self.create("https://www.example.com/b")
        self.assertNotEqual(data1["key"], data2["key"])

    def test_missing_url_field(self):
        status, _headers, body = self.request(
            "POST", "/",
            body=json.dumps({"wrong key": "https://www.example.com"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(body, "Missing field: url")

    def test_malformed_json(self):
        status, _headers, body = self.request(
            "POST", "/",
            body="{not json",
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertTrue(body.startswith("Invalid JSON"))

    def test_non_object_json(self):
        status, _headers, _body = self.request(
            "POST", "/",
            body="[1, 2]",
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_non_string_url(self):
        status, _headers, _body = self.request(
            "POST", "/",
            body=json.dumps({"url": 123}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_empty_url(self):
        status, _headers, _body = self.request(
            "POST", "/",
            body=json.dumps({"url": ""}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_url_without_scheme_or_host(self):
        status, _headers, _body = self.request(
            "POST", "/",
            body=json.dumps({"url": "notaurl"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_non_http_scheme(self):
        status, _headers, _body = self.request(
            "POST", "/",
            body=json.dumps({"url": "ftp://example.com/file"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)


class TestRedirect(ServerTestCase):
    def test_known_key_redirects_302_with_location(self):
        _, data = self.create("https://www.example.com/target")
        status, headers, body = self.request("GET", "/" + data["key"])
        self.assertEqual(status, 302)
        # http.client lowercases? No — it preserves case; check both.
        location = headers.get("Location") or headers.get("location")
        self.assertEqual(location, "https://www.example.com/target")
        self.assertEqual(body, "")

    def test_unknown_key_404(self):
        status, _headers, body = self.request("GET", "/nosuchkey")
        self.assertEqual(status, 404)
        self.assertEqual(body, "URL not found")

    def test_root_get_404(self):
        status, _headers, body = self.request("GET", "/")
        self.assertEqual(status, 404)
        self.assertEqual(body, "URL not found")

    def test_short_url_from_create_response_redirects(self):
        _, data = self.create("https://www.example.com/follow")
        path = data["short_url"].split("127.0.0.1:%d" % self.port, 1)[1]
        status, headers, _body = self.request("GET", path)
        self.assertEqual(status, 302)
        location = headers.get("Location") or headers.get("location")
        self.assertEqual(location, "https://www.example.com/follow")


class TestDelete(ServerTestCase):
    def test_delete_existing_then_get_404(self):
        _, data = self.create("https://www.example.com/gone")
        status, _headers, body = self.request("DELETE", "/" + data["key"])
        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        status, _headers, body = self.request("GET", "/" + data["key"])
        self.assertEqual(status, 404)
        self.assertEqual(body, "URL not found")

    def test_delete_unknown_is_noop(self):
        _, data = self.create("https://www.example.com/stays")
        status, _headers, body = self.request("DELETE", "/nosuchkey")
        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        status, _headers, _body = self.request("GET", "/" + data["key"])
        self.assertEqual(status, 302)

    def test_deleted_url_can_be_recreated(self):
        _, data = self.create("https://www.example.com/back")
        self.request("DELETE", "/" + data["key"])
        status, data2 = self.create("https://www.example.com/back")
        self.assertEqual(status, 201)
        self.assertEqual(data2["key"], data["key"])
        status, _headers, _body = self.request("GET", "/" + data2["key"])
        self.assertEqual(status, 302)


class TestKeyGeneration(unittest.TestCase):
    def test_same_input_same_key_different_input_different_key(self):
        self.assertEqual(_key_for("https://a.example"),
                         _key_for("https://a.example"))
        self.assertNotEqual(_key_for("https://a.example"),
                            _key_for("https://b.example"))

    def test_key_format(self):
        self.assertRegex(_key_for("https://www.example.com"), KEY_RE)

    def test_forced_collision_gets_distinct_working_key(self):
        store = UrlStore()
        new_url = "https://www.example.com/collision"
        taken_key = _key_for(new_url)
        # Pre-seed the key the new URL would naturally hash to.
        store.by_key[taken_key] = "https://other.example/"
        store.by_url["https://other.example/"] = taken_key
        key = store.create(new_url)
        self.assertNotEqual(key, taken_key)
        self.assertEqual(store.lookup(key), new_url)
        self.assertEqual(store.lookup(taken_key), "https://other.example/")


if __name__ == "__main__":
    unittest.main()

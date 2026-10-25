"""Live-server tests for web_server.py.

A real ThreadingHTTPServer on an OS-assigned ephemeral port (port 0),
with real HTTP requests via http.client. No hard-coded ports.
"""

import http.client
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web_server import create_server  # noqa: E402

INDEX = b"<html><body>Hello index</body></html>\n"
CSS = b"body { color: red; }\n"
JS = b"console.log('hi');\n"
JSON = b'{"ok": true}\n'
TEXT = b"hello world\n"
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 16
PAGE = b"<html><body>sub page</body></html>\n"


class WebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = tempfile.TemporaryDirectory()
        cls.outside_dir = tempfile.TemporaryDirectory()
        root = Path(cls.root_dir.name)
        (root / "index.html").write_bytes(INDEX)
        (root / "style.css").write_bytes(CSS)
        (root / "app.js").write_bytes(JS)
        (root / "data.json").write_bytes(JSON)
        (root / "hello.txt").write_bytes(TEXT)
        (root / "hello world.txt").write_bytes(b"spaced\n")
        (root / "pic.png").write_bytes(PNG)
        (root / "unknown.foobar123").write_bytes(b"mystery\n")
        (root / "sub").mkdir()
        (root / "sub" / "page.html").write_bytes(PAGE)
        outside = Path(cls.outside_dir.name) / "outside.txt"
        outside.write_bytes(b"secret\n")
        # Symlink inside the root pointing outside it.
        os.symlink(outside, root / "link-outside.txt")

        cls.server = create_server("127.0.0.1", 0, cls.root_dir.name)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.root_dir.cleanup()
        cls.outside_dir.cleanup()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_get_index_at_root(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, INDEX)
        self.assertIn("text/html", headers["Content-Type"])

    def test_get_html_file(self):
        status, _headers, body = self.request("GET", "/index.html")
        self.assertEqual(status, 200)
        self.assertEqual(body, INDEX)

    def test_get_css_content_type(self):
        status, headers, body = self.request("GET", "/style.css")
        self.assertEqual(status, 200)
        self.assertEqual(body, CSS)
        self.assertIn("text/css", headers["Content-Type"])

    def test_get_js_content_type(self):
        status, headers, _body = self.request("GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertTrue(
            "javascript" in headers["Content-Type"],
            headers["Content-Type"])

    def test_get_json_content_type(self):
        status, headers, body = self.request("GET", "/data.json")
        self.assertEqual(status, 200)
        self.assertEqual(body, JSON)
        self.assertIn("application/json", headers["Content-Type"])

    def test_get_text_content_type(self):
        status, headers, body = self.request("GET", "/hello.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, TEXT)
        self.assertIn("text/plain", headers["Content-Type"])

    def test_get_binary_png(self):
        status, headers, body = self.request("GET", "/pic.png")
        self.assertEqual(status, 200)
        self.assertEqual(body, PNG)
        self.assertIn("image/png", headers["Content-Type"])

    def test_get_subdirectory_file(self):
        status, _headers, body = self.request("GET", "/sub/page.html")
        self.assertEqual(status, 200)
        self.assertEqual(body, PAGE)

    def test_get_directory_without_index_404(self):
        status, _headers, _body = self.request("GET", "/sub/")
        self.assertEqual(status, 404)

    def test_get_missing_404(self):
        status, _headers, _body = self.request("GET", "/nope.html")
        self.assertEqual(status, 404)

    def test_query_string_ignored(self):
        status, _headers, body = self.request("GET", "/hello.txt?v=1")
        self.assertEqual(status, 200)
        self.assertEqual(body, TEXT)

    def test_percent_encoded_path(self):
        status, _headers, body = self.request("GET", "/hello%20world.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"spaced\n")

    def test_head_same_headers_no_body(self):
        status, headers, body = self.request("HEAD", "/hello.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["Content-Length"]), len(TEXT))

    def test_head_missing_404(self):
        status, _headers, body = self.request("HEAD", "/nope.html")
        self.assertEqual(status, 404)
        self.assertEqual(body, b"")

    def test_post_405(self):
        status, headers, _body = self.request("POST", "/hello.txt", body=b"x")
        self.assertEqual(status, 405)
        self.assertIn("GET", headers.get("Allow", ""))

    def test_traversal_dotdot_403(self):
        status, _headers, _body = self.request("GET", "/../outside.txt")
        self.assertEqual(status, 403)

    def test_traversal_encoded_403(self):
        status, _headers, _body = self.request("GET", "/%2e%2e/outside.txt")
        self.assertEqual(status, 403)

    def test_symlink_escape_403(self):
        status, _headers, _body = self.request("GET", "/link-outside.txt")
        self.assertEqual(status, 403)

    def test_unknown_extension_octet_stream(self):
        status, headers, body = self.request("GET", "/unknown.foobar123")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"mystery\n")
        self.assertEqual(headers["Content-Type"], "application/octet-stream")

    def test_content_length_matches_body(self):
        status, headers, body = self.request("GET", "/hello.txt")
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(body))


if __name__ == "__main__":
    unittest.main()

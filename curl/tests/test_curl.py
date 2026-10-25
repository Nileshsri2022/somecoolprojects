"""Tests for curl.py — all against a local HTTP server, never the net."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import curl as cc

CURL_PY = os.path.join(os.path.dirname(__file__), "..", "curl.py")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _echo(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        payload = json.dumps({
            "method": self.command, "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send(self, status, body, headers=()):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _route(self):
        routes = {
            "/redirect": (302, "", [("Location", "/get")]),
            "/redirect-relative": (302, "", [("Location", "get")]),
            "/redirect-post": (302, "", [("Location", "/get")]),
            "/redirect-307": (307, "", [("Location", "/post")]),
            "/redirect-loop": (302, "", [("Location", "/redirect-loop")]),
            "/status/404": (404, "not here", []),
            "/status/500": (500, "boom", []),
        }
        if self.path in routes:
            status, body, headers = routes[self.path]
            # Drain any request body so the connection stays usable.
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self._send(status, body, headers)
            return True
        return False

    def do_GET(self):
        if self._route():
            return
        if self.path == "/chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in (b"hello ", b"chunked ", b"world"):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.write(b"0\r\n\r\n")
        else:
            self._echo()

    def _echo_or_route(self):
        if not self._route():
            self._echo()

    do_DELETE = _echo_or_route
    do_POST = _echo_or_route
    do_PUT = _echo_or_route
    do_PATCH = _echo_or_route

    def do_HEAD(self):
        self._echo()  # _echo suppresses the body for HEAD


def run_cli(*args):
    return subprocess.run(
        [sys.executable, CURL_PY, *args],
        capture_output=True, timeout=30)


class CurlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def echo(self, resp):
        return json.loads(resp.body.decode())

    # --- URL parsing (Step 1) ---
    def test_parse_defaults_and_query(self):
        p = cc.parse_url("http://example.com/foo?x=1")
        self.assertEqual((p.scheme, p.host, p.port, p.target),
                         ("http", "example.com", 80, "/foo?x=1"))
        self.assertEqual(p.host_header, "example.com")

    def test_parse_https_default_port_and_fragment_dropped(self):
        p = cc.parse_url("https://example.com:443/a#b")
        self.assertEqual((p.port, p.target), (443, "/a"))

    def test_parse_missing_path_and_nondefault_port(self):
        p = cc.parse_url("http://example.com:8080")
        self.assertEqual(p.target, "/")
        self.assertEqual(p.host_header, "example.com:8080")

    def test_parse_errors(self):
        for bad in ("example.com/x", "ftp://example.com/", "http:///x",
                    "http://example.com:notaport/"):
            with self.assertRaises(cc.CurlError) as ctx:
                cc.parse_url(bad)
            self.assertEqual(ctx.exception.code, 3)

    # --- headers (Steps 1/2/5) ---
    def test_default_headers(self):
        p = cc.parse_url(self.url("/get"))
        headers = dict(cc.build_headers(p, None, []))
        self.assertEqual(headers["Host"], "127.0.0.1:%d" % self.port)
        self.assertEqual(headers["Accept"], "*/*")
        self.assertEqual(headers["Connection"], "close")
        self.assertNotIn("Content-Length", headers)

    def test_user_header_replaces_default_and_content_length(self):
        p = cc.parse_url(self.url("/get"))
        headers = cc.build_headers(p, b"abc",
                                   [("Accept", "application/json")])
        names = [n for n, _ in headers]
        self.assertEqual(names.count("Accept"), 1)
        self.assertEqual(dict(headers)["Accept"], "application/json")
        self.assertEqual(dict(headers)["Content-Length"], "3")

    def test_user_content_length_not_duplicated(self):
        p = cc.parse_url(self.url("/get"))
        headers = cc.build_headers(p, b"abc", [("Content-Length", "3")])
        self.assertEqual([n for n, _ in headers].count("Content-Length"), 1)

    def test_bad_header_no_colon(self):
        with self.assertRaises(cc.CurlError) as ctx:
            cc.parse_header("NoColonHere")
        self.assertEqual(ctx.exception.code, 3)

    # --- methods and bodies (Steps 2/4/5/6, Going Further HEAD/PATCH) ---
    def test_get(self):
        resp = cc.request(self.url("/get"))
        self.assertEqual(resp.status, 200)
        self.assertEqual(self.echo(resp)["method"], "GET")

    def test_delete_put_patch(self):
        for method, path in (("DELETE", "/delete"), ("PUT", "/put"),
                             ("PATCH", "/patch")):
            with self.subTest(method=method):
                resp = cc.request(self.url(path), method=method)
                self.assertEqual(self.echo(resp)["method"], method)

    def test_post_json_arrives_intact(self):
        data = '{"key": "value"}'
        resp = cc.request(self.url("/post"), method="POST", data=data,
                          extra_headers=[("Content-Type", "application/json")])
        echoed = self.echo(resp)
        self.assertEqual(echoed["body"], data)
        self.assertEqual(echoed["headers"]["Content-Type"], "application/json")
        self.assertEqual(echoed["headers"]["Content-Length"], str(len(data)))

    def test_data_implies_post(self):
        resp = cc.request(self.url("/post"), data="hi")
        self.assertEqual(self.echo(resp)["method"], "POST")

    def test_custom_headers_arrive(self):
        resp = cc.request(self.url("/headers"), method="GET",
                          extra_headers=[("X-Test", "yes")])
        self.assertEqual(self.echo(resp)["headers"]["X-Test"], "yes")

    def test_head_empty_body(self):
        resp = cc.request(self.url("/head"), method="HEAD")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body, b"")

    def test_chunked_body_read_fully(self):
        resp = cc.request(self.url("/chunked"))
        self.assertEqual(resp.body, b"hello chunked world")

    # --- redirects ---
    def test_redirect_not_followed_by_default(self):
        resp = cc.request(self.url("/redirect"))
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.header("Location"), "/get")

    def test_redirect_followed_absolute_and_relative(self):
        for path in ("/redirect", "/redirect-relative"):
            with self.subTest(path=path):
                resp = cc.request(self.url(path), follow_redirects=True)
                self.assertEqual(resp.status, 200)
                self.assertEqual(self.echo(resp)["path"], "/get")

    def test_redirect_post_becomes_get_on_302(self):
        resp = cc.request(self.url("/redirect-post"), method="POST",
                          data="payload", follow_redirects=True)
        echoed = self.echo(resp)
        self.assertEqual(echoed["method"], "GET")
        self.assertEqual(echoed["body"], "")

    def test_redirect_307_keeps_method_and_body(self):
        resp = cc.request(self.url("/redirect-307"), method="POST",
                          data="keepme", follow_redirects=True)
        echoed = self.echo(resp)
        self.assertEqual(echoed["method"], "POST")
        self.assertEqual(echoed["body"], "keepme")

    def test_redirect_loop_hits_limit(self):
        with self.assertRaises(cc.CurlError) as ctx:
            cc.request(self.url("/redirect-loop"), follow_redirects=True,
                       max_redirs=3)
        self.assertEqual(ctx.exception.code, 47)

    # --- CLI ---
    def test_cli_body_only_by_default(self):
        proc = run_cli(self.url("/get"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["method"], "GET")
        self.assertEqual(proc.stderr, b"")

    def test_cli_verbose(self):
        proc = run_cli("-v", self.url("/get"))
        self.assertEqual(proc.returncode, 0)
        self.assertIn(b"> GET /get HTTP/1.1", proc.stderr)
        self.assertIn(b"> Host: 127.0.0.1:", proc.stderr)
        self.assertIn(b"< HTTP/1.1 200", proc.stderr)
        self.assertTrue(proc.stdout.startswith(b"{"))

    def test_cli_include(self):
        proc = run_cli("-i", self.url("/get"))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.startswith(b"HTTP/1.1 200"))
        self.assertIn(b"\r\n\r\n{", proc.stdout)

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            proc = run_cli("-o", path, self.url("/get"))
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, b"")
            with open(path, "rb") as f:
                self.assertEqual(json.loads(f.read())["method"], "GET")

    def test_cli_binary_body_round_trips_via_output(self):
        # Chunked endpoint body is plain bytes; -o must preserve them.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.bin")
            proc = run_cli("-o", path, self.url("/chunked"))
            self.assertEqual(proc.returncode, 0)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"hello chunked world")

    def test_cli_fail_flag(self):
        proc = run_cli("-f", self.url("/status/404"))
        self.assertEqual(proc.returncode, 22)
        self.assertEqual(proc.stdout, b"")
        self.assertIn(b"404", proc.stderr)
        proc = run_cli(self.url("/status/404"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"not here")

    def test_cli_connection_refused(self):
        # Port 1 on localhost is (virtually) never listening.
        proc = run_cli("http://127.0.0.1:1/nope")
        self.assertEqual(proc.returncode, 7)
        self.assertEqual(proc.stdout, b"")
        self.assertIn(b"curl: (7)", proc.stderr)

    def test_cli_usage_errors(self):
        self.assertEqual(run_cli().returncode, 2)
        self.assertEqual(run_cli("--bogus", self.url("/get")).returncode, 2)
        self.assertEqual(run_cli("-H", "NoColon", self.url("/get")).returncode, 3)
        self.assertEqual(run_cli("ftp://example.com/").returncode, 3)
        self.assertEqual(
            run_cli(self.url("/get"), self.url("/get")).returncode, 2)


if __name__ == "__main__":
    unittest.main()

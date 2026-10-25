"""Tests for the HTTP forward proxy. Local servers only, ephemeral ports."""

import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proxy import (  # noqa: E402
    contains_banned_word,
    create_proxy_server,
    is_forbidden_host,
    load_list_file,
    parse_request_target,
    strip_hop_by_hop_headers,
)


class OriginHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    last = {}

    def _record(self, body=b""):
        OriginHandler.last = {
            "method": self.command,
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
        }

    def _send(self, code, body, ctype="text/plain"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("X-Origin", "yes")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        self._record()
        if self.path == "/hello":
            self._send(200, "Hello, proxy!")
        elif self.path == "/secret":
            self._send(200, "this page mentions dummy stuff")
        elif self.path == "/chunked":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"5\r\nhello\r\n6\r\n proxy\r\n0\r\n\r\n")
        else:
            self._send(404, "not here")

    def do_HEAD(self):
        self._record()
        self._send(200, "")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._record(body)
        payload = json.dumps({
            "method": self.command,
            "path": self.path,
            "body": body.decode("utf-8", "replace"),
        })
        self._send(200, payload, "application/json")

    def log_message(self, *args):
        pass


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def raw_request(port, request_bytes, read_all=True):
    """Send raw bytes to the proxy; return (status_line, headers, body)."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        sock.sendall(request_bytes)
        sock.shutdown(socket.SHUT_WR) if False else None
        data = b""
        # Read until the server closes or we have a complete CL body.
        sock.settimeout(10)
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
            head, sep, body = data.partition(b"\r\n\r\n")
            if sep and b"content-length:" in head.lower():
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        n = int(line.split(b":", 1)[1].strip())
                        if len(body) >= n:
                            return (head.split(b"\r\n")[0].decode(),
                                    head.decode(), body[:n])
            if not read_all:
                break
        head, sep, body = data.partition(b"\r\n\r\n")
        return (head.split(b"\r\n")[0].decode() if head else "",
                head.decode() if head else "", body)
    finally:
        sock.close()


class ProxyTestCase(unittest.TestCase):
    forbidden = []
    banned = []

    def setUp(self):
        self.origin = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), OriginHandler)
        start_server(self.origin)
        self.origin_port = self.origin.server_address[1]
        tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".log")
        tmp.close()
        self.log_path = tmp.name
        self.proxy = create_proxy_server(
            "127.0.0.1", 0,
            forbidden_hosts=self.forbidden,
            banned_words=self.banned,
            log_file=self.log_path)
        start_server(self.proxy)
        self.proxy_port = self.proxy.server_address[1]

    def tearDown(self):
        self.proxy.shutdown()
        self.proxy.server_close()
        self.origin.shutdown()
        self.origin.server_close()
        os.unlink(self.log_path)

    def proxy_get(self, url, extra=b""):
        return raw_request(
            self.proxy_port,
            b"GET " + url.encode() + b" HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nConnection: close\r\n\r\n" + extra)


class TestUnit(unittest.TestCase):
    def test_parse_absolute(self):
        host, port, path = parse_request_target(
            "GET", "http://example.com:8080/a/b?x=1", None)
        self.assertEqual((host, port, path), ("example.com", 8080, "/a/b?x=1"))

    def test_parse_absolute_default_port_and_root(self):
        host, port, path = parse_request_target(
            "GET", "http://example.com", None)
        self.assertEqual((host, port, path), ("example.com", 80, "/"))

    def test_parse_origin_form(self):
        host, port, path = parse_request_target(
            "GET", "/ip", "example.com:1234")
        self.assertEqual((host, port, path), ("example.com", 1234, "/ip"))

    def test_parse_connect(self):
        host, port, path = parse_request_target(
            "CONNECT", "example.com:443", None)
        self.assertEqual((host, port, path), ("example.com", 443, None))

    def test_parse_connect_default_port(self):
        _, port, _ = parse_request_target("CONNECT", "example.com", None)
        self.assertEqual(port, 443)

    def test_parse_rejects_https_absolute(self):
        with self.assertRaises(ValueError):
            parse_request_target("GET", "https://example.com/", None)

    def test_parse_rejects_missing_host(self):
        with self.assertRaises(ValueError):
            parse_request_target("GET", "/ip", None)
        with self.assertRaises(ValueError):
            parse_request_target("GET", "http:///ip", None)

    def test_load_list_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("# comment\n\nFacebook.COM\n  example.org  \n")
            name = f.name
        try:
            self.assertEqual(load_list_file(name),
                             ["facebook.com", "example.org"])
        finally:
            os.unlink(name)
        self.assertEqual(load_list_file("/nonexistent/nope.txt"), [])
        self.assertEqual(load_list_file("none"), [])

    def test_is_forbidden(self):
        self.assertTrue(is_forbidden_host("facebook.com", ["facebook.com"]))
        self.assertTrue(is_forbidden_host("www.facebook.com",
                                          ["facebook.com"]))
        self.assertTrue(is_forbidden_host("FACEBOOK.COM", ["facebook.com"]))
        self.assertFalse(is_forbidden_host("notfacebook.com",
                                           ["facebook.com"]))
        self.assertFalse(is_forbidden_host("facebook.com", []))

    def test_contains_banned_word(self):
        self.assertTrue(contains_banned_word(b"a DuMmY word", ["dummy"]))
        self.assertFalse(contains_banned_word(b"clean page", ["dummy"]))
        self.assertFalse(contains_banned_word(b"dummy", []))

    def test_strip_hop_by_hop(self):
        headers = [("Host", "x"), ("Proxy-Connection", "keep-alive"),
                   ("Connection", "X-Custom-Hop"), ("X-Custom-Hop", "1"),
                   ("User-Agent", "t"), ("Keep-Alive", "timeout=5")]
        kept = dict((k.lower(), v) for k, v in
                    strip_hop_by_hop_headers(headers))
        self.assertEqual(set(kept), {"host", "user-agent"})


class TestProxy(ProxyTestCase):
    def test_get_absolute_form(self):
        status, headers, body = self.proxy_get(
            f"http://127.0.0.1:{self.origin_port}/hello")
        self.assertIn("200", status)
        self.assertEqual(body, b"Hello, proxy!")
        self.assertIn("x-origin: yes", headers.lower())

    def test_get_origin_form(self):
        status, _, body = raw_request(
            self.proxy_port,
            (f"GET /hello HTTP/1.1\r\nHost: 127.0.0.1:{self.origin_port}\r\n"
             "Connection: close\r\n\r\n").encode())
        self.assertIn("200", status)
        self.assertEqual(body, b"Hello, proxy!")

    def test_post_body_and_x_forwarded_for(self):
        status, _, body = raw_request(
            self.proxy_port,
            (f"POST http://127.0.0.1:{self.origin_port}/echo HTTP/1.1\r\n"
             f"Host: 127.0.0.1:{self.origin_port}\r\n"
             "Content-Type: text/plain\r\nX-Test: abc\r\n"
             "Content-Length: 5\r\nConnection: close\r\n\r\nhello").encode())
        self.assertIn("200", status)
        echoed = json.loads(body)
        self.assertEqual(echoed["method"], "POST")
        self.assertEqual(echoed["path"], "/echo")  # origin form, rewritten
        self.assertEqual(echoed["body"], "hello")
        last = OriginHandler.last
        self.assertEqual(last["headers"].get("x-test"), "abc")
        self.assertEqual(last["headers"].get("x-forwarded-for"), "127.0.0.1")

    def test_hop_by_hop_not_forwarded(self):
        raw_request(
            self.proxy_port,
            (f"GET http://127.0.0.1:{self.origin_port}/hello HTTP/1.1\r\n"
             f"Host: 127.0.0.1:{self.origin_port}\r\n"
             "Proxy-Connection: Keep-Alive\r\n"
             "Proxy-Authorization: Basic xyz\r\n"
             "Connection: close\r\n\r\n").encode())
        last = OriginHandler.last
        self.assertNotIn("proxy-connection", last["headers"])
        self.assertNotIn("proxy-authorization", last["headers"])

    def test_chunked_origin_response(self):
        status, _, body = self.proxy_get(
            f"http://127.0.0.1:{self.origin_port}/chunked")
        self.assertIn("200", status)
        self.assertEqual(body, b"hello proxy")

    def test_head(self):
        status, headers, body = raw_request(
            self.proxy_port,
            (f"HEAD http://127.0.0.1:{self.origin_port}/hello HTTP/1.1\r\n"
             f"Host: 127.0.0.1:{self.origin_port}\r\n"
             "Connection: close\r\n\r\n").encode())
        self.assertIn("200", status)
        self.assertEqual(body, b"")

    def test_unreachable_origin_502(self):
        status, _, _ = self.proxy_get("http://127.0.0.1:1/hello")
        self.assertIn("502", status)

    def test_malformed_request_400(self):
        status, _, _ = raw_request(self.proxy_port, b"GARBAGE\r\n\r\n")
        self.assertIn("400", status)

    def test_logging(self):
        self.proxy_get(f"http://127.0.0.1:{self.origin_port}/hello")
        with open(self.log_path) as f:
            log = f.read()
        self.assertIn("GET", log)
        self.assertIn("/hello", log)
        self.assertIn("200", log)


class TestForbidden(ProxyTestCase):
    forbidden = ["blocked.example"]

    def test_forbidden_absolute(self):
        # Origin must not be contacted: use a host that is forbidden
        # even though no such origin exists; 403 must come first.
        status, headers, body = self.proxy_get(
            "http://blocked.example/hello")
        self.assertIn("403", status)
        self.assertEqual(body, b"Website not allowed: blocked.example")
        # Correct length for the body actually sent (the page's 34
        # fits its facebook.com example only with a trailing newline).
        self.assertIn(f"content-length: {len(body)}", headers.lower())

    def test_forbidden_subdomain(self):
        status, _, body = self.proxy_get("http://www.blocked.example/")
        self.assertIn("403", status)
        self.assertEqual(body, b"Website not allowed: www.blocked.example")

    def test_forbidden_connect(self):
        sock = socket.create_connection(("127.0.0.1", self.proxy_port),
                                        timeout=10)
        try:
            sock.sendall(b"CONNECT blocked.example:443 HTTP/1.1\r\n"
                         b"Host: blocked.example:443\r\n\r\n")
            data = sock.recv(4096)
        finally:
            sock.close()
        self.assertIn(b"403", data)
        self.assertIn(b"Website not allowed: blocked.example", data)


class TestBanned(ProxyTestCase):
    banned = ["dummy"]

    def test_banned_word_blocked(self):
        status, _, body = self.proxy_get(
            f"http://127.0.0.1:{self.origin_port}/secret")
        self.assertIn("403", status)
        self.assertEqual(body, b"Website content not allowed.")
        self.assertNotIn(b"dummy", body)

    def test_clean_page_passes_with_ban_list(self):
        status, _, body = self.proxy_get(
            f"http://127.0.0.1:{self.origin_port}/hello")
        self.assertIn("200", status)
        self.assertEqual(body, b"Hello, proxy!")


class TestConnect(ProxyTestCase):
    def test_connect_tunnel(self):
        sock = socket.create_connection(("127.0.0.1", self.proxy_port),
                                        timeout=10)
        try:
            sock.sendall(
                f"CONNECT 127.0.0.1:{self.origin_port} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.origin_port}\r\n\r\n".encode())
            reply = sock.recv(4096)
            self.assertIn(b"200", reply)
            # Now speak plain HTTP through the tunnel.
            sock.sendall(b"GET /hello HTTP/1.1\r\nHost: x\r\n"
                         b"Connection: close\r\n\r\n")
            data = b""
            sock.settimeout(10)
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        finally:
            sock.close()
        self.assertIn(b"200", data)
        self.assertIn(b"Hello, proxy!", data)


if __name__ == "__main__":
    unittest.main()

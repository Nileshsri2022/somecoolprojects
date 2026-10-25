"""URL shortener service (Coding Challenges #12).

Python 3 standard library only. One HTTP service:

- POST /   {"url": "<long url>"} -> 201 {"key", "long_url", "short_url"}
  (idempotent: the same URL always returns the same key)
- GET /<key> -> 302 Found with a Location header, or 404 "URL not found"
- DELETE /<key> -> 200 with an empty body (no-op for an unknown key)

Storage is in-memory. Run: python3 url_shortener.py [port] (default 8080).
"""

import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
KEY_LENGTH = 6


def _key_for(url, salt=0):
    """Deterministic 6-char base62 key from SHA-256 of the URL.

    A non-zero salt re-hashes a salted input, which is how key
    collisions with a different URL are resolved (see UrlStore.create).
    """
    data = url if salt == 0 else "%s:%d" % (url, salt)
    number = int.from_bytes(hashlib.sha256(data.encode("utf-8")).digest()[:8], "big")
    chars = []
    for _ in range(KEY_LENGTH):
        chars.append(ALPHABET[number % len(ALPHABET)])
        number //= len(ALPHABET)
    return "".join(reversed(chars))


class UrlStore:
    """In-memory key <-> URL store with idempotent create."""

    def __init__(self):
        self._lock = threading.Lock()
        self.by_key = {}
        self.by_url = {}

    def __len__(self):
        with self._lock:
            return len(self.by_key)

    def create(self, url):
        """Return the key for url, creating a mapping if needed."""
        with self._lock:
            if url in self.by_url:
                return self.by_url[url]
            salt = 0
            while True:
                key = _key_for(url, salt)
                existing = self.by_key.get(key)
                if existing is None or existing == url:
                    break
                salt += 1
            self.by_key[key] = url
            self.by_url[url] = key
            return key

    def lookup(self, key):
        with self._lock:
            return self.by_key.get(key)

    def delete(self, key):
        with self._lock:
            url = self.by_key.pop(key, None)
            if url is not None:
                self.by_url.pop(url, None)
            return url is not None


def _validate_url(value):
    """Return an error string for a bad url value, else None."""
    if not isinstance(value, str) or not value.strip():
        return "Invalid URL: url must be a non-empty string"
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "Invalid URL: %r is not an http(s) URL" % value
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test/server output clean
        pass

    # -- helpers -----------------------------------------------------
    def _send(self, status, body=b"", content_type="text/plain", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _key_from_path(self):
        return urlparse(self.path).path.lstrip("/")

    # -- endpoints ---------------------------------------------------
    def do_POST(self):
        if urlparse(self.path).path != "/":
            self._send(404, "URL not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        try:
            payload = json.loads(self.rfile.read(length) if length > 0 else b"")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, "Invalid JSON")
            return
        if not isinstance(payload, dict):
            self._send(400, "Invalid JSON: expected an object")
            return
        if "url" not in payload:
            self._send(400, "Missing field: url")
            return
        error = _validate_url(payload["url"])
        if error is not None:
            self._send(400, error)
            return
        url = payload["url"]
        key = self.server.store.create(url)
        host = self.headers.get("Host", "localhost")
        body = json.dumps({
            "key": key,
            "long_url": url,
            "short_url": "http://%s/%s" % (host, key),
        })
        self._send(201, body, content_type="application/json")

    def do_GET(self):
        url = self.server.store.lookup(self._key_from_path())
        if url is None:
            self._send(404, "URL not found")
            return
        self._send(302, b"", extra={"Location": url})

    def do_DELETE(self):
        self.server.store.delete(self._key_from_path())
        self._send(200, b"")


class ShortenerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.store = UrlStore()


def create_server(port, host="127.0.0.1"):
    """Build (but do not start) a server; port 0 picks an ephemeral port."""
    return ShortenerServer((host, port))


def main(argv):
    try:
        port = int(argv[1]) if len(argv) > 1 else 8080
    except ValueError:
        print("usage: python3 url_shortener.py [port]", file=sys.stderr)
        return 2
    server = create_server(port, host="")
    print("Serving on http://localhost:%d" % server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

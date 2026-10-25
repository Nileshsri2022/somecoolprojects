#!/usr/bin/env python3
"""Minimal static-file HTTP server (Coding Challenges #11).

Python 3 standard library only. Serves files from one root directory:

  python3 web_server.py [--host HOST] [--port PORT] [--directory DIR]

Defaults: host 127.0.0.1, port 8080, directory = current directory.

Behaviour: GET serves files, HEAD returns the same headers with no
body, directories serve index.html or 404, paths escaping the root
return 403, missing files 404, other methods 405. See docs/SPEC.md.
"""

import argparse
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def _is_within(path, root):
    """True if resolved `path` is inside resolved `root` (or equal)."""
    try:
        return path.is_relative_to(root)
    except AttributeError:  # Python < 3.9 fallback
        return os.path.commonpath([str(path), str(root)]) == str(root)


def _content_type(path):
    """Content type for a file path; text/* gains a utf-8 charset."""
    ctype, _ = mimetypes.guess_type(str(path))
    if ctype is None:
        return "application/octet-stream"
    if ctype.startswith("text/"):
        return ctype + "; charset=utf-8"
    return ctype


def make_handler(root):
    """Return a request-handler class serving files under `root`."""
    root = Path(root).resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "web_server/1.0"

        def do_GET(self):
            self._serve(head_only=False)

        def do_HEAD(self):
            self._serve(head_only=True)

        def do_POST(self):
            self._method_not_allowed()

        def do_PUT(self):
            self._method_not_allowed()

        def do_PATCH(self):
            self._method_not_allowed()

        def do_DELETE(self):
            self._method_not_allowed()

        def do_OPTIONS(self):
            self._method_not_allowed()

        def _send(self, status, body=b"", content_type=None,
                    write_body=True):
            self.send_response(status)
            if content_type is not None:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body and write_body:
                self.wfile.write(body)

        def _method_not_allowed(self):
            # Drain any request body first, else it is misparsed as the
            # next request on a keep-alive connection.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > 0:
                self.rfile.read(length)
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            body = b"405 Method Not Allowed\n"
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve(self, head_only):
            # Strip query/fragment, then percent-decode the path.
            raw_path = urlsplit(self.path).path
            rel = unquote(raw_path).lstrip("/")
            target = (root / rel).resolve() if rel else root
            if not _is_within(target, root):
                body = b"403 Forbidden\n"
                self._send(403, body, "text/plain; charset=utf-8",
                           write_body=not head_only)
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                body = b"404 Not Found\n"
                self._send(404, body, "text/plain; charset=utf-8",
                           write_body=not head_only)
                return
            data = target.read_bytes()
            # HEAD: same headers (including full Content-Length), no body.
            self.send_response(200)
            self.send_header("Content-Type", _content_type(target))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head_only:
                self.wfile.write(data)

        def log_message(self, fmt, *args):  # keep default stderr logging
            sys.stderr.write(
                "%s - %s\n" % (self.address_string(), fmt % args)
            )

    return Handler


def create_server(host, port, root):
    """Create (but do not start) a threaded server for `root`."""
    return ThreadingHTTPServer((host, port), make_handler(root))


def serve(host, port, root):
    """Serve forever until interrupted."""
    server = create_server(host, port, root)
    actual = server.server_address[1]
    print(f"Serving {Path(root).resolve()} on http://{host}:{actual}/",
          file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Serve static files over HTTP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--directory", default=".")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    serve(args.host, args.port, args.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

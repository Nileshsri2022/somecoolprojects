"""Pastebin: a tiny stdlib-only pastebin server.

Usage:  python3 pastebin.py [--host 127.0.0.1] [--port 8080] [--store FILE]

Routes (see docs/SPEC.md):
  GET  /                home page: form + recent pastes
  POST /                create a paste (form -> 303, JSON -> 201)
  GET  /<id>            snippet page
  GET  /<id>/raw        exact content, text/plain
  GET  /<id>/delete     delete confirmation page
  POST /<id>/delete     delete, redirect home

Storage is an in-memory dict, optionally persisted to a JSON file
(--store). Expiry is checked lazily on every access.
"""

import argparse
import html
import json
import re
import secrets
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ID_ALPHABET = string.ascii_letters + string.digits
ID_LENGTH = 7

# Form expiry values (seconds); "never" means no expiry.
EXPIRY_OPTIONS = [
    ("never", "Never"),
    ("600", "10 minutes"),
    ("3600", "1 hour"),
    ("86400", "1 day"),
    ("604800", "1 week"),
]
LANGUAGES = ["plain", "python", "javascript", "html", "sql"]

PYTHON_KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
}

# Tokenizer for Python highlighting: comments, strings, words.
_TOKEN_RE = re.compile(
    r"(?P<comment>#[^\n]*)"
    r"|(?P<string>\"\"\"(?:\\.|[^\\])*?\"\"\"|'''(?:\\.|[^\\])*?'''"
    r"|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')"
    r"|(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
)


def highlight_python(content):
    """Escape content and wrap Python keywords/strings/comments in spans."""
    out = []
    pos = 0
    for match in _TOKEN_RE.finditer(content):
        out.append(html.escape(content[pos:match.start()]))
        text = match.group()
        if match.lastgroup == "comment":
            out.append('<span class="c">%s</span>' % html.escape(text))
        elif match.lastgroup == "string":
            out.append('<span class="s">%s</span>' % html.escape(text))
        elif text in PYTHON_KEYWORDS:
            out.append('<span class="k">%s</span>' % html.escape(text))
        else:
            out.append(html.escape(text))
        pos = match.end()
    out.append(html.escape(content[pos:]))
    return "".join(out)


def render_body(content):
    """Render a snippet body: <pre> + escaped text, or raw if empty."""
    return ("<pre>%s</pre>" % content) if content else "<p><em>(empty)</em></p>"


def page(title, body):
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>%s</title><style>"
        "body{font-family:sans-serif;max-width:800px;margin:2em auto;padding:0 1em}"
        "textarea{width:100%%;height:16em}pre{background:#f4f4f4;padding:1em;"
        "white-space:pre-wrap;word-wrap:break-word}"
        ".k{color:#007020;font-weight:bold}.s{color:#4070a0}.c{color:#60a0b0;"
        "font-style:italic}</style></head><body>%s</body></html>"
        % (html.escape(title), body)
    )


class PasteStore:
    """Thread-safe id -> paste dict, optionally backed by a JSON file."""

    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        self.pastes = {}
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.pastes = data
            except (OSError, ValueError):
                self.pastes = {}

    def _save_locked(self):
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.pastes, f)
            import os
            os.replace(tmp, self.path)

    def create(self, content, language, expiry_seconds):
        with self.lock:
            paste_id = "".join(secrets.choice(ID_ALPHABET)
                               for _ in range(ID_LENGTH))
            while paste_id in self.pastes:
                paste_id = "".join(secrets.choice(ID_ALPHABET)
                                   for _ in range(ID_LENGTH))
            now = time.time()
            self.pastes[paste_id] = {
                "content": content,
                "language": language,
                "created_at": now,
                "expires_at": (now + expiry_seconds
                               if expiry_seconds is not None else None),
            }
            self._save_locked()
            return paste_id

    def get(self, paste_id):
        """Return the paste, or None if unknown/deleted/expired.

        Expired pastes are removed (lazy expiry) so they never resurface.
        """
        with self.lock:
            paste = self.pastes.get(paste_id)
            if paste is None:
                return None
            expires_at = paste.get("expires_at")
            if expires_at is not None and time.time() >= expires_at:
                del self.pastes[paste_id]
                self._save_locked()
                return None
            return paste

    def delete(self, paste_id):
        """Delete if present and live; return True on success."""
        if self.get(paste_id) is None:
            return False
        with self.lock:
            removed = self.pastes.pop(paste_id, None) is not None
            if removed:
                self._save_locked()
            return removed

    def recent(self):
        """Live pastes, newest first (expired ones are purged)."""
        with self.lock:
            now = time.time()
            live = []
            expired = []
            for paste_id, paste in self.pastes.items():
                expires_at = paste.get("expires_at")
                if expires_at is not None and now >= expires_at:
                    expired.append(paste_id)
                else:
                    live.append((paste["created_at"], paste_id))
            for paste_id in expired:
                del self.pastes[paste_id]
            if expired:
                self._save_locked()
            live.sort(reverse=True)
            return [paste_id for _, paste_id in live]


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # -- helpers -------------------------------------------------
        def log_message(self, *args):  # keep stdout clean
            pass

        def _send(self, status, body, content_type="text/html; charset=utf-8"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location):
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _not_found(self):
            self._send(404, page("Not found",
                                 "<h1>404 Not Found</h1>"
                                 "<p>This paste does not exist, was deleted, "
                                 "or has expired.</p><p><a href='/'>New paste"
                                 "</a></p>"))

        def _home(self):
            options = "".join(
                '<option value="%s">%s</option>' % (v, label)
                for v, label in EXPIRY_OPTIONS)
            langs = "".join(
                '<option value="%s">%s</option>' % (lang, lang)
                for lang in LANGUAGES)
            recent = store.recent()
            if recent:
                items = "".join(
                    '<li><a href="/%s">/%s</a></li>' % (pid, pid)
                    for pid in recent)
                recent_html = "<h2>Recent pastes</h2><ul>%s</ul>" % items
            else:
                recent_html = ""
            body = (
                "<h1>Pastebin</h1>"
                "<form method='post' action='/'>"
                "<p><textarea name='content' placeholder='Paste text here…'"
                " required></textarea></p>"
                "<p>Expiry: <select name='expiry'>%s</select> "
                "Language: <select name='language'>%s</select> "
                "<input type='submit' value='Create paste'></p>"
                "</form>%s" % (options, langs, recent_html))
            self._send(200, page("Pastebin", body))

        # -- routing -------------------------------------------------
        def do_GET(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if not parts:
                self._home()
                return
            paste_id = parts[0]
            if len(parts) == 2 and parts[1] == "raw":
                paste = store.get(paste_id)
                if paste is None:
                    self._not_found()
                else:
                    self._send(200, paste["content"], "text/plain; charset=utf-8")
                return
            if len(parts) == 2 and parts[1] == "delete":
                paste = store.get(paste_id)
                if paste is None:
                    self._not_found()
                else:
                    body = (
                        "<h1>Delete paste?</h1>"
                        "<p>Are you sure you want to delete "
                        "<a href='/%s'>/%s</a>? This cannot be undone.</p>"
                        "<form method='post' action='/%s/delete'>"
                        "<input type='submit' value='Yes, delete it'>"
                        "</form><p><a href='/%s'>Cancel</a></p>"
                        % (paste_id, paste_id, paste_id, paste_id))
                    self._send(200, page("Delete paste", body))
                return
            if len(parts) == 1:
                paste = store.get(paste_id)
                if paste is None:
                    self._not_found()
                    return
                if paste["language"] == "python":
                    rendered = highlight_python(paste["content"])
                    snippet = "<pre>%s</pre>" % rendered
                else:
                    snippet = render_body(html.escape(paste["content"]))
                body = (
                    "<h1>Paste /%s</h1><p>Language: %s</p>%s"
                    "<p><a href='/%s/raw'>Raw</a> | "
                    "<a href='/%s/delete'>Delete</a> | "
                    "<a href='/'>New paste</a></p>"
                    % (paste_id, html.escape(paste["language"]), snippet,
                       paste_id, paste_id))
                self._send(200, page("Paste " + paste_id, body))
                return
            self._not_found()

        def do_POST(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 2 and parts[1] == "delete":
                if store.delete(parts[0]):
                    self._redirect("/")
                else:
                    self._not_found()
                return
            if parts:
                self._not_found()
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            content_type = self.headers.get("Content-Type") or ""
            if "application/json" in content_type:
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError:
                    self._send(400, page("Bad request",
                                         "<p>Invalid JSON body.</p>"))
                    return
                content = data.get("content", "")
                language = data.get("language") or "plain"
                expiry = data.get("expiry_seconds")
            else:
                fields = parse_qs(raw.decode("utf-8", "replace"))
                content = fields.get("content", [""])[0]
                language = fields.get("language", ["plain"])[0]
                expiry_raw = fields.get("expiry", ["never"])[0]
                if expiry_raw == "never":
                    expiry = None
                else:
                    parsed = _to_int(expiry_raw)
                    expiry = parsed if parsed is not None else "invalid"
            if language not in LANGUAGES:
                language = "plain"
            if not isinstance(content, str) or not content.strip():
                self._send(400, page("Bad request",
                                     "<p>Content must not be empty.</p>"))
                return
            if expiry is not None and not isinstance(expiry, (int, float)):
                self._send(400, page("Bad request",
                                     "<p>Invalid expiry.</p>"))
                return
            paste_id = store.create(content, language, expiry)
            if "application/json" in content_type:
                self._send(201, json.dumps({"id": paste_id,
                                            "url": "/" + paste_id}),
                           "application/json")
            else:
                self._redirect("/" + paste_id)

    return Handler


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def make_server(host="127.0.0.1", port=8080, store_path=None):
    store = PasteStore(store_path)
    return ThreadingHTTPServer((host, port), make_handler(store))


def main():
    parser = argparse.ArgumentParser(description="Tiny stdlib pastebin.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--store", default=None,
                        help="optional JSON file for persistence")
    args = parser.parse_args()
    server = make_server(args.host, args.port, args.store)
    print("Pastebin at http://%s:%d/ (Ctrl-C to stop)"
          % (args.host, server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""cclsp — a small Language Server implementing the Language Server
Protocol (LSP) over stdio, for the Coding Challenges "Build Your Own
Language Server" challenge (see docs/SPEC.md).

Implemented: initialize/initialized, textDocument/didOpen,
didChange (Full sync), didClose, didSave, textDocument/completion,
shutdown/exit, and textDocument/publishDiagnostics for two fixed
phrases ("Watching a Video", "Coding Challenges").

Protocol bytes go to stdout ONLY; all logging goes to stderr (or
--log-file). Python 3 standard library only.

Usage:
    python3 lsp_server.py [--log-file PATH]
"""

import argparse
import io
import json
import re
import sys

SERVER_NAME = "cclsp"
SERVER_VERSION = "0.1.0"

# phrase -> (message, severity)  -- severity: 2 = Warning, 3 = Information
PHRASES = [
    ("Watching a Video",
     "It's much better to learn by doing! Try Coding Challenges instead.",
     2),
    ("Coding Challenges", "This is the way!", 3),
]

COMPLETION_LABEL = "CodingChallenges"
_WORD_RE = re.compile(r"[A-Za-z0-9_]*$")


def log(message, stream):
    """One log line to the log stream (never stdout)."""
    print("[%s] %s" % (SERVER_NAME, message), file=stream, flush=True)


def encode_message(message):
    """Frame a dict as LSP base-protocol bytes."""
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = ("Content-Length: %d\r\n\r\n" % len(body)).encode("ascii")
    return header + body


def read_message(stream):
    """Read one framed message from a binary stream.

    Returns the decoded dict, or None on clean EOF. Raises ValueError
    on a header block without Content-Length or on a truncated body;
    a body that is not valid JSON is returned as a sentinel so the
    caller can log and skip it without killing the server.
    """
    headers = {}
    while True:
        line = stream.readline()
        if line in (b"", b"\r\n", b"\n"):
            break
        if line == b"":
            break
        if b":" not in line:
            continue
        name, value = line.decode("ascii", "replace").split(":", 1)
        headers[name.strip().lower()] = value.strip()
    if not headers and line == b"":
        return None  # EOF before any header
    if "content-length" not in headers:
        raise ValueError("missing Content-Length header")
    length = int(headers["content-length"])
    body = stream.read(length)
    if len(body) < length:
        raise ValueError("truncated message body")
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"__invalid_json__": True}


def analyze_document(text):
    """Diagnostics for every occurrence of the fixed phrases.

    Returns a list of LSP Diagnostic dicts. Ranges are 0-based
    (line, character) in Python string indices; see docs/DESIGN.md
    for the UTF-16 limitation on non-ASCII text.
    """
    diagnostics = []
    for lineno, line in enumerate(text.split("\n")):
        for phrase, message, severity in PHRASES:
            start = 0
            while True:
                idx = line.find(phrase, start)
                if idx < 0:
                    break
                diagnostics.append({
                    "range": {
                        "start": {"line": lineno, "character": idx},
                        "end": {"line": lineno,
                                "character": idx + len(phrase)},
                    },
                    "severity": severity,
                    "source": SERVER_NAME,
                    "message": message,
                })
                start = idx + len(phrase)
    return diagnostics


def word_fragment_at(text, line_no, character):
    """Word fragment immediately before (line_no, character)."""
    lines = text.split("\n")
    if line_no < 0 or line_no >= len(lines):
        return ""
    line = lines[line_no][:max(0, character)]
    match = _WORD_RE.search(line)
    return match.group(0) if match else ""


def completion_items(text, line_no, character):
    """Completion items for a cursor position, or [] if none apply."""
    fragment = word_fragment_at(text, line_no, character)
    if fragment and not COMPLETION_LABEL.startswith(fragment):
        return []
    return [{
        "label": COMPLETION_LABEL,
        "detail": "Coding Challenges \u2014 learn by doing",
        "documentation": "Try Coding Challenges instead of watching videos.",
        "insertText": COMPLETION_LABEL,
    }]


class LanguageServer:
    """One stdio LSP session. rfile/wfile are binary streams."""

    def __init__(self, rfile, wfile, log_stream):
        self.rfile = rfile
        self.wfile = wfile
        self.log_stream = log_stream
        self.documents = {}  # uri -> {languageId, version, text}
        self.shutdown_requested = False
        self.running = True
        self.exit_code = 0

    # -- transport -------------------------------------------------
    def send(self, message):
        self.wfile.write(encode_message(message))
        self.wfile.flush()

    def send_response(self, msg_id, result):
        self.send({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def send_error(self, msg_id, code, message):
        self.send({"jsonrpc": "2.0", "id": msg_id,
                   "error": {"code": code, "message": message}})

    def send_notification(self, method, params):
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    # -- main loop -------------------------------------------------
    def run(self):
        log("CC LSP is running", self.log_stream)
        while self.running:
            try:
                message = read_message(self.rfile)
            except ValueError as exc:
                log("Framing error: %s" % exc, self.log_stream)
                break
            if message is None:
                break  # EOF
            if message.get("__invalid_json__"):
                log("Ignoring invalid JSON message", self.log_stream)
                continue
            self.handle(message)
        return self.exit_code

    # -- dispatch --------------------------------------------------
    def handle(self, message):
        method = message.get("method")
        if method is None:
            log("Ignoring message without a method", self.log_stream)
            return
        log("Received method: %s" % method, self.log_stream)
        has_id = "id" in message
        params = message.get("params") or {}

        if method == "exit" and not has_id:
            self.exit_code = 0 if self.shutdown_requested else 1
            self.running = False
            return

        if has_id:
            if self.shutdown_requested:
                self.send_error(message["id"], -32600,
                                "Invalid Request: server is shut down")
                return
            handler = {
                "initialize": self.on_initialize,
                "shutdown": self.on_shutdown,
                "textDocument/completion": self.on_completion,
            }.get(method)
            if handler is None:
                self.send_error(message["id"], -32601,
                                "Method not found: %s" % method)
            else:
                handler(message["id"], params)
        else:
            # Notifications are never answered.
            handler = {
                "initialized": self.on_initialized,
                "textDocument/didOpen": self.on_did_open,
                "textDocument/didChange": self.on_did_change,
                "textDocument/didClose": self.on_did_close,
                "textDocument/didSave": self.on_did_save,
            }.get(method)
            if handler is not None:
                handler(params)
            else:
                log("Ignoring unknown notification: %s" % method,
                    self.log_stream)

    # -- requests --------------------------------------------------
    def on_initialize(self, msg_id, params):
        client = params.get("clientInfo") or {}
        name = client.get("name", "unknown client")
        version = client.get("version")
        log("Connected to: %s%s" % (
            name, (" " + str(version)) if version else ""),
            self.log_stream)
        self.send_response(msg_id, {
            "capabilities": {
                "textDocumentSync": 1,  # Full
                "completionProvider": {},
            },
            "serverInfo": {"name": SERVER_NAME,
                           "version": SERVER_VERSION},
        })
        log("Sent the reply", self.log_stream)

    def on_shutdown(self, msg_id, _params):
        self.shutdown_requested = True
        self.send_response(msg_id, None)

    def on_completion(self, msg_id, params):
        doc = self.documents.get((params.get("textDocument") or {}).get("uri"))
        position = params.get("position") or {}
        if doc is None:
            items = []
        else:
            items = completion_items(doc["text"],
                                     position.get("line", 0),
                                     position.get("character", 0))
        self.send_response(msg_id, {"isIncomplete": False, "items": items})

    # -- notifications ---------------------------------------------
    def on_initialized(self, _params):
        pass  # Logged by dispatch already; nothing to do.

    def publish_diagnostics(self, uri):
        doc = self.documents.get(uri)
        params = {"uri": uri, "diagnostics": []}
        if doc is not None:
            params["diagnostics"] = analyze_document(doc["text"])
            if doc.get("version") is not None:
                params["version"] = doc["version"]
        self.send_notification("textDocument/publishDiagnostics", params)

    def on_did_open(self, params):
        doc = params.get("textDocument") or {}
        uri = doc.get("uri")
        if uri is None:
            log("didOpen without a uri, ignored", self.log_stream)
            return
        self.documents[uri] = {
            "languageId": doc.get("languageId"),
            "version": doc.get("version"),
            "text": doc.get("text", ""),
        }
        log("Opened: %s" % uri, self.log_stream)
        log(self.documents[uri]["text"], self.log_stream)
        self.publish_diagnostics(uri)

    def on_did_change(self, params):
        doc_params = params.get("textDocument") or {}
        uri = doc_params.get("uri")
        changes = params.get("contentChanges") or []
        if uri is None or not changes:
            log("didChange without uri/content, ignored", self.log_stream)
            return
        entry = self.documents.setdefault(
            uri, {"languageId": None, "version": None, "text": ""})
        entry["text"] = changes[0].get("text", "")
        if doc_params.get("version") is not None:
            entry["version"] = doc_params["version"]
        self.publish_diagnostics(uri)

    def on_did_close(self, params):
        uri = (params.get("textDocument") or {}).get("uri")
        if uri is None:
            return
        self.documents.pop(uri, None)
        # Publish empty diagnostics to clear the editor's markers.
        self.send_notification("textDocument/publishDiagnostics",
                               {"uri": uri, "diagnostics": []})

    def on_did_save(self, _params):
        pass  # Accepted; no action needed.


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lsp_server.py",
        description="cclsp: a small LSP language server over stdio.")
    parser.add_argument("--log-file", default=None,
                        help="write logs to this file instead of stderr")
    args = parser.parse_args(argv)
    if args.log_file:
        log_stream = open(args.log_file, "a", encoding="utf-8")
    else:
        log_stream = sys.stderr
    server = LanguageServer(sys.stdin.buffer, sys.stdout.buffer, log_stream)
    try:
        return server.run()
    finally:
        if args.log_file:
            log_stream.close()


if __name__ == "__main__":
    sys.exit(main())

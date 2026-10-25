#!/usr/bin/env python3
"""Tests for lsp_server.py — framing, diagnostics, completion, server
dispatch over in-memory streams, and one subprocess end-to-end run
over real pipes. Run: python3 -m unittest discover -s tests -v"""

import io
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lsp_server import (LanguageServer, analyze_document,
                        completion_items, encode_message, read_message)


URI = "file:///tmp/test.txt"


def decode_all(raw):
    """Parse every framed message out of raw stdout bytes."""
    stream = io.BytesIO(raw)
    messages = []
    while True:
        msg = read_message(stream)
        if msg is None:
            break
        messages.append(msg)
    return messages


def run_server(messages):
    """Feed framed messages to a LanguageServer; return (server, replies)."""
    raw = b"".join(encode_message(m) for m in messages)
    server = LanguageServer(io.BytesIO(raw), io.BytesIO(), io.StringIO())
    code = server.run()
    return server, decode_all(server.wfile.getvalue()), code


def req(msg_id, method, params=None):
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def note(method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def did_open(text, version=1):
    return note("textDocument/didOpen", {"textDocument": {
        "uri": URI, "languageId": "plaintext", "version": version,
        "text": text}})


class FramingTests(unittest.TestCase):
    def test_round_trip_and_header(self):
        msg = {"jsonrpc": "2.0", "id": 3, "method": "initialize"}
        raw = encode_message(msg)
        header, body = raw.split(b"\r\n\r\n", 1)
        self.assertTrue(header.startswith(b"Content-Length: "))
        self.assertEqual(int(header.split(b": ")[1]), len(body))
        self.assertEqual(read_message(io.BytesIO(raw)), msg)

    def test_case_insensitive_header_and_content_type(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "initialized"})
        raw = ("content-length: %d\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n%s"
               % (len(body), body)).encode()
        self.assertEqual(read_message(io.BytesIO(raw))["method"], "initialized")

    def test_eof_returns_none(self):
        self.assertIsNone(read_message(io.BytesIO(b"")))


class DiagnosticTests(unittest.TestCase):
    def test_both_phrases_one_line(self):
        diags = analyze_document(
            "Watching a Video is not Coding Challenges")
        self.assertEqual(len(diags), 2)
        first, second = diags
        self.assertEqual(first["range"]["start"], {"line": 0, "character": 0})
        self.assertEqual(first["range"]["end"], {"line": 0, "character": 16})
        self.assertEqual(first["message"],
                         "It's much better to learn by doing! "
                         "Try Coding Challenges instead.")
        self.assertEqual(first["severity"], 2)
        self.assertEqual(second["range"]["start"], {"line": 0, "character": 24})
        self.assertEqual(second["message"], "This is the way!")
        self.assertEqual(second["severity"], 3)
        self.assertTrue(all(d["source"] == "cclsp" for d in diags))

    def test_multiple_occurrences_same_line(self):
        text = "Coding Challenges and Coding Challenges"
        diags = analyze_document(text)
        self.assertEqual(len(diags), 2)
        self.assertEqual(diags[1]["range"]["start"]["character"], 22)

    def test_line_numbers_and_empty(self):
        diags = analyze_document("clean line\nWatching a Video here")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0]["range"]["start"]["line"], 1)
        self.assertEqual(analyze_document("nothing to see"), [])

    def test_case_sensitive(self):
        self.assertEqual(analyze_document("watching a video"), [])


class CompletionTests(unittest.TestCase):
    def test_empty_and_prefixes(self):
        for fragment in ("", "C", "Cod", "CodingChallenges"):
            text = "prefix " + fragment
            items = completion_items(text, 0, len(text))
            self.assertEqual(len(items), 1, fragment)
            self.assertEqual(items[0]["label"], "CodingChallenges")
            self.assertEqual(items[0]["insertText"], "CodingChallenges")

    def test_non_matching_fragment(self):
        self.assertEqual(completion_items("xyz", 0, 3), [])
        self.assertEqual(completion_items("Watching", 0, 8), [])

    def test_cursor_mid_word(self):
        # Cursor after "Cod" in "CodingChallenges" uses only "Cod".
        self.assertEqual(len(completion_items("CodingChallenges", 0, 3)), 1)

    def test_out_of_range_line(self):
        self.assertEqual(len(completion_items("hi", 9, 0)), 1)


class ServerTests(unittest.TestCase):
    def test_initialize_response(self):
        _, replies, _ = run_server([req(1, "initialize", {
            "clientInfo": {"name": "FakeClient", "version": "0.1"}})])
        self.assertEqual(len(replies), 1)
        reply = replies[0]
        self.assertEqual(reply["id"], 1)
        caps = reply["result"]["capabilities"]
        self.assertEqual(caps["textDocumentSync"], 1)
        self.assertIn("completionProvider", caps)
        self.assertEqual(reply["result"]["serverInfo"]["name"], "cclsp")

    def test_string_id_echoed(self):
        _, replies, _ = run_server([req("abc", "initialize")])
        self.assertEqual(replies[0]["id"], "abc")

    def test_initialized_produces_no_reply(self):
        _, replies, _ = run_server([note("initialized")])
        self.assertEqual(replies, [])

    def test_did_open_publishes_diagnostics(self):
        _, replies, _ = run_server(
            [did_open("Watching a Video\nCoding Challenges")])
        self.assertEqual(len(replies), 1)
        pub = replies[0]
        self.assertEqual(pub["method"], "textDocument/publishDiagnostics")
        self.assertEqual(pub["params"]["uri"], URI)
        self.assertEqual(pub["params"]["version"], 1)
        self.assertEqual(len(pub["params"]["diagnostics"]), 2)

    def test_did_change_replaces_and_republishes(self):
        _, replies, _ = run_server([
            did_open("Watching a Video"),
            note("textDocument/didChange", {
                "textDocument": {"uri": URI, "version": 2},
                "contentChanges": [{"text": "Coding Challenges"}]}),
        ])
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[1]["params"]["diagnostics"][0]["message"],
                         "This is the way!")
        self.assertEqual(replies[1]["params"]["version"], 2)

    def test_did_close_clears(self):
        server, replies, _ = run_server([
            did_open("Coding Challenges"),
            note("textDocument/didClose", {"textDocument": {"uri": URI}}),
        ])
        self.assertNotIn(URI, server.documents)
        self.assertEqual(replies[-1]["params"]["diagnostics"], [])

    def test_did_save_no_reply(self):
        _, replies, _ = run_server([note("textDocument/didSave",
                                         {"textDocument": {"uri": URI}})])
        self.assertEqual(replies, [])

    def test_completion_opened_and_unopened(self):
        _, replies, _ = run_server([
            did_open("I like Cod"),
            req(7, "textDocument/completion", {
                "textDocument": {"uri": URI},
                "position": {"line": 0, "character": 10}}),
            req(8, "textDocument/completion", {
                "textDocument": {"uri": "file:///tmp/other.txt"},
                "position": {"line": 0, "character": 0}}),
        ])
        items = replies[1]["result"]["items"]
        self.assertEqual([i["label"] for i in items], ["CodingChallenges"])
        self.assertEqual(replies[2]["result"]["items"], [])

    def test_unknown_request_and_notification(self):
        _, replies, _ = run_server([
            req(1, "textDocument/hover"),
            note("workspace/didChangeConfiguration"),
        ])
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["error"]["code"], -32601)

    def test_invalid_json_skipped(self):
        body = b"{not json"
        raw = b"Content-Length: %d\r\n\r\n" % len(body) + body
        raw += encode_message(req(1, "initialize"))
        server = LanguageServer(io.BytesIO(raw), io.BytesIO(), io.StringIO())
        server.run()
        replies = decode_all(server.wfile.getvalue())
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["id"], 1)

    def test_shutdown_exit_codes(self):
        _, replies, code = run_server([
            req(1, "shutdown"), note("exit")])
        self.assertEqual(replies[0]["result"], None)
        self.assertEqual(code, 0)

        _, _, code = run_server([note("exit")])
        self.assertEqual(code, 1)

    def test_request_after_shutdown_rejected(self):
        _, replies, _ = run_server([
            req(1, "shutdown"),
            req(2, "initialize"),
            note("exit"),
        ])
        self.assertEqual(replies[1]["error"]["code"], -32600)

    def test_eof_returns_zero(self):
        _, _, code = run_server([])
        self.assertEqual(code, 0)


class EndToEndTests(unittest.TestCase):
    def test_subprocess_conversation(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, "lsp_server.py")
        messages = [
            req(1, "initialize", {"clientInfo": {"name": "FakeClient"}}),
            note("initialized"),
            did_open("I love Coding Challenges"),
            req(2, "textDocument/completion", {
                "textDocument": {"uri": URI},
                "position": {"line": 0, "character": 0}}),
            req(3, "shutdown"),
            note("exit"),
        ]
        payload = b"".join(encode_message(m) for m in messages)
        proc = subprocess.run(
            [sys.executable, script], input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        replies = decode_all(proc.stdout)
        methods = [r.get("method") for r in replies]
        self.assertIn("textDocument/publishDiagnostics", methods)
        pub = replies[methods.index("textDocument/publishDiagnostics")]
        self.assertIn("This is the way!",
                      [d["message"] for d in pub["params"]["diagnostics"]])
        by_id = {r["id"]: r for r in replies if "id" in r}
        self.assertEqual(by_id[2]["result"]["items"][0]["label"],
                         "CodingChallenges")
        self.assertEqual(by_id[3]["result"], None)
        self.assertIn(b"[cclsp] Received method: initialize", proc.stderr)


if __name__ == "__main__":
    unittest.main()

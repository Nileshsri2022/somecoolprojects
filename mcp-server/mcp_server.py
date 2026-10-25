#!/usr/bin/env python3
"""MCP Server For AI Agents — Coding Challenges challenge-mcp-server.

Python 3 standard library only. Implements the Model Context Protocol
core (JSON-RPC 2.0) directly: stdio transport by default, plain
JSON-RPC POST on --http. See docs/SPEC.md for divergences and scope.

Tools:
  hello                         Step 1: "Hello, <name>"
  CodingChallengesSolutionFinder Step 3: links for a coding challenge
  get_solution                  Step 6: solution row for challenge+language

No API keys, no LLM, no real agent is involved. The solutions index is
a local Markdown file by default (data/shared-solutions.md); pass
--solutions-file / --solutions-url to use a real index.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "mcp-server"
SERVER_VERSION = "0.1.0"
FETCH_TIMEOUT = 10

LINK_RE = re.compile(r"\[(.*?)\]\((.*?)\)")

TOOLS = [
    {
        "name": "hello",
        "description": "Return 'Hello, <name>'. The Step 1 Hello-World tool.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "CodingChallengesSolutionFinder",
        "description": (
            "Find links to pages listing shared solutions for a coding "
            "challenge. Takes the challenge name (or part of it)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"challenge": {"type": "string"}},
            "required": ["challenge"],
        },
    },
    {
        "name": "get_solution",
        "description": (
            "Get the shared solution for a challenge in a given language "
            "by parsing the challenge's solution-list page table."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "challenge": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["challenge", "language"],
        },
    },
]

RESOURCES = [
    {
        "uri": "solutions://index",
        "name": "Shared solutions index",
        "description": "The raw text of the solutions index currently loaded.",
        "mimeType": "text/markdown",
    }
]

PROMPTS = [
    {
        "name": "find-solution",
        "description": "Ask for shared solutions to a coding challenge.",
        "arguments": [
            {"name": "challenge", "description": "Challenge name", "required": True},
            {"name": "language", "description": "Language (optional)", "required": False},
        ],
    }
]


# ---------------------------------------------------------------- index

def default_index_path():
    return Path(__file__).resolve().parent / "data" / "shared-solutions.md"


def default_solutions_dir():
    return Path(__file__).resolve().parent / "data" / "solutions"


def load_index(solutions_file=None, solutions_url=None):
    """Return (text, error_or_None). Never raises for fetch problems."""
    if solutions_url:
        try:
            with urllib.request.urlopen(solutions_url, timeout=FETCH_TIMEOUT) as r:
                if r.status != 200:
                    return "", "failed to fetch solutions index from %s: HTTP %s" % (
                        solutions_url, r.status)
                return r.read().decode("utf-8", "replace"), None
        except Exception as exc:  # Step 4: GitHub unreachable, report it
            return "", "failed to fetch solutions index from %s: %s" % (
                solutions_url, exc)
    path = Path(solutions_file) if solutions_file else default_index_path()
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return "", "failed to read solutions index %s: %s" % (path, exc)


def find_solutions(index_text, query):
    """Step 3: Markdown links whose text contains query (case-insensitive)."""
    q = query.strip().lower()
    found, seen = [], set()
    for line in index_text.splitlines():
        for text, url in LINK_RE.findall(line):
            if q and q in text.lower() and url not in seen:
                seen.add(url)
                found.append({"challenge": text.strip(), "url": url.strip()})
    return found


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "challenge"


def parse_solution_table(page_text, language):
    """Step 6: first table row whose first column matches language."""
    lang = language.strip().lower()
    header = None
    for line in page_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") and c for c in cells):
            continue  # separator row
        if header is None:
            header = cells
            continue
        if cells and cells[0].lower() == lang:
            row = {}
            for i, value in enumerate(cells):
                key = header[i] if i < len(header) else "column%d" % i
                row[key] = value
            return row
    return None


def get_solution(state, challenge, language):
    """Step 6: local page first, then follow Step 3 links over HTTP(S)."""
    solutions = find_solutions(state["index"], challenge)
    if not solutions:
        return None, "no shared solutions listed for %r" % challenge
    local = Path(state["solutions_dir"]) / (slugify(challenge) + ".md")
    pages = []
    if local.exists():
        try:
            pages.append(local.read_text(encoding="utf-8"))
        except OSError as exc:
            return None, "failed to read solution page %s: %s" % (local, exc)
        # A local page is authoritative: do not also chase its (possibly
        # placeholder) links over the network.
        row = parse_solution_table(pages[0], language)
        if row is not None:
            return row, None
        return None, "no solution in language %r found for %r" % (language, challenge)
    last_error = None
    for entry in solutions:
        url = entry["url"]
        if not url.startswith(("http://", "https://")):
            continue
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT) as r:
                if r.status == 200:
                    pages.append(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            last_error = exc
    for page in pages:
        row = parse_solution_table(page, language)
        if row is not None:
            return row, None
    if not pages:
        detail = (" (last fetch error: %s)" % last_error) if last_error else ""
        return None, "could not obtain a solution page for %r%s" % (challenge, detail)
    return None, "no solution in language %r found for %r" % (language, challenge)


# ---------------------------------------------------------------- tools

def text_result(text, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def _arg(arguments, *names):
    for name in names:
        if isinstance(arguments, dict) and name in arguments:
            return arguments[name]
    return None


def call_tool(state, name, arguments):
    """Return an MCP tool result dict (never raises for bad tool input)."""
    arguments = arguments if isinstance(arguments, dict) else {}
    if name == "hello":
        value = _arg(arguments, "name", "string")
        if not isinstance(value, str):
            return text_result(
                "hello requires a string argument 'name'.", is_error=True)
        return text_result("Hello, %s" % value)
    if name == "CodingChallengesSolutionFinder":
        query = _arg(arguments, "challenge", "name", "query")
        if not isinstance(query, str) or not query.strip():
            return text_result(
                "CodingChallengesSolutionFinder requires a string argument "
                "'challenge'.", is_error=True)
        if state["index_error"]:
            return text_result(state["index_error"], is_error=True)
        matches = find_solutions(state["index"], query)
        if not matches:
            return text_result(
                'No shared solutions listed for "%s".' % query)
        return text_result("\n".join(
            "%s: %s" % (m["challenge"], m["url"]) for m in matches))
    if name == "get_solution":
        challenge = _arg(arguments, "challenge", "name", "query")
        language = _arg(arguments, "language")
        if not isinstance(challenge, str) or not challenge.strip():
            return text_result(
                "get_solution requires a string argument 'challenge'.",
                is_error=True)
        if not isinstance(language, str) or not language.strip():
            return text_result(
                "get_solution requires a string argument 'language'.",
                is_error=True)
        if state["index_error"]:
            return text_result(state["index_error"], is_error=True)
        row, error = get_solution(state, challenge, language)
        if error:
            return text_result(error, is_error=True)
        return text_result(" | ".join("%s: %s" % kv for kv in row.items()))
    return None  # unknown tool: caller turns this into -32602


# ---------------------------------------------------------------- dispatch

def handle_request(state, request):
    """Pure dispatcher: request dict -> response dict, or None for
    notifications (requests without an 'id')."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    method = request.get("method")
    params = request.get("params") or {}
    req_id = request.get("id")
    if req_id is None:
        return None  # notification: no response, by protocol
    if not isinstance(params, dict):
        params = {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        tool = params.get("name")
        result = call_tool(state, tool, params.get("arguments"))
        if result is None:
            return err(-32602, "Unknown tool: %r" % (tool,))
        return ok(result)
    if method == "resources/list":
        return ok({"resources": RESOURCES})
    if method == "resources/read":
        uri = params.get("uri")
        if uri != "solutions://index":
            return err(-32602, "Unknown resource: %r" % (uri,))
        if state["index_error"]:
            return err(-32602, state["index_error"])
        return ok({"contents": [{"uri": uri, "mimeType": "text/markdown",
                                 "text": state["index"]}]})
    if method == "prompts/list":
        return ok({"prompts": PROMPTS})
    if method == "prompts/get":
        name = params.get("name")
        if name != "find-solution":
            return err(-32602, "Unknown prompt: %r" % (name,))
        args = params.get("arguments") or {}
        challenge = args.get("challenge", "")
        language = args.get("language")
        text = "Find shared solutions for the coding challenge %r." % challenge
        if language:
            text += " I want a solution in %s." % language
        return ok({
            "description": "Ask for shared solutions to a coding challenge.",
            "messages": [{"role": "user",
                          "content": {"type": "text", "text": text}}],
        })
    return err(-32601, "Method not found: %r" % (method,))


def make_state(args):
    index, index_error = load_index(args.solutions_file, args.solutions_url)
    return {
        "index": index,
        "index_error": index_error,
        "solutions_dir": args.solutions_dir or str(default_solutions_dir()),
    }


def serve_stdio(state):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = handle_request(state, request)
        except Exception as exc:  # never die on one bad request
            response = {"jsonrpc": "2.0",
                        "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32603, "message": "Internal error: %s" % exc}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def serve_http(state, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout/stderr clean
            pass

        def _send(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/mcp":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(200, {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "Parse error"}})
                return
            response = handle_request(state, request)
            if response is None:
                self._send(202, {})
            else:
                self._send(200, response)

        def do_GET(self):
            self._send(404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("listening on port %d" % server.server_address[1], file=sys.stderr, flush=True)
    server.serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(description="MCP server (stdio/HTTP).")
    parser.add_argument("--http", action="store_true",
                        help="serve JSON-RPC POST on /mcp instead of stdio")
    parser.add_argument("--port", type=int, default=0,
                        help="HTTP port (0 = ephemeral, printed to stderr)")
    parser.add_argument("--solutions-file", default=None)
    parser.add_argument("--solutions-url", default=None)
    parser.add_argument("--solutions-dir", default=None)
    args = parser.parse_args(argv)
    state = make_state(args)
    if args.http:
        serve_http(state, args.port)
    else:
        serve_stdio(state)


if __name__ == "__main__":
    main()

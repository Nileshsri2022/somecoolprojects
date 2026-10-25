#!/usr/bin/env python3
"""Scripted fake MCP client tests for mcp_server.py (stdlib unittest).

No real agent, LLM, Inspector, or network is used. The stdio tests
spawn the server as a subprocess and speak JSON-RPC to it exactly as
an MCP client would; HTTP tests use an ephemeral port and kill the
child by explicit PID.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"


def req(req_id, method, params=None):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


class StdioClient:
    def __init__(self, extra_args=()):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER), *extra_args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=str(ROOT))
        self.next_id = 1

    def call(self, method, params=None):
        rid = self.next_id
        self.next_id += 1
        self.proc.stdin.write(json.dumps(req(rid, method, params)) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "server closed stdout unexpectedly"
        resp = json.loads(line)
        assert resp["id"] == rid, resp
        return resp

    def raw(self, text):
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        self.proc.wait(timeout=10)


class StdioTests(unittest.TestCase):
    def setUp(self):
        self.client = StdioClient()

    def tearDown(self):
        self.client.close()

    def test_initialize_and_capabilities(self):
        resp = self.client.call("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "fake-client", "version": "0"}})
        result = resp["result"]
        self.assertEqual(result["serverInfo"]["name"], "mcp-server")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("prompts", result["capabilities"])

    def test_notification_gets_no_response(self):
        # notifications/initialized has no id, so the next real reply
        # must still be the ping reply — a stray reply would desync us.
        self.client.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.client.proc.stdin.flush()
        resp = self.client.call("ping")
        self.assertEqual(resp["result"], {})

    def test_ping(self):
        self.assertEqual(self.client.call("ping")["result"], {})

    def test_tools_list_names_all_three(self):
        names = [t["name"] for t in
                 self.client.call("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["hello", "CodingChallengesSolutionFinder",
                                 "get_solution"])

    def test_hello(self):
        resp = self.client.call("tools/call", {
            "name": "hello", "arguments": {"name": "World"}})
        self.assertEqual(resp["result"]["content"][0]["text"], "Hello, World")
        self.assertNotIn("isError", resp["result"])

    def test_hello_alias_and_empty(self):
        resp = self.client.call("tools/call", {
            "name": "hello", "arguments": {"string": "Ada"}})
        self.assertEqual(resp["result"]["content"][0]["text"], "Hello, Ada")
        resp = self.client.call("tools/call", {
            "name": "hello", "arguments": {"name": ""}})
        self.assertEqual(resp["result"]["content"][0]["text"], "Hello, ")

    def test_hello_bad_args_are_tool_errors_not_crashes(self):
        for args in ({}, {"name": 42}):
            resp = self.client.call("tools/call", {"name": "hello", "arguments": args})
            self.assertTrue(resp["result"]["isError"])
        # server still alive afterwards
        self.assertEqual(self.client.call("ping")["result"], {})

    def test_finder_exact_and_substring_and_case(self):
        resp = self.client.call("tools/call", {
            "name": "CodingChallengesSolutionFinder",
            "arguments": {"challenge": "Build Your Own WC Tool"}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("https://example.invalid/solutions/wc-tool", text)
        resp = self.client.call("tools/call", {
            "name": "CodingChallengesSolutionFinder",
            "arguments": {"challenge": "build your own"}})
        text = resp["result"]["content"][0]["text"]
        self.assertGreaterEqual(text.count("https://example.invalid/solutions/"), 4)

    def test_finder_no_match_sentence(self):
        resp = self.client.call("tools/call", {
            "name": "CodingChallengesSolutionFinder",
            "arguments": {"challenge": "No Such Challenge XYZ"}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("No shared solutions listed", text)
        self.assertNotIn("http", text)  # never fabricate a link

    def test_unknown_tool_and_method(self):
        resp = self.client.call("tools/call", {"name": "nope", "arguments": {}})
        self.assertEqual(resp["error"]["code"], -32602)
        resp = self.client.call("no/such-method")
        self.assertEqual(resp["error"]["code"], -32601)

    def test_malformed_json_then_server_survives(self):
        resp = self.client.raw("{not json")
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertEqual(self.client.call("ping")["result"], {})

    def test_full_agent_shaped_flow(self):
        # Step 2 Inspector role, scripted: init → list → call.
        self.client.call("initialize", {"protocolVersion": "2024-11-05",
                                        "capabilities": {}, "clientInfo": {}})
        tools = self.client.call("tools/list")["result"]["tools"]
        self.assertTrue(any(t["name"] == "hello" for t in tools))
        resp = self.client.call("tools/call", {
            "name": "hello", "arguments": {"name": "Inspector"}})
        self.assertEqual(resp["result"]["content"][0]["text"],
                         "Hello, Inspector")

    def test_get_solution_local_page(self):
        resp = self.client.call("tools/call", {
            "name": "get_solution",
            "arguments": {"challenge": "Build Your Own WC Tool",
                          "language": "python"}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("Ada Example", text)
        self.assertIn("https://example.invalid/solutions/wc-tool/python", text)

    def test_get_solution_language_case_and_missing(self):
        resp = self.client.call("tools/call", {
            "name": "get_solution",
            "arguments": {"challenge": "Build Your Own WC Tool",
                          "language": "GO"}})
        self.assertIn("Bo Example", resp["result"]["content"][0]["text"])
        resp = self.client.call("tools/call", {
            "name": "get_solution",
            "arguments": {"challenge": "Build Your Own WC Tool",
                          "language": "Haskell"}})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("Haskell", resp["result"]["content"][0]["text"])

    def test_resources_and_prompts(self):
        res = self.client.call("resources/list")["result"]["resources"]
        self.assertEqual(res[0]["uri"], "solutions://index")
        read = self.client.call("resources/read", {"uri": "solutions://index"})
        self.assertIn("Build Your Own WC Tool",
                      read["result"]["contents"][0]["text"])
        bad = self.client.call("resources/read", {"uri": "nope://x"})
        self.assertEqual(bad["error"]["code"], -32602)
        prompts = self.client.call("prompts/list")["result"]["prompts"]
        self.assertEqual(prompts[0]["name"], "find-solution")
        got = self.client.call("prompts/get", {
            "name": "find-solution",
            "arguments": {"challenge": "WC Tool", "language": "Go"}})
        msg = got["result"]["messages"][0]["content"]["text"]
        self.assertIn("WC Tool", msg)
        self.assertIn("Go", msg)
        bad = self.client.call("prompts/get", {"name": "nope"})
        self.assertEqual(bad["error"]["code"], -32602)


class DirectTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT))
        import mcp_server
        self.m = mcp_server

    def test_find_solutions_dedup_and_substring(self):
        text = ("- [Alpha Tool](https://x/a)\n"
                "- [Alpha Tool](https://x/a)\n"
                "- [Beta](https://x/b)\n"
                "bare https://x/c not a link\n")
        found = self.m.find_solutions(text, "alpha")
        self.assertEqual(found, [{"challenge": "Alpha Tool", "url": "https://x/a"}])

    def test_parse_table_extra_columns_and_separator(self):
        page = ("| Language | Author | Link | Notes |\n"
                "|---|---|---|---|\n"
                "| Java | Jo | https://x/j | fast |\n")
        row = self.m.parse_solution_table(page, "java")
        self.assertEqual(row["Author"], "Jo")
        self.assertEqual(row["Notes"], "fast")
        self.assertIsNone(self.m.parse_solution_table(page, "Python"))

    def test_slugify(self):
        self.assertEqual(self.m.slugify("Build Your Own WC Tool!"),
                         "build-your-own-wc-tool")


class ErrorHandlingTests(unittest.TestCase):
    def test_unreachable_index_url_is_tool_error_server_alive(self):
        client = StdioClient(("--solutions-url", "http://127.0.0.1:1/index.md"))
        try:
            resp = client.call("tools/call", {
                "name": "CodingChallengesSolutionFinder",
                "arguments": {"challenge": "WC Tool"}})
            self.assertTrue(resp["result"]["isError"])
            self.assertIn("failed to fetch", resp["result"]["content"][0]["text"])
            self.assertEqual(client.call("ping")["result"], {})
        finally:
            client.close()

    def test_custom_index_without_links_gives_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.md"
            index.write_text("# Solutions\n\nNothing linked here yet.\n")
            client = StdioClient(("--solutions-file", str(index)))
            try:
                resp = client.call("tools/call", {
                    "name": "CodingChallengesSolutionFinder",
                    "arguments": {"challenge": "WC Tool"}})
                text = resp["result"]["content"][0]["text"]
                self.assertIn("No shared solutions listed", text)
                self.assertNotIn("http", text)
            finally:
                client.close()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--http", "--port", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=str(ROOT))
        line = self.proc.stderr.readline()
        m = re.search(r"port (\d+)", line)
        assert m, "no port line: %r" % line
        self.port = int(m.group(1))
        self.base = "http://127.0.0.1:%d" % self.port

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)

    def post(self, payload):
        request = urllib.request.Request(
            self.base + "/mcp",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as r:
            return json.loads(r.read())

    def test_http_round_trip(self):
        resp = self.post(req(1, "initialize", {"protocolVersion": "2024-11-05"}))
        self.assertEqual(resp["result"]["serverInfo"]["name"], "mcp-server")
        resp = self.post(req(2, "tools/call", {
            "name": "hello", "arguments": {"name": "HTTP"}}))
        self.assertEqual(resp["result"]["content"][0]["text"], "Hello, HTTP")

    def test_http_unknown_path_404(self):
        request = urllib.request.Request(self.base + "/nope", method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

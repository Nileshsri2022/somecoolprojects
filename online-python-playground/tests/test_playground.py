"""Tests for the Online Python Playground (see ../docs/TEST_PLAN.md)."""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
MAIN = os.path.join(PROJECT, "playground.py")


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class PlaygroundServerTest(unittest.TestCase):
    proc = None
    base = None

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ, PLAYGROUND_TIMEOUT="2")
        cls.proc = subprocess.Popen(
            [sys.executable, MAIN, "--port", str(cls.port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        cls.base = "http://127.0.0.1:%d" % cls.port
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                cls.get("/")
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=10)

    # -- helpers -----------------------------------------------------
    @classmethod
    def get(cls, path):
        with urllib.request.urlopen(cls.base + path, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    @classmethod
    def exec_code(cls, code):
        req = urllib.request.Request(
            cls.base + "/run",
            data=json.dumps({"code": code}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    @classmethod
    def post_raw(cls, path, data, headers=None):
        req = urllib.request.Request(
            cls.base + path, data=data,
            headers=headers or {}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    # -- frontend / routing ------------------------------------------
    def test_get_root_serves_editor_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        for needle in ('id="editor"', "Run", 'id="output"',
                       "localStorage", 'id="theme-toggle"', "#code=",
                       "Local demo sandbox"):
            self.assertIn(needle, body)

    def test_unknown_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_get_run_405(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/run")
        self.assertEqual(ctx.exception.code, 405)

    def test_post_run_bad_json_400(self):
        status, _ = self.post_raw("/run", b"{not json",
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_post_run_missing_code_400(self):
        status, _ = self.post_raw("/run", b"{}",
                                  {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_post_run_nonstring_code_400(self):
        status, _ = self.post_raw(
            "/run", json.dumps({"code": 42}).encode(),
            {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    # -- step 1: execution -------------------------------------------
    def test_hello_world(self):
        result = self.exec_code('print("Hello, World!")')
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "Hello, World!\n")

    def test_multiple_lines_math_variables(self):
        result = self.exec_code('print("a")\nprint(2 + 2)\nx = 3\nprint(x * 2)')
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "a\n4\n6\n")

    def test_empty_code(self):
        result = self.exec_code("")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "")
        self.assertIsNone(result["error"])

    def test_input_raises_eoferror_not_hang(self):
        result = self.exec_code('x = input()\nprint(x)')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "EOFError")

    # -- step 2: errors ----------------------------------------------
    def test_syntax_error_with_lineno(self):
        result = self.exec_code('if True\n    print("x")')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "SyntaxError")
        self.assertEqual(result["error"]["lineno"], 1)

    def test_name_error_with_lineno(self):
        result = self.exec_code('print(undefined_name)')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "NameError")
        self.assertEqual(result["error"]["lineno"], 1)

    def test_zero_division(self):
        result = self.exec_code('print(1 / 0)')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "ZeroDivisionError")
        self.assertEqual(result["error"]["lineno"], 1)

    def test_traceback_mentions_error_type(self):
        result = self.exec_code('print(1 / 0)')
        self.assertIn("ZeroDivisionError", result["error"]["traceback"])

    # -- step 5: safeguards ------------------------------------------
    def test_infinite_loop_times_out(self):
        start = time.time()
        result = self.exec_code('while True:\n    pass')
        elapsed = time.time() - start
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["error"]["type"], "TimeoutError")
        self.assertLess(elapsed, 10)

    def test_deep_recursion_does_not_kill_server(self):
        result = self.exec_code('def f():\n    return f()\nf()')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "RecursionError")
        # Server still responsive afterwards.
        self.assertTrue(self.exec_code('print("alive")')["ok"])

    def test_huge_output_truncated(self):
        result = self.exec_code('print("x" * 100000)')
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["stdout"]), 10000)

    def test_memory_hog_reported_and_server_survives(self):
        result = self.exec_code('x = []\nwhile True:\n    x.append("y" * 1000000)')
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["error"])
        self.assertTrue(self.exec_code('print("alive")')["ok"])

    # -- sandbox ------------------------------------------------------
    def test_import_socket_blocked(self):
        result = self.exec_code('import socket')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "PermissionError")
        self.assertIn("socket", result["error"]["message"])

    def test_import_subprocess_and_os_system_blocked(self):
        for code in ('import subprocess', 'import os\nos.system("echo hi")'):
            result = self.exec_code(code)
            self.assertFalse(result["ok"], code)
            self.assertEqual(result["error"]["type"], "PermissionError")

    def test_read_outside_tempdir_blocked(self):
        result = self.exec_code('open("/etc/passwd")')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "PermissionError")

    def test_relative_write_stays_in_tempdir(self):
        result = self.exec_code(
            'open("out.txt", "w").write("hi")\nprint(open("out.txt").read())')
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"], "hi\n")
        self.assertFalse(os.path.exists(os.path.join(PROJECT, "out.txt")))

    def test_no_cross_run_contamination(self):
        self.exec_code('x_secret = 123')
        result = self.exec_code('print(x_secret)')
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "NameError")


class DefaultTimeoutTest(unittest.TestCase):
    def test_default_timeout_is_five_seconds(self):
        sys.path.insert(0, PROJECT)
        try:
            import playground
            self.assertEqual(playground.DEFAULT_TIMEOUT, 5.0)
        finally:
            sys.path.pop(0)
            sys.modules.pop("playground", None)


if __name__ == "__main__":
    unittest.main()

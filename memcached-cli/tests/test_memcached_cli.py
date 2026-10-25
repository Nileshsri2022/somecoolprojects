#!/usr/bin/env python3
"""Tests for memcached_cli.py against a small in-process fake server.

The fake server speaks enough of the Memcached text protocol for the
tests and listens on an ephemeral port (port 0). No real memcached
daemon and no other project directory are involved.
"""

import socket
import socketserver
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memcached_cli import MemcachedClient, MemcachedError, build_parser  # noqa: E402

CLI = str(Path(__file__).resolve().parent.parent / "memcached_cli.py")


class FakeMemcachedHandler(socketserver.StreamRequestHandler):
    store = {}
    lock = threading.Lock()
    cas_counter = 0

    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                return
            parts = line.decode().strip().split()
            if not parts:
                continue
            cmd = parts[0]
            if cmd in ("set", "add", "replace", "append", "prepend"):
                self._storage(cmd, parts)
            elif cmd in ("get", "gets"):
                self._retrieve(cmd, parts[1:])
            elif cmd == "delete":
                self._delete(parts)
            elif cmd in ("incr", "decr"):
                self._counter(cmd, parts)
            elif cmd == "touch":
                self._touch(parts)
            elif cmd == "flush_all":
                with self.lock:
                    self.store.clear()
                self.wfile.write(b"OK\r\n")
            elif cmd == "stats":
                self.wfile.write(b"STAT pid 1234\r\nSTAT version 1.6.9\r\nEND\r\n")
            elif cmd == "version":
                self.wfile.write(b"VERSION 1.6.9\r\n")
            elif cmd == "quit":
                return
            else:
                self.wfile.write(b"ERROR\r\n")
            self.wfile.flush()

    def _storage(self, cmd, parts):
        key, flags, _exptime, nbytes = parts[1], parts[2], parts[3], int(parts[4])
        data = self.rfile.read(nbytes + 2)[:nbytes]
        with self.lock:
            exists = key in self.store
            if cmd == "add" and exists:
                self.wfile.write(b"NOT_STORED\r\n")
                return
            if cmd == "replace" and not exists:
                self.wfile.write(b"NOT_STORED\r\n")
                return
            if cmd == "append" and exists:
                old_flags, old, _ = self.store[key]
                data, flags = old + data, old_flags
            elif cmd == "prepend" and exists:
                old_flags, old, _ = self.store[key]
                data, flags = data + old, old_flags
            elif cmd in ("append", "prepend") and not exists:
                self.wfile.write(b"NOT_STORED\r\n")
                return
            FakeMemcachedHandler.cas_counter += 1
            self.store[key] = (flags, data, FakeMemcachedHandler.cas_counter)
            self.wfile.write(b"STORED\r\n")

    def _retrieve(self, cmd, keys):
        with self.lock:
            for key in keys:
                if key in self.store:
                    flags, data, cas = self.store[key]
                    header = f"VALUE {key} {flags} {len(data)}"
                    if cmd == "gets":
                        header += f" {cas}"
                    self.wfile.write(header.encode() + b"\r\n" + data + b"\r\n")
        self.wfile.write(b"END\r\n")

    def _delete(self, parts):
        with self.lock:
            if parts[1] in self.store:
                del self.store[parts[1]]
                self.wfile.write(b"DELETED\r\n")
            else:
                self.wfile.write(b"NOT_FOUND\r\n")

    def _counter(self, cmd, parts):
        key, amount = parts[1], int(parts[2])
        with self.lock:
            if key not in self.store:
                self.wfile.write(b"NOT_FOUND\r\n")
                return
            _flags, data, _cas = self.store[key]
            try:
                value = int(data)
            except ValueError:
                self.wfile.write(b"CLIENT_ERROR cannot increment or decrement non-numeric value\r\n")
                return
            value = value + amount if cmd == "incr" else max(0, value - amount)
            self.store[key] = (_flags, str(value).encode(), _cas)
            self.wfile.write(f"{value}\r\n".encode())

    def _touch(self, parts):
        with self.lock:
            self.wfile.write(b"TOUCHED\r\n" if parts[1] in self.store else b"NOT_FOUND\r\n")


class FakeServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class MemcachedCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeServer(("127.0.0.1", 0), FakeMemcachedHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeMemcachedHandler.store.clear()
        self.client = MemcachedClient("127.0.0.1", self.port).connect()

    def tearDown(self):
        self.client.close()

    def cli(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, CLI, "--host", "127.0.0.1",
             "--port", str(self.port), *args],
            input=input_text, capture_output=True, text=True, timeout=15)

    # -- client: storage and retrieval -----------------------------------

    def test_set_then_get_roundtrip_with_flags(self):
        self.assertEqual(self.client.set("k", "v", flags=7), "STORED")
        self.assertEqual(self.client.get("k"), (7, "v"))

    def test_get_missing_returns_none_and_multi_get_skips_missing(self):
        self.client.set("a", "1")
        self.assertIsNone(self.client.get("nope"))
        self.assertEqual(self.client.get_multi(["a", "nope"]), {"a": (0, "1")})

    def test_gets_cas_changes_on_store(self):
        self.client.set("k", "v")
        _f, _v, cas1 = self.client.gets("k")
        self.client.set("k", "v2")
        _f, _v, cas2 = self.client.gets("k")
        self.assertIsNotNone(cas1)
        self.assertNotEqual(cas1, cas2)

    def test_add_only_when_absent_replace_only_when_present(self):
        self.assertEqual(self.client.add("k", "v"), "STORED")
        self.assertEqual(self.client.add("k", "v2"), "NOT_STORED")
        self.assertEqual(self.client.replace("missing", "v"), "NOT_STORED")
        self.assertEqual(self.client.replace("k", "v3"), "STORED")
        self.assertEqual(self.client.get("k"), (0, "v3"))

    def test_append_and_prepend_order(self):
        self.client.set("k", "mid")
        self.assertEqual(self.client.append("k", "-end"), "STORED")
        self.assertEqual(self.client.prepend("k", "start-"), "STORED")
        self.assertEqual(self.client.get("k"), (0, "start-mid-end"))
        self.assertEqual(self.client.append("missing", "x"), "NOT_STORED")

    def test_delete_then_not_found(self):
        self.client.set("k", "v")
        self.assertEqual(self.client.delete("k"), "DELETED")
        self.assertEqual(self.client.delete("k"), "NOT_FOUND")

    def test_incr_decr_and_missing(self):
        self.client.set("n", "10")
        self.assertEqual(self.client.incr("n"), 11)
        self.assertEqual(self.client.incr("n", 5), 16)
        self.assertEqual(self.client.decr("n", 2), 14)
        with self.assertRaises(MemcachedError):
            self.client.incr("missing")

    def test_touch_flush_stats_version(self):
        self.client.set("k", "v")
        self.assertEqual(self.client.touch("k", 300), "TOUCHED")
        self.assertEqual(self.client.touch("missing", 300), "NOT_FOUND")
        self.assertEqual(self.client.flush_all(), "OK")
        self.assertIsNone(self.client.get("k"))
        self.assertEqual(self.client.stats()["version"], "1.6.9")
        self.assertEqual(self.client.version(), "VERSION 1.6.9")

    def test_empty_and_non_ascii_values(self):
        self.assertEqual(self.client.set("empty", ""), "STORED")
        self.assertEqual(self.client.get("empty"), (0, ""))
        self.client.set("uni", "héllo →")
        self.assertEqual(self.client.get("uni"), (0, "héllo →"))

    def test_unknown_command_raises(self):
        self.client._send(b"bogus\r\n")
        with self.assertRaises(MemcachedError):
            self.client._read_reply()

    # -- CLI: one-shot -----------------------------------------------------

    def test_cli_set_get_and_missing_get(self):
        result = self.cli("set", "ck", "cv")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "STORED")
        result = self.cli("get", "ck")
        self.assertEqual(result.stdout.strip(), "ck: cv")
        result = self.cli("get", "absent")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_incr_stats_version_delete(self):
        self.cli("set", "n", "41")
        result = self.cli("incr", "n")
        self.assertEqual(result.stdout.strip(), "42")
        result = self.cli("stats")
        self.assertIn("STAT version 1.6.9", result.stdout)
        result = self.cli("version")
        self.assertEqual(result.stdout.strip(), "VERSION 1.6.9")
        result = self.cli("delete", "n")
        self.assertEqual(result.stdout.strip(), "DELETED")

    def test_cli_repl(self):
        result = self.cli(input_text="set rk rv\nget rk\nquit\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("STORED", result.stdout)
        self.assertIn("rk: rv", result.stdout)

    def test_cli_repl_set_with_spaces(self):
        result = self.cli(input_text="set sk hello world\nget sk\nquit\n")
        self.assertIn("sk: hello world", result.stdout)

    def test_cli_connection_failure_is_clean_error(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        result = subprocess.run(
            [sys.executable, CLI, "--host", "127.0.0.1",
             "--port", str(free_port), "version"],
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class TestParser(unittest.TestCase):
    def test_page_form_flags_and_defaults(self):
        # Challenge page form: ccmc -host <host> -p <port> <command>
        args = build_parser().parse_args(
            ["-host", "example.local", "-p", "12121", "get", "k"])
        self.assertEqual((args.host, args.port, args.command),
                         ("example.local", 12121, "get"))
        # Defaults match the page: localhost, 11211.
        args = build_parser().parse_args(["get", "k"])
        self.assertEqual((args.host, args.port), ("localhost", 11211))


if __name__ == "__main__":
    unittest.main()

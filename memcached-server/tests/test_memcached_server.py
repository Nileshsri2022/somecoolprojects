#!/usr/bin/env python3
"""Tests for memcached_server.py.

Starts the real server on an ephemeral port and speaks the wire protocol
over raw sockets — no hard-coded ports, no Memcached client library.
"""

import os
import socket
import subprocess
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memcached_server import DEFAULT_PORT, make_server  # noqa: E402


class Client:
    """Minimal raw-socket Memcached client with a receive buffer."""

    def __init__(self, port: int) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.buf = b""

    def close(self) -> None:
        self.sock.close()

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def _fill(self) -> None:
        chunk = self.sock.recv(4096)
        if not chunk:
            raise ConnectionError("server closed the connection")
        self.buf += chunk

    def read_until(self, marker: bytes) -> bytes:
        while marker not in self.buf:
            self._fill()
        out, self.buf = self.buf.split(marker, 1)
        return out + marker

    def read_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            self._fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    # Protocol helpers -------------------------------------------------
    def storage(self, cmd: str, key: str, data: bytes, flags: int = 0,
                exptime: int = 0, noreply: bool = False) -> bytes | None:
        line = f"{cmd} {key} {flags} {exptime} {len(data)}"
        if noreply:
            line += " noreply"
        self.send(line.encode() + b"\r\n" + data + b"\r\n")
        if noreply:
            return None
        return self.read_until(b"\r\n")

    def get_raw(self, *keys: str) -> bytes:
        self.send(("get " + " ".join(keys) + "\r\n").encode())
        return self.read_until(b"END\r\n")

    def get(self, key: str) -> tuple[int, bytes] | None:
        """Return (flags, data) for a single key, or None if missing."""
        raw = self.get_raw(key)
        if raw == b"END\r\n":
            return None
        header, rest = raw.split(b"\r\n", 1)
        _, _, flags, nbytes = header.split()
        data = rest[: int(nbytes)]
        return int(flags), data

    def delete(self, key: str, noreply: bool = False) -> bytes | None:
        line = f"delete {key}" + (" noreply" if noreply else "")
        self.send(line.encode() + b"\r\n")
        if noreply:
            return None
        return self.read_until(b"\r\n")


class ServerTestCase(unittest.TestCase):
    server = None
    port = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = make_server(0)  # ephemeral port
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.client = Client(self.port)

    def tearDown(self) -> None:
        self.client.close()


class TestSetGet(ServerTestCase):
    def test_set_then_get(self) -> None:
        self.assertEqual(self.client.storage("set", "test", b"1234"), b"STORED\r\n")
        self.assertEqual(self.client.get("test"), (0, b"1234"))

    def test_flags_round_trip(self) -> None:
        self.client.storage("set", "test2", b"testing", flags=1)
        self.assertEqual(self.client.get("test2"), (1, b"testing"))

    def test_get_missing_key(self) -> None:
        self.assertIsNone(self.client.get("definitely-not-here"))
        self.assertEqual(self.client.get_raw("definitely-not-here"), b"END\r\n")

    def test_noreply_set_stores_silently(self) -> None:
        self.assertIsNone(
            self.client.storage("set", "quiet", b"shh", noreply=True))
        self.assertEqual(self.client.get("quiet"), (0, b"shh"))

    def test_zero_byte_value(self) -> None:
        self.assertEqual(self.client.storage("set", "empty", b""), b"STORED\r\n")
        self.assertEqual(self.client.get("empty"), (0, b""))

    def test_binary_safe_value_with_crlf(self) -> None:
        data = b"a\r\nb\x00\xff\r\nc"
        self.client.storage("set", "bin", data)
        self.assertEqual(self.client.get("bin"), (0, data))

    def test_overwrite_replaces_value_and_flags(self) -> None:
        self.client.storage("set", "over", b"one", flags=1)
        self.client.storage("set", "over", b"two", flags=2)
        self.assertEqual(self.client.get("over"), (2, b"two"))

    def test_multi_key_get_found_only_in_order(self) -> None:
        self.client.storage("set", "mk1", b"a")
        self.client.storage("set", "mk2", b"bb")
        raw = self.client.get_raw("mk2", "missing", "mk1")
        self.assertEqual(raw, b"VALUE mk2 0 2\r\nbb\r\n"
                              b"VALUE mk1 0 1\r\na\r\nEND\r\n")

    def test_page_step2_transcript(self) -> None:
        # Exact transcript from Step 2 of the challenge page.
        self.assertEqual(self.client.storage("set", "test", b"1234"), b"STORED\r\n")
        self.assertEqual(self.client.get_raw("test"),
                         b"VALUE test 0 4\r\n1234\r\nEND\r\n")
        self.assertIsNone(
            self.client.storage("set", "test2", b"testing", flags=1, noreply=True))
        self.assertEqual(self.client.get_raw("test2"),
                         b"VALUE test2 1 7\r\ntesting\r\nEND\r\n")


class TestConcurrency(ServerTestCase):
    def test_two_clients_share_store(self) -> None:
        other = Client(self.port)
        try:
            self.client.storage("set", "shared", b"from-one")
            self.assertEqual(other.get("shared"), (0, b"from-one"))
            other.storage("set", "shared", b"from-two")
            self.assertEqual(self.client.get("shared"), (0, b"from-two"))
        finally:
            other.close()

    def test_interleaved_threads_no_crosstalk(self) -> None:
        errors: list[str] = []

        def worker(i: int) -> None:
            try:
                c = Client(self.port)
                key = f"thr{i}"
                c.storage("set", key, f"value{i}".encode())
                got = c.get(key)
                assert got == (0, f"value{i}".encode()), f"{key}: {got!r}"
                c.close()
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class TestExpiry(ServerTestCase):
    def test_short_expiry_then_gone(self) -> None:
        self.client.storage("set", "shortlived", b"data", exptime=1)
        self.assertEqual(self.client.get("shortlived"), (0, b"data"))
        time.sleep(1.3)
        self.assertIsNone(self.client.get("shortlived"))

    def test_long_expiry_still_present(self) -> None:
        self.client.storage("set", "longlived", b"data", exptime=100)
        self.assertEqual(self.client.get("longlived"), (0, b"data"))

    def test_negative_expiry_immediately_expired(self) -> None:
        self.assertEqual(
            self.client.storage("set", "dead", b"data", exptime=-1), b"STORED\r\n")
        self.assertIsNone(self.client.get("dead"))

    def test_expired_key_does_not_block_add(self) -> None:
        self.client.storage("set", "reborn", b"old", exptime=-1)
        self.assertEqual(self.client.storage("add", "reborn", b"new"), b"STORED\r\n")
        self.assertEqual(self.client.get("reborn"), (0, b"new"))


class TestAddReplace(ServerTestCase):
    def test_add_missing_stores(self) -> None:
        self.assertEqual(self.client.storage("add", "fresh", b"v"), b"STORED\r\n")
        self.assertEqual(self.client.get("fresh"), (0, b"v"))

    def test_add_existing_not_stored_keeps_old(self) -> None:
        self.client.storage("set", "taken", b"old")
        self.assertEqual(self.client.storage("add", "taken", b"new"), b"NOT_STORED\r\n")
        self.assertEqual(self.client.get("taken"), (0, b"old"))

    def test_replace_existing_stores(self) -> None:
        self.client.storage("set", "rep", b"old")
        self.assertEqual(self.client.storage("replace", "rep", b"new"), b"STORED\r\n")
        self.assertEqual(self.client.get("rep"), (0, b"new"))

    def test_replace_missing_not_stored(self) -> None:
        self.assertEqual(
            self.client.storage("replace", "nope", b"v"), b"NOT_STORED\r\n")
        self.assertIsNone(self.client.get("nope"))

    def test_add_replace_noreply(self) -> None:
        self.assertIsNone(
            self.client.storage("add", "nr-add", b"v", noreply=True))
        self.assertEqual(self.client.get("nr-add"), (0, b"v"))
        self.assertIsNone(
            self.client.storage("replace", "nr-add", b"v2", noreply=True))
        self.assertEqual(self.client.get("nr-add"), (0, b"v2"))

    def test_page_step5_transcript(self) -> None:
        self.assertEqual(self.client.storage("set", "test", b"data"), b"STORED\r\n")
        self.assertEqual(self.client.storage("add", "test", b"test"), b"NOT_STORED\r\n")
        self.assertEqual(self.client.storage("replace", "test", b"john"), b"STORED\r\n")
        self.assertEqual(self.client.get("test"), (0, b"john"))
        self.assertEqual(
            self.client.storage("replace", "test2", b"data"), b"NOT_STORED\r\n")


class TestAppendPrepend(ServerTestCase):
    def test_page_step6_transcript(self) -> None:
        self.client.storage("set", "test", b"john")
        self.assertEqual(self.client.storage("append", "test", b"more"), b"STORED\r\n")
        self.assertEqual(self.client.get("test"), (0, b"johnmore"))
        self.assertEqual(self.client.storage("prepend", "test", b"send"), b"STORED\r\n")
        self.assertEqual(self.client.get("test"), (0, b"sendjohnmore"))
        self.assertEqual(self.client.storage("append", "foo", b"test"), b"NOT_STORED\r\n")
        self.assertEqual(
            self.client.storage("prepend", "foo", b"test"), b"NOT_STORED\r\n")

    def test_append_prepend_take_new_flags_and_exptime(self) -> None:
        self.client.storage("set", "fl", b"base", flags=9)
        self.client.storage("append", "fl", b"!", flags=3)
        self.assertEqual(self.client.get("fl"), (3, b"base!"))
        # Exptime from the append command applies: 1 s, then gone.
        self.client.storage("append", "fl", b"?", exptime=1)
        self.assertEqual(self.client.get("fl"), (0, b"base!?"))
        time.sleep(1.3)
        self.assertIsNone(self.client.get("fl"))


class TestDelete(ServerTestCase):
    def test_delete_existing(self) -> None:
        self.client.storage("set", "gone", b"v")
        self.assertEqual(self.client.delete("gone"), b"DELETED\r\n")
        self.assertIsNone(self.client.get("gone"))

    def test_delete_missing(self) -> None:
        self.assertEqual(self.client.delete("never-was"), b"NOT_FOUND\r\n")

    def test_delete_expired_is_not_found(self) -> None:
        self.client.storage("set", "exp", b"v", exptime=-1)
        self.assertEqual(self.client.delete("exp"), b"NOT_FOUND\r\n")

    def test_delete_noreply(self) -> None:
        self.client.storage("set", "quiet-del", b"v")
        self.assertIsNone(self.client.delete("quiet-del", noreply=True))
        self.assertIsNone(self.client.get("quiet-del"))


class TestErrorsAndRobustness(ServerTestCase):
    def test_unknown_command_error_connection_survives(self) -> None:
        self.client.send(b"bogus hello\r\n")
        self.assertEqual(self.client.read_until(b"\r\n"), b"ERROR\r\n")
        self.client.storage("set", "after", b"ok")
        self.assertEqual(self.client.get("after"), (0, b"ok"))

    def test_get_without_key_is_error(self) -> None:
        self.client.send(b"get\r\n")
        self.assertEqual(self.client.read_until(b"\r\n"), b"ERROR\r\n")

    def test_server_survives_client_disconnect(self) -> None:
        doomed = Client(self.port)
        doomed.storage("set", "before", b"v")
        doomed.close()
        self.assertEqual(self.client.get("before"), (0, b"v"))


class TestStartup(unittest.TestCase):
    def test_default_port_constant(self) -> None:
        self.assertEqual(DEFAULT_PORT, 11211)

    def test_ephemeral_server_accepts_connection(self) -> None:
        server = make_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5):
                pass
        finally:
            server.shutdown()
            server.server_close()

    def test_cli_dash_p_flag(self) -> None:
        # Find a free port, then launch the real CLI with -p <port>.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        script = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "memcached_server.py")
        proc = subprocess.Popen(
            [sys.executable, script, "-p", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.time() + 10
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port),
                                                  timeout=1):
                        break
                except OSError:
                    if time.time() > deadline:
                        raise
                    time.sleep(0.1)
            client = Client(port)
            try:
                self.assertEqual(client.storage("set", "cli", b"ok"), b"STORED\r\n")
                self.assertEqual(client.get("cli"), (0, b"ok"))
            finally:
                client.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            if proc.stdout is not None:
                proc.stdout.close()


if __name__ == "__main__":
    unittest.main()

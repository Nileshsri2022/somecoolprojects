"""Tests for scanner.py — localhost / loopback only, never external hosts.

Test servers bind to 127.0.0.1 on port 0 (ephemeral) and are closed
in tearDown. No live non-loopback connection is ever made: the
DNS-error and filtered cases monkeypatch socket.create_connection.
"""

import io
import socket
import threading
import unittest
from contextlib import redirect_stdout
from unittest import mock

import scanner


class LoopbackServer:
    """A listening TCP socket on 127.0.0.1:0 that accepts in background."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                self.sock.settimeout(0.2)
                conn, _ = self.sock.accept()
                conn.close()
            except (socket.timeout, OSError):
                pass

    def close(self):
        self._stop.set()
        self.sock.close()
        self._thread.join(timeout=2)


def free_port():
    """An ephemeral port that is closed again immediately after lookup."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestScanPort(unittest.TestCase):
    def setUp(self):
        self.server = LoopbackServer()

    def tearDown(self):
        self.server.close()

    def test_open(self):
        self.assertEqual(scanner.scan_port("127.0.0.1", self.server.port), "open")

    def test_closed(self):
        self.assertEqual(scanner.scan_port("127.0.0.1", free_port()), "closed")

    def test_filtered_on_timeout(self):
        with mock.patch("socket.create_connection", side_effect=TimeoutError):
            self.assertEqual(
                scanner.scan_port("127.0.0.1", self.server.port), "filtered")

    def test_error_on_dns_failure(self):
        # Mocked, not a live lookup: this sandbox's resolver intercepts
        # even .invalid names (resolves them to the egress proxy), so a
        # real gaierror cannot be produced here. The mock exercises the
        # same classification branch scan_port uses for gaierror.
        with mock.patch("socket.create_connection",
                        side_effect=socket.gaierror("Name or service not known")):
            self.assertEqual(
                scanner.scan_port("nonexistent.invalid", 80), "error")


class TestParsePorts(unittest.TestCase):
    def test_single(self):
        self.assertEqual(scanner.parse_ports("80"), [80])

    def test_list(self):
        self.assertEqual(scanner.parse_ports("443,80"), [80, 443])

    def test_range(self):
        self.assertEqual(scanner.parse_ports("8000-8002"), [8000, 8001, 8002])

    def test_mixed_dedup_sorted(self):
        self.assertEqual(scanner.parse_ports("90,80-81,80"), [80, 81, 90])

    def test_invalid(self):
        for bad in ("0", "65536", "10-5", "", "abc", "80,", "80-abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    scanner.parse_ports(bad)


class TestExpandHosts(unittest.TestCase):
    def test_single(self):
        self.assertEqual(scanner.expand_hosts("localhost"), ["localhost"])

    def test_list(self):
        self.assertEqual(scanner.expand_hosts("localhost,127.0.0.1"),
                         ["localhost", "127.0.0.1"])

    def test_wildcard(self):
        hosts = scanner.expand_hosts("127.0.0.*")
        self.assertEqual(len(hosts), 254)
        self.assertEqual(hosts[0], "127.0.0.1")
        self.assertEqual(hosts[-1], "127.0.0.254")

    def test_cidr(self):
        self.assertEqual(scanner.expand_hosts("127.0.0.0/30"),
                         ["127.0.0.1", "127.0.0.2"])

    def test_oversized_cidr_rejected(self):
        with self.assertRaises(ValueError):
            scanner.expand_hosts("10.0.0.0/16")


class TestScanHost(unittest.TestCase):
    def setUp(self):
        self.s1 = LoopbackServer()
        self.s2 = LoopbackServer()

    def tearDown(self):
        self.s1.close()
        self.s2.close()

    def test_mixed_states(self):
        closed = free_port()
        results = scanner.scan_host(
            "127.0.0.1", [self.s1.port, self.s2.port, closed])
        self.assertEqual(results[self.s1.port], "open")
        self.assertEqual(results[self.s2.port], "open")
        self.assertEqual(results[closed], "closed")


def run_cli(args):
    out = io.StringIO()
    with redirect_stdout(out):
        code = scanner.main(args)
    return code, out.getvalue()


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.server = LoopbackServer()

    def tearDown(self):
        self.server.close()

    def test_single_port_open(self):
        code, out = run_cli(["--host", "127.0.0.1",
                             "--port", str(self.server.port)])
        self.assertEqual(code, 0)
        self.assertIn("Scanning host: 127.0.0.1 port: %d" % self.server.port, out)
        self.assertIn("Port: %d is open" % self.server.port, out)

    def test_range_open_only_by_default(self):
        closed = free_port()
        code, out = run_cli(["--host", "127.0.0.1", "--ports",
                             "%d,%d" % (self.server.port, closed)])
        self.assertEqual(code, 0)
        self.assertIn("Port: %d is open" % self.server.port, out)
        self.assertNotIn("Port: %d is closed" % closed, out)

    def test_show_all_prints_closed(self):
        closed = free_port()
        code, out = run_cli(["--host", "127.0.0.1", "--ports",
                             "%d,%d" % (self.server.port, closed), "--show-all"])
        self.assertEqual(code, 0)
        self.assertIn("Port: %d is closed" % closed, out)

    def test_sweep_two_hosts(self):
        code, out = run_cli(["--host", "127.0.0.1,127.0.0.1",
                             "--port", str(self.server.port)])
        self.assertEqual(code, 0)
        self.assertEqual(out.count("Scanning host: 127.0.0.1"), 2)
        self.assertEqual(out.count("Port: %d is open" % self.server.port), 2)

    def test_bad_port_exits_nonzero(self):
        for bad in ("0", "70000"):
            with self.subTest(bad=bad):
                with self.assertRaises(SystemExit) as ctx:
                    run_cli(["--host", "127.0.0.1", "--port", bad])
                self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

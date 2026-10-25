#!/usr/bin/env python3
"""Tests for echo_server.py. Ephemeral ports only, 127.0.0.1 only.

Run: python3 -m unittest discover -s tests -v   (from echo-server/)
Subprocess tests signal the child's explicit Popen PID only; no pkill.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from echo_server import TCPServer, UDPServer, parse_args  # noqa: E402

HOST = "127.0.0.1"
SERVER_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "echo_server.py",
)


def recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            break
        data += chunk
    return data


class TCPTestBase(unittest.TestCase):
    def setUp(self):
        self.server = TCPServer(HOST, 0)
        self.server.start()
        self.port = self.server.actual_port

    def tearDown(self):
        self.server.stop()

    def connect(self):
        sock = socket.create_connection((HOST, self.port), timeout=5)
        self.addCleanup(sock.close)
        return sock


class TestTCPEcho(TCPTestBase):
    def test_tcp_single_message_echo(self):
        sock = self.connect()
        sock.sendall(b"Hello, Coding Challenges")
        self.assertEqual(recv_exact(sock, 24), b"Hello, Coding Challenges")

    def test_tcp_multiple_messages_same_connection(self):
        sock = self.connect()
        for msg in (b"one", b"two", b"three"):
            sock.sendall(msg)
            self.assertEqual(recv_exact(sock, len(msg)), msg)

    def test_tcp_binary_and_large_payload(self):
        sock = self.connect()
        payload = bytes(range(256)) * 16
        sock.sendall(payload)
        self.assertEqual(recv_exact(sock, len(payload)), payload)
        big = b"Z" * (1024 * 1024)
        sock.sendall(big)
        self.assertEqual(recv_exact(sock, len(big)), big)

    def test_tcp_concurrent_clients(self):
        results = {}
        errors = []

        def client(i):
            try:
                sock = self.connect()
                msg = f"client-{i}-message".encode()
                sock.sendall(msg)
                results[i] = recv_exact(sock, len(msg))
                sock.close()
            except Exception as exc:  # noqa: BLE001 - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=client, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        for i in range(5):
            self.assertEqual(results[i], f"client-{i}-message".encode())

    def test_tcp_server_stays_up_after_disconnect(self):
        sock = self.connect()
        sock.sendall(b"first")
        self.assertEqual(recv_exact(sock, 5), b"first")
        sock.close()
        time.sleep(0.2)
        sock2 = self.connect()
        sock2.sendall(b"second")
        self.assertEqual(recv_exact(sock2, 6), b"second")


class TestTCPSubprocess(unittest.TestCase):
    def start_server(self, extra_args):
        proc = subprocess.Popen(
            [sys.executable, SERVER_FILE, "--host", HOST, "--port", "0"]
            + extra_args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

        def _cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()

        self.addCleanup(_cleanup)
        # Port 0 prints the real port; read the first line for it.
        line = proc.stdout.readline()
        self.assertIn("Echo server listening on :", line)
        port = int(line.rsplit(":", 1)[1].strip())
        return proc, port

    def test_tcp_accept_log_message(self):
        proc, port = self.start_server([])
        try:
            sock = socket.create_connection((HOST, port), timeout=5)
            sock.sendall(b"hi")
            self.assertEqual(recv_exact(sock, 2), b"hi")
            sock.close()
            time.sleep(0.3)
        finally:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
        out = proc.stdout.read()
        self.assertIn(f"Accepted connection from: {HOST}:", out)

    def test_tcp_clean_shutdown_via_sigint(self):
        proc, port = self.start_server([])
        sock = socket.create_connection((HOST, port), timeout=5)
        sock.sendall(b"ping")
        self.assertEqual(recv_exact(sock, 4), b"ping")
        proc.send_signal(signal.SIGINT)  # explicit PID only, no pkill
        self.assertEqual(proc.wait(timeout=5), 0)
        sock.close()
        self.assertIn("Server shutting down", proc.stdout.read())


class TestCLI(unittest.TestCase):
    def test_cli_udp_flag_parses(self):
        self.assertTrue(parse_args(["--udp"]).udp)
        self.assertTrue(parse_args(["-udp"]).udp)
        self.assertFalse(parse_args([]).udp)
        self.assertFalse(parse_args(["--tcp"]).udp)
        self.assertEqual(parse_args(["--port", "7007"]).port, 7007)


class TestUDPEcho(unittest.TestCase):
    def test_udp_datagram_echo(self):
        try:
            server = UDPServer(HOST, 0)
            server.start()
        except PermissionError as exc:
            self.skipTest(f"UDP loopback blocked in this sandbox: {exc}")
        except OSError as exc:
            self.skipTest(f"UDP unavailable in this sandbox: {exc}")
        try:
            port = server.actual_port
            try:
                for msg in (b"Hi Coding Challenges", b"second datagram"):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(5)
                    try:
                        sock.sendto(msg, (HOST, port))
                        data, _addr = sock.recvfrom(65535)
                        self.assertEqual(data, msg)
                    finally:
                        sock.close()
            except PermissionError as exc:
                # UDP send is blocked in this sandbox even though the
                # bind succeeded; skip honestly rather than faking it.
                self.skipTest(f"UDP loopback blocked in this sandbox: {exc}")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

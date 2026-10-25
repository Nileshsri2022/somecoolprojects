"""Tests for chat.py: real server on an ephemeral port, real sockets.

Run from the project directory:
    python3 -m unittest discover -s tests -v
"""

import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chat import ChatServer, WELCOME  # noqa: E402


class RawClient:
    """Minimal line client: first line sent is the nickname."""

    def __init__(self, port, name):
        self.sock = socket.create_connection(("127.0.0.1", port))
        self.sock.settimeout(5)
        self.buf = b""
        self.send(name)
        self.welcome = self.recv_line()
        # Drain nothing else; join notices go to *other* clients.

    def send(self, line):
        self.sock.sendall((line + "\n").encode("utf-8"))

    def recv_line(self, timeout=2):
        self.sock.settimeout(timeout)
        try:
            while b"\n" not in self.buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                self.buf += chunk
        except socket.timeout:
            return None
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8")

    def drain(self, timeout=0.3):
        """Collect lines arriving within timeout; [] if none."""
        lines = []
        while True:
            line = self.recv_line(timeout=timeout)
            if line is None:
                return lines
            lines.append(line)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class ChatTestBase(unittest.TestCase):
    echo = False

    def setUp(self):
        self.server = ChatServer("127.0.0.1", 0, echo=self.echo).start()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.stop()

    def connect(self, name):
        client = RawClient(self.server.port, name)
        self.clients.append(client)
        return client

    def wait_for_count(self, n, timeout=2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.server.client_count == n:
                return True
            time.sleep(0.02)
        return self.server.client_count == n


class TestChatServer(ChatTestBase):
    def test_welcome_message(self):
        alice = self.connect("Alice")
        self.assertEqual(alice.welcome, WELCOME)

    def test_broadcast_reaches_others_not_sender(self):
        alice = self.connect("Alice")
        bob = self.connect("Bob")
        alice.drain()  # Bob's join notice
        bob.drain()
        alice.send("Hello Bob")
        self.assertEqual(bob.recv_line(), "Alice: Hello Bob")
        self.assertEqual(alice.drain(), [])  # sender excluded
        bob.send("Hi Alice")
        self.assertEqual(alice.recv_line(), "Bob: Hi Alice")
        self.assertEqual(bob.drain(), [])

    def test_three_way_broadcast(self):
        alice = self.connect("Alice")
        bob = self.connect("Bob")
        carol = self.connect("Carol")
        for client in (alice, bob, carol):
            client.drain()
        alice.send("to everyone")
        self.assertEqual(bob.recv_line(), "Alice: to everyone")
        self.assertEqual(carol.recv_line(), "Alice: to everyone")
        self.assertEqual(alice.drain(), [])

    def test_join_notice(self):
        alice = self.connect("Alice")
        self.connect("Bob")
        self.assertEqual(alice.recv_line(), "Bob has joined the chatroom.")

    def test_disconnect_leave_notice_and_others_keep_chatting(self):
        alice = self.connect("Alice")
        bob = self.connect("Bob")
        carol = self.connect("Carol")
        for client in (alice, bob, carol):
            client.drain()
        bob.close()
        self.clients.remove(bob)
        self.assertEqual(alice.recv_line(), "Bob has left the chatroom.")
        self.assertEqual(carol.recv_line(), "Bob has left the chatroom.")
        self.assertTrue(self.wait_for_count(2))
        alice.send("still here?")
        self.assertEqual(carol.recv_line(), "Alice: still here?")

    def test_empty_lines_ignored(self):
        alice = self.connect("Alice")
        bob = self.connect("Bob")
        alice.drain()
        bob.drain()
        alice.send("")
        self.assertEqual(bob.drain(), [])

    def test_server_stop_refuses_new_connections(self):
        self.server.stop()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.server.port),
                                     timeout=2)


class TestEchoServer(ChatTestBase):
    echo = True

    def test_echo_returns_lines_to_sender(self):
        alice = self.connect("Alice")
        alice.send("test")
        self.assertEqual(alice.recv_line(), "test")
        alice.send("again")
        self.assertEqual(alice.recv_line(), "again")


class TestCliClient(ChatTestBase):
    def test_cli_client_sends_and_exits_on_exit(self):
        chat_py = str(Path(__file__).resolve().parent.parent / "chat.py")
        proc = subprocess.Popen(
            [sys.executable, chat_py, "client",
             "--host", "127.0.0.1", "--port", str(self.server.port)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            out, _err = proc.communicate("Dana\nHello world\nexit\n",
                                         timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode, 0)
        self.assertIn(WELCOME, out)
        self.assertIn("Dana: Hello world", out)


if __name__ == "__main__":
    unittest.main()

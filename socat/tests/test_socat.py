#!/usr/bin/env python3
"""Tests for socat.py. Loopback only, ephemeral ports only.

Listener processes are subprocess.Popen objects stopped explicitly by
PID (proc.terminate()); helper servers are daemon threads whose sockets
are closed in tearDown. No pkill, no fixed ports.
"""

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SOCAT = os.path.join(os.path.dirname(__file__), "..", "socat.py")


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_socat(args, input_data=None, timeout=15):
    return subprocess.run(
        [sys.executable, SOCAT] + args,
        input=input_data, capture_output=True, timeout=timeout,
    )


class EchoServer(threading.Thread):
    """TCP echo server: echoes until client half-closes, then closes."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(5)

    def run(self):
        try:
            while True:
                conn, _ = self.sock.accept()
                threading.Thread(target=self._handle, args=(conn,),
                                 daemon=True).start()
        except OSError:
            pass

    @staticmethod
    def _handle(conn):
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                conn.sendall(data)
        except OSError:
            pass
        finally:
            conn.close()

    def stop(self):
        self.sock.close()


class GreetingServer(threading.Thread):
    """Sends a greeting, then closes."""

    def __init__(self, port, greeting=b"hello-from-server\n"):
        super().__init__(daemon=True)
        self.port = port
        self.greeting = greeting
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(5)

    def run(self):
        try:
            while True:
                conn, _ = self.sock.accept()
                try:
                    conn.sendall(self.greeting)
                except OSError:
                    pass
                conn.close()
        except OSError:
            pass

    def stop(self):
        self.sock.close()


class CaptureServer(threading.Thread):
    """TCP server that records everything received."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.received = bytearray()
        self.done = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(5)

    def run(self):
        try:
            conn, _ = self.sock.accept()
            try:
                while True:
                    data = conn.recv(65536)
                    if not data:
                        break
                    self.received += data
            except OSError:
                pass
            finally:
                conn.close()
            self.done.set()
        except OSError:
            self.done.set()

    def stop(self):
        self.sock.close()
        self.done.set()


class SocatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.servers = []
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
            for stream in (p.stdin, p.stdout, p.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
        for s in self.servers:
            s.stop()
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def start(self, args, **kw):
        p = subprocess.Popen([sys.executable, SOCAT] + args,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, **kw)
        self.procs.append(p)
        return p

    # ---- CLI / parsing ----

    def test_help(self):
        r = run_socat(["-h"])
        self.assertEqual(r.returncode, 0)
        for word in (b"STDIO", b"TCP", b"FILE", b"EXEC"):
            self.assertIn(word, r.stdout)

    def test_missing_second_address(self):
        r = run_socat(["STDIO"])
        self.assertNotEqual(r.returncode, 0)

    def test_unknown_address_type(self):
        r = run_socat(["NOPE:x", "STDIO"])
        self.assertNotEqual(r.returncode, 0)

    def test_unknown_option(self):
        r = run_socat(["-u", "STDIO", f"FILE:{self.path('o')},badopt"],
                      input_data=b"x")
        self.assertNotEqual(r.returncode, 0)

    def test_append_and_trunc_conflict(self):
        r = run_socat(["-u", "STDIO",
                       f"FILE:{self.path('o')},create,append,trunc"],
                      input_data=b"x")
        self.assertNotEqual(r.returncode, 0)

    def test_missing_file_without_create(self):
        r = run_socat(["-u", "STDIO", f"FILE:{self.path('nope')}"],
                      input_data=b"x")
        self.assertNotEqual(r.returncode, 0)

    # ---- Step 2: file ----

    def test_stdio_to_file_create(self):
        out = self.path("test.txt")
        r = run_socat(["-u", "STDIO", f"FILE:{out},create"],
                      input_data=b"Hello Coding Challenges\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"Hello Coding Challenges\n")

    def test_stdio_to_file_append(self):
        out = self.path("a.txt")
        with open(out, "wb") as f:
            f.write(b"first\n")
        r = run_socat(["-u", "STDIO", f"FILE:{out},append"],
                      input_data=b"second\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"first\nsecond\n")

    def test_stdio_to_file_trunc(self):
        out = self.path("t.txt")
        with open(out, "wb") as f:
            f.write(b"old content that is longer\n")
        r = run_socat(["-u", "STDIO", f"FILE:{out},trunc"],
                      input_data=b"new\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"new\n")

    def test_file_to_stdio(self):
        src = self.path("in.txt")
        with open(src, "wb") as f:
            f.write(b"file bytes \x00\xff\n")
        r = run_socat(["-u", f"FILE:{src}", "STDIO"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"file bytes \x00\xff\n")

    def test_open_alias_and_creat_spelling(self):
        out = self.path("log.txt")
        r = run_socat(["-u", "STDIO", f"OPEN:{out},creat,append"],
                      input_data=b"via open\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"via open\n")

    def test_stdin_alias(self):
        out = self.path("s.txt")
        r = run_socat(["-u", "STDIN", f"FILE:{out},create"],
                      input_data=b"stdin alias\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"stdin alias\n")

    # ---- Step 1: TCP connect ----

    def test_tcp_connect_echo(self):
        port = free_port()
        srv = EchoServer(port)
        srv.start()
        self.servers.append(srv)
        r = run_socat(["-", f"TCP4:127.0.0.1:{port}"],
                      input_data=b"ping via tcp\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"ping via tcp\n")

    def test_tcp_spelling(self):
        port = free_port()
        srv = EchoServer(port)
        srv.start()
        self.servers.append(srv)
        r = run_socat(["STDIO", f"TCP:127.0.0.1:{port}"],
                      input_data=b"tcp spelling\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"tcp spelling\n")

    def test_unidirectional_tcp_to_stdio(self):
        # -u is left -> right, so TCP (left) -> STDIO (right) prints the
        # server greeting. (-U would be STDIO -> TCP, i.e. reading stdin,
        # which is a different direction and must not be used here.)
        port = free_port()
        srv = GreetingServer(port)
        srv.start()
        self.servers.append(srv)
        r = run_socat(["-u", f"TCP:127.0.0.1:{port}", "STDIO"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"hello-from-server\n")

    def test_reverse_unidirectional_stdio_to_tcp(self):
        # -U is right -> left: STDIO (right) -> TCP (left) sends stdin to
        # a capture server.
        port = free_port()
        srv = CaptureServer(port)
        srv.start()
        self.servers.append(srv)
        r = run_socat(["-U", f"TCP:127.0.0.1:{port}", "STDIO"],
                      input_data=b"reverse direction\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(srv.done.wait(timeout=5))
        self.assertEqual(bytes(srv.received), b"reverse direction\n")

    # ---- Step 3: TCP listen / log collector ----

    def test_tcp_listen_fork_log_collector(self):
        port = free_port()
        logpath = self.path("test.log")
        p = self.start(["-u", f"TCP4-LISTEN:{port},reuseaddr,fork",
                        f"OPEN:{logpath},creat,append"])
        time.sleep(0.5)
        self.assertIsNone(p.poll(), "collector exited early")
        for i in range(1, 4):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
                s.sendall(f"Hello, Coding Challenges Log Message {i}\n".encode())
        # Give forked handlers time to flush.
        deadline = time.time() + 5
        lines = []
        while time.time() < deadline:
            if os.path.exists(logpath):
                with open(logpath, "rb") as f:
                    lines = f.read().decode().splitlines()
                if len(lines) >= 3:
                    break
            time.sleep(0.2)
        p.terminate()
        p.wait(timeout=5)
        self.assertEqual(
            sorted(lines),
            [f"Hello, Coding Challenges Log Message {i}" for i in range(1, 4)])

    def test_tcp_listen_reuseaddr_rebind(self):
        port = free_port()
        logpath = self.path("r.log")
        p = self.start(["-u", f"TCP4-LISTEN:{port},reuseaddr,fork",
                        f"OPEN:{logpath},creat,append"])
        time.sleep(0.4)
        p.terminate()
        p.wait(timeout=5)
        self.procs.remove(p)
        for stream in (p.stdin, p.stdout, p.stderr):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        p2 = self.start(["-u", f"TCP4-LISTEN:{port},reuseaddr,fork",
                         f"OPEN:{logpath},creat,append"])
        time.sleep(0.4)
        self.assertIsNone(p2.poll(), "rebind with reuseaddr failed")
        p2.terminate()
        p2.wait(timeout=5)

    def test_tcp_listen_single_connection_exits(self):
        port = free_port()
        out = self.path("one.txt")
        p = self.start(["-u", f"TCP-LISTEN:{port},reuseaddr",
                        f"FILE:{out},create"])
        time.sleep(0.4)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"one shot\n")
        rc = p.wait(timeout=5)
        self.assertEqual(rc, 0)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"one shot\n")

    # ---- Step 4: EXEC ----

    def test_exec_to_file(self):
        out = self.path("exec.txt")
        r = run_socat(["-u", "EXEC:'echo hello-exec'", f"FILE:{out},create"])
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"hello-exec\n")

    def test_exec_to_tcp_capture(self):
        port = free_port()
        srv = CaptureServer(port)
        srv.start()
        self.servers.append(srv)
        r = run_socat(["-u", "EXEC:'printf log-line-1'",
                       f"TCP4:127.0.0.1:{port}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(srv.done.wait(timeout=5))
        self.assertEqual(bytes(srv.received), b"log-line-1")

    # ---- Going Further: UDP ----

    def test_udp_send_to_capture(self):
        # One-way UDP send: stdin -> UDP datagram -> capture server.
        # A UDP echo round-trip is NOT asserted here: in this sandbox the
        # reply direction is blocked (server sendto to a loopback client
        # port raises PermissionError / is swallowed), while the send
        # direction to a bound port works. Echo round-trip is a manual
        # check on a normal machine (see TEST_PLAN.md).
        port = free_udp_port()
        received = []
        done = threading.Event()
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", port))

        def capture():
            try:
                data, _ = srv.recvfrom(65535)
                received.append(data)
            except OSError:
                pass
            finally:
                done.set()

        threading.Thread(target=capture, daemon=True).start()
        r = run_socat(["-u", "STDIO", f"UDP:127.0.0.1:{port}"],
                      input_data=b"udp payload\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(done.wait(timeout=5))
        self.assertEqual(received, [b"udp payload\n"])
        srv.close()

    def test_udp_listen_to_file(self):
        # Same UDP caveat: the listener has no way to know the sender is
        # done, so it runs until terminated explicitly by PID.
        port = free_udp_port()
        out = self.path("udp.txt")
        p = self.start(["-u", f"UDP-LISTEN:{port}", f"FILE:{out},create"])
        time.sleep(0.4)
        # Connected send, not sendto: this sandbox blocks unconnected
        # UDP sendto (PermissionError) but permits a connected send.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("127.0.0.1", port))
            s.send(b"datagram payload")
        deadline = time.time() + 5
        content = b""
        while time.time() < deadline:
            if os.path.exists(out):
                with open(out, "rb") as f:
                    content = f.read()
                if content:
                    break
            time.sleep(0.2)
        p.terminate()
        p.wait(timeout=5)
        self.assertEqual(content, b"datagram payload")


if __name__ == "__main__":
    unittest.main()

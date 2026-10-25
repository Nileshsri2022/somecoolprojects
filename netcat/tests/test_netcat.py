"""Tests for netcat.py. Localhost ephemeral ports only; no external hosts.

System nc is used only for interop tests, skipped if absent.
Every spawned process is terminated explicitly by PID (Popen object),
never via pkill.
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NC = os.path.join(ROOT, "netcat.py")
sys.path.insert(0, ROOT)

from netcat import format_hexdump, parse_args, parse_ports  # noqa: E402

NC_BIN = shutil.which("nc")


def _udp_available():
    """Probe: this sandbox blocks UDP sendto with EPERM, so UDP
    integration tests must skip there rather than hang/fail.
    The probe itself is a localhost-only UDP round-trip."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        srv.bind(("127.0.0.1", 0))
        srv.settimeout(2)
        cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cli.settimeout(2)
        cli.sendto(b"probe", srv.getsockname())
        data, addr = srv.recvfrom(100)
        srv.sendto(b"pong", addr)
        assert cli.recv(100) == b"pong"
        return True
    except OSError:
        return False
    finally:
        try:
            srv.close()
        except Exception:
            pass
        try:
            cli.close()
        except Exception:
            pass


UDP_AVAILABLE = _udp_available()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_ccnc(args, **kw):
    kw.setdefault("stdin", subprocess.PIPE)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    return subprocess.Popen([sys.executable, NC] + args, **kw)


def read_line_timeout(f, timeout=5):
    """Read one line from a pipe with a deadline, so a buffering
    peer fails the test instead of hanging the suite forever."""
    import select
    ready, _, _ = select.select([f], [], [], timeout)
    if not ready:
        raise AssertionError("timed out waiting for a line on %r" % (f,))
    return f.readline()


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


class HexdumpTests(unittest.TestCase):
    def test_page_example_received(self):
        data = b"Hello from the client\n"
        self.assertEqual(len(data), 22)
        lines = format_hexdump(data)
        self.assertEqual(
            lines[0],
            "00000000  48 65 6C 6C  6F 20 66 72  6F 6D 20 74  "
            "68 65 20 63  Hello from the c")
        self.assertEqual(
            lines[1],
            "00000010  6C 69 65 6E  74 0A"
            "                                  lient.")

    def test_page_example_sent(self):
        data = b"Response from the server\n"
        self.assertEqual(len(data), 25)
        lines = format_hexdump(data)
        self.assertTrue(lines[0].endswith("Response from th"))
        self.assertTrue(lines[1].endswith("e server."))
        self.assertTrue(lines[1].startswith("00000010"))

    def test_empty_and_nonprintable(self):
        self.assertEqual(format_hexdump(b""), [])
        line = format_hexdump(b"\x00\xffA")[0]
        self.assertTrue(line.endswith("..A"))

    def test_exactly_16_bytes(self):
        self.assertEqual(len(format_hexdump(b"0123456789abcdef")), 1)


class ParseTests(unittest.TestCase):
    def test_tcp_listen(self):
        o = parse_args(["-l", "-p", "8888"])
        self.assertTrue(o.listen)
        self.assertEqual(o.port, 8888)
        self.assertFalse(o.udp)

    def test_page_step2_ordering(self):
        # The page prints: ccnc -l -p -u 8888
        o = parse_args(["-l", "-p", "-u", "8888"])
        self.assertTrue(o.listen and o.udp)
        self.assertEqual(o.port, 8888)

    def test_attached_and_combined(self):
        o = parse_args(["-lv", "-p8888"])
        self.assertTrue(o.listen and o.verbose)
        self.assertEqual(o.port, 8888)

    def test_scan_range(self):
        o = parse_args(["-z", "localhost", "8880-8890"])
        self.assertTrue(o.scan)
        self.assertEqual(parse_ports(o.portspec), list(range(8880, 8891)))

    def test_execute(self):
        o = parse_args(["-l", "-p", "8888", "-e", "/bin/cat"])
        self.assertEqual(o.execute, "/bin/cat")

    def test_errors(self):
        # parse_args itself validates listen ports and flags;
        # port-spec validation lives in parse_ports (used by
        # scan/client modes, which turn it into exit code 2).
        for args in (["-l"], ["-l", "-p", "0"], ["-l", "-p", "99999"],
                     ["-q"], []):
            with self.assertRaises(ValueError, msg=str(args)):
                parse_args(args)
        for spec in ("8890-8880", "abc", "0", "99999"):
            with self.assertRaises(ValueError, msg=spec):
                parse_ports(spec)


class TcpTests(unittest.TestCase):
    def test_listen_both_directions(self):
        port = free_port()
        srv = start_ccnc(["-v", "-l", "-p", str(port)])
        try:
            self.assertIn(b"Listening", srv.stderr.readline())
            client = socket.create_connection(("127.0.0.1", port))
            try:
                client.sendall(b"Hello from the client\n")
                self.assertEqual(srv.stdout.readline(),
                                 b"Hello from the client\n")
                srv.stdin.write(b"Response from the server\n")
                srv.stdin.flush()
                self.assertEqual(client.recv(4096),
                                 b"Response from the server\n")
            finally:
                client.close()
            srv.wait(timeout=5)
            self.assertEqual(srv.returncode, 0)
        finally:
            stop(srv)

    def test_client_against_echo_server(self):
        port = free_port()
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(1)

        def serve():
            conn, _ = listener.accept()
            try:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    conn.sendall(data)
            finally:
                conn.close()
                listener.close()

        threading.Thread(target=serve, daemon=True).start()
        out = subprocess.run(
            [sys.executable, NC, "127.0.0.1", str(port)],
            input=b"hello tcp\n", capture_output=True, timeout=10)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, b"hello tcp\n")

    def test_verbose_client_message(self):
        port = free_port()
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(1)

        def serve():
            conn, _ = listener.accept()
            # Client shuts down its write side on stdin EOF;
            # closing here lets the client exit cleanly.
            conn.recv(4096)
            conn.close()
            listener.close()

        threading.Thread(target=serve, daemon=True).start()
        out = subprocess.run(
            [sys.executable, NC, "-v", "127.0.0.1", str(port)],
            input=b"", capture_output=True, timeout=10)
        self.assertEqual(out.returncode, 0)
        self.assertIn(b"Connection to 127.0.0.1 port %d [tcp] succeeded!"
                      % port, out.stderr)


@unittest.skipUnless(UDP_AVAILABLE,
                     "UDP loopback blocked in this sandbox (EPERM on sendto)")
class UdpTests(unittest.TestCase):
    def test_listen_both_directions(self):
        port = free_port()
        srv = start_ccnc(["-v", "-u", "-l", "-p", str(port)])
        try:
            self.assertIn(b"Listening", srv.stderr.readline())
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(5)
            try:
                client.sendto(b"hello udp\n", ("127.0.0.1", port))
                self.assertEqual(srv.stdout.readline(), b"hello udp\n")
                srv.stdin.write(b"back udp\n")
                srv.stdin.flush()
                self.assertEqual(client.recv(4096), b"back udp\n")
            finally:
                client.close()
        finally:
            stop(srv)

    def test_client_against_udp_echo(self):
        port = free_port()
        echo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        echo.bind(("127.0.0.1", port))
        echo.settimeout(5)
        stop_flag = threading.Event()

        def serve():
            while not stop_flag.is_set():
                try:
                    data, addr = echo.recvfrom(4096)
                except socket.timeout:
                    continue
                echo.sendto(data, addr)

        threading.Thread(target=serve, daemon=True).start()
        cli = start_ccnc(["-u", "127.0.0.1", str(port)])
        try:
            cli.stdin.write(b"hello udp client\n")
            cli.stdin.flush()
            self.assertEqual(cli.stdout.readline(), b"hello udp client\n")
        finally:
            stop_flag.set()
            stop(cli)
            echo.close()


class ScanTests(unittest.TestCase):
    def test_single_and_range_and_closed(self):
        port = free_port()
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(5)
        listener.settimeout(2)

        def accept_loop():
            try:
                while True:
                    conn, _ = listener.accept()
                    conn.close()
            except (socket.timeout, OSError):
                pass

        threading.Thread(target=accept_loop, daemon=True).start()
        try:
            out = subprocess.run(
                [sys.executable, NC, "-z", "127.0.0.1", str(port)],
                capture_output=True, timeout=10)
            self.assertEqual(out.returncode, 0)
            self.assertIn(b"port %d [tcp] succeeded!" % port, out.stderr)

            out = subprocess.run(
                [sys.executable, NC, "-z", "127.0.0.1",
                 "%d-%d" % (port - 1, port + 1)],
                capture_output=True, timeout=10)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stderr.count(b"succeeded!"), 1)
            self.assertIn(b"port %d [tcp] succeeded!" % port, out.stderr)

            closed = free_port()
            out = subprocess.run(
                [sys.executable, NC, "-z", "127.0.0.1", str(closed)],
                capture_output=True, timeout=10)
            self.assertEqual(out.returncode, 1)
            self.assertNotIn(b"succeeded!", out.stderr)
            out = subprocess.run(
                [sys.executable, NC, "-vz", "127.0.0.1", str(closed)],
                capture_output=True, timeout=10)
            self.assertEqual(out.returncode, 1)
            self.assertIn(b"failed:", out.stderr)
        finally:
            listener.close()


class ExecuteTests(unittest.TestCase):
    def test_execute_cat(self):
        port = free_port()
        srv = start_ccnc(["-v", "-l", "-p", str(port), "-e", "/bin/cat"])
        try:
            self.assertIn(b"Listening", srv.stderr.readline())
            client = socket.create_connection(("127.0.0.1", port))
            try:
                # "Connection from ..." (verbose, in run_listen)
                # precedes the warning printed in run_execute.
                self.assertIn(b"Connection from", srv.stderr.readline())
                self.assertIn(b"WARNING", srv.stderr.readline())
                client.sendall(b"via cat\n")
                self.assertEqual(client.recv(4096), b"via cat\n")
            finally:
                client.close()
            srv.wait(timeout=5)
            self.assertEqual(srv.returncode, 0)
        finally:
            stop(srv)


class HexdumpIntegrationTests(unittest.TestCase):
    def test_x_dump_on_listen(self):
        port = free_port()
        srv = start_ccnc(["-v", "-x", "-l", "-p", str(port)])
        try:
            self.assertIn(b"Listening", srv.stderr.readline())
            client = socket.create_connection(("127.0.0.1", port))
            try:
                client.sendall(b"Hello from the client\n")
                self.assertEqual(srv.stdout.readline(),
                                 b"Hello from the client\n")
                # "Connection from ..." (verbose) precedes the dump
                # lines on stderr; dump lines follow, in page format.
                self.assertIn(b"Connection from", srv.stderr.readline())
                header = srv.stderr.readline()
                self.assertIn(b"Received 22 bytes from the socket", header)
                first = srv.stderr.readline()
                self.assertTrue(first.startswith(b"00000000"))
                self.assertIn(b"48 65 6C 6C", first)
                self.assertTrue(first.rstrip(b"\n").endswith(
                    b"Hello from the c"))
            finally:
                client.close()
            srv.wait(timeout=5)
        finally:
            stop(srv)


class ErrorTests(unittest.TestCase):
    def test_no_args_and_bad_connect(self):
        out = subprocess.run([sys.executable, NC],
                             capture_output=True, timeout=10)
        self.assertEqual(out.returncode, 2)
        out = subprocess.run(
            [sys.executable, NC, "127.0.0.1", str(free_port())],
            input=b"", capture_output=True, timeout=10)
        self.assertEqual(out.returncode, 1)


@unittest.skipUnless(NC_BIN, "system nc not installed")
class NcInteropTests(unittest.TestCase):
    def test_nc_client_to_our_listener(self):
        port = free_port()
        srv = start_ccnc(["-v", "-l", "-p", str(port)])
        nc = None
        try:
            self.assertIn(b"Listening", srv.stderr.readline())
            nc = subprocess.Popen([NC_BIN, "127.0.0.1", str(port)],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            nc.stdin.write(b"via nc\n")
            nc.stdin.flush()
            self.assertEqual(srv.stdout.readline(), b"via nc\n")
            srv.stdin.write(b"back\n")
            srv.stdin.flush()
            self.assertEqual(read_line_timeout(nc.stdout), b"back\n")
        finally:
            if nc is not None:
                stop(nc)
            stop(srv)

    def test_our_client_to_nc_listener(self):
        port = free_port()
        nc = subprocess.Popen([NC_BIN, "-l", "127.0.0.1", str(port)],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        try:
            time.sleep(0.5)
            cli = start_ccnc(["127.0.0.1", str(port)])
            try:
                cli.stdin.write(b"from ccnc\n")
                cli.stdin.flush()
                self.assertEqual(read_line_timeout(nc.stdout),
                                 b"from ccnc\n")
            finally:
                stop(cli)
        finally:
            stop(nc)

    def test_scan_against_nc_listener(self):
        port = free_port()
        nc = subprocess.Popen([NC_BIN, "-l", "127.0.0.1", str(port)],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        try:
            time.sleep(0.5)
            out = subprocess.run(
                [sys.executable, NC, "-z", "127.0.0.1", str(port)],
                capture_output=True, timeout=10)
            self.assertEqual(out.returncode, 0)
            self.assertIn(b"succeeded!", out.stderr)
        finally:
            stop(nc)


if __name__ == "__main__":
    unittest.main()

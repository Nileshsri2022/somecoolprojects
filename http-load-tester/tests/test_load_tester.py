#!/usr/bin/env python3
"""Tests for load_tester.py. Local servers only, ephemeral ports,
deterministic endpoints; no real-time assertions for correctness
(see docs/TEST_PLAN.md)."""

import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import load_tester  # noqa: E402
from load_tester import (RequestResult, compute_stats, do_request,  # noqa: E402
                         format_summary, run_load, summarise)

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(os.path.dirname(HERE), "load_tester.py")


class CountingHandler(BaseHTTPRequestHandler):
    counts = {}
    lock = threading.Lock()
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _count(self):
        with self.lock:
            self.counts[self.path] = self.counts.get(self.path, 0) + 1

    def _send(self, code, body=b"ok"):
        self._count()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass  # client timed out / went away; expected in tests

    def do_GET(self):
        if self.path == "/slow":
            time.sleep(0.2)
            self._send(200)
        elif self.path == "/error":
            self._send(500, b"boom")
        elif self.path == "/notfound":
            self._send(404, b"nope")
        elif self.path == "/redirect":
            self._count()
            self.send_response(301)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:  # /ok and anything else
            self._send(200)


def start_server(handler=CountingHandler, secure=False, certfile=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    if secure:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        CountingHandler.counts = {}
        self.server = start_server()
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


# ---- pure stats -----------------------------------------------------

class TestStats(unittest.TestCase):
    def test_min_max_mean(self):
        s = compute_stats([0.1, 0.2, 0.3])
        self.assertAlmostEqual(s["min"], 0.1)
        self.assertAlmostEqual(s["max"], 0.3)
        self.assertAlmostEqual(s["mean"], 0.2)

    def test_percentiles_nearest_rank(self):
        s = compute_stats([float(i) for i in range(1, 11)])
        self.assertEqual(s["p50"], 5.0)
        self.assertEqual(s["p90"], 9.0)
        self.assertEqual(s["p99"], 10.0)

    def test_empty_list(self):
        s = compute_stats([])
        self.assertTrue(all(v is None for v in s.values()))

    def test_summarise_counts(self):
        results = [RequestResult(url="u", status=200, total=0.1,
                                 ttfb=0.05, ttlb=0.05),
                   RequestResult(url="u", status=500, total=0.2,
                                 ttfb=0.1, ttlb=0.1),
                   RequestResult(url="u", status=None, error="refused")]
        s = summarise(results, wall_time=1.0)
        self.assertEqual(s.total, 3)
        self.assertEqual(s.successes, 1)
        self.assertEqual(s.failures, 2)
        self.assertEqual(s.failed_5xx, 1)
        self.assertEqual(s.status_counts, {200: 1, 500: 1})
        self.assertEqual(s.error_count, 1)
        self.assertAlmostEqual(s.requests_per_second, 3.0)
        self.assertAlmostEqual(s.total_stats["mean"], 0.15)
        text = format_summary(s)
        self.assertIn("Total Requests (2XX)", text)
        self.assertIn("200: 1, 500: 1", text)


# ---- live (local) requests ------------------------------------------

class TestRequests(ServerTestCase):
    def test_single_request_timings(self):
        r = do_request(f"{self.base}/ok")
        self.assertEqual(r.status, 200)
        self.assertIsNone(r.error)
        self.assertLessEqual(r.ttfb, r.total)
        self.assertGreaterEqual(r.ttlb, 0)
        self.assertAlmostEqual(r.total, r.ttfb + r.ttlb, places=6)

    def test_exact_count(self):
        s = run_load([f"{self.base}/ok"], count=20, concurrency=1)
        self.assertEqual(s.total, 20)
        self.assertEqual(CountingHandler.counts.get("/ok"), 20)

    def test_concurrent(self):
        s = run_load([f"{self.base}/ok"], count=20, concurrency=5)
        self.assertEqual(s.total, 20)
        self.assertEqual(s.successes, 20)
        self.assertEqual(CountingHandler.counts.get("/ok"), 20)

    def test_mixed_statuses(self):
        urls = [f"{self.base}/ok", f"{self.base}/error",
                f"{self.base}/notfound"]
        s = run_load(urls, count=3, concurrency=1)
        self.assertEqual(s.status_counts, {200: 1, 500: 1, 404: 1})
        self.assertEqual(s.successes, 1)
        self.assertEqual(s.failed_5xx, 1)

    def test_redirect_not_followed(self):
        r = do_request(f"{self.base}/redirect")
        self.assertEqual(r.status, 301)

    def test_connection_refused_is_error_result(self):
        # Port 1 on localhost: nothing listens there in practice; use
        # a just-closed server port instead for certainty.
        dead = start_server()
        port = dead.server_address[1]
        dead.shutdown()
        dead.server_close()
        s = run_load([f"http://127.0.0.1:{port}/ok"], count=3,
                     concurrency=1)
        self.assertEqual(s.total, 3)
        self.assertEqual(s.error_count, 3)
        self.assertEqual(s.successes, 0)
        self.assertTrue(all(r.status is None for r in s.results))

    def test_timeout_is_error_result(self):
        r = do_request(f"{self.base}/slow", timeout=0.05)
        self.assertIsNone(r.status)
        self.assertIsNotNone(r.error)

    def test_unsupported_scheme(self):
        r = do_request("ftp://example.com/x")
        self.assertIsNone(r.status)
        self.assertIn("unsupported scheme", r.error)


# ---- file mode -------------------------------------------------------

class TestFileMode(ServerTestCase):
    def test_round_robin_and_blank_lines(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as f:
            f.write(f"\n{self.base}/ok\n\n{self.base}/error\n")
            path = f.name
        try:
            urls = load_tester.load_urls_file(path)
            self.assertEqual(urls, [f"{self.base}/ok",
                                    f"{self.base}/error"])
            s = run_load(urls, count=4, concurrency=1)
            self.assertEqual(CountingHandler.counts.get("/ok"), 2)
            self.assertEqual(CountingHandler.counts.get("/error"), 2)
        finally:
            os.unlink(path)


# ---- duration mode (loose bounds only) -------------------------------

class TestDuration(ServerTestCase):
    def test_duration_only_stops(self):
        s = run_load([f"{self.base}/slow"], count=None, concurrency=2,
                     duration=0.4)
        self.assertGreaterEqual(s.total, 1)
        self.assertLess(s.wall_time, 0.4 + 1.5)

    def test_duration_beats_huge_count(self):
        s = run_load([f"{self.base}/slow"], count=1000, concurrency=2,
                     duration=0.3)
        self.assertLess(s.total, 1000)
        self.assertLess(s.wall_time, 0.3 + 1.5)


# ---- CLI --------------------------------------------------------------

class TestCLI(ServerTestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, MAIN, *args],
                              capture_output=True, text=True, timeout=60)

    def test_positional_single(self):
        out = self.run_cli(f"{self.base}/ok")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "Response code: 200")

    def test_flag_single(self):
        out = self.run_cli("-u", f"{self.base}/ok", "-n", "1")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "Response code: 200")

    def test_summary_output(self):
        out = self.run_cli("-u", f"{self.base}/ok", "-n", "10",
                           "-c", "2")
        self.assertEqual(out.returncode, 0)
        self.assertIn("Results:", out.stdout)
        self.assertIn("Total Requests (2XX)", out.stdout)
        self.assertIn("Request/second", out.stdout)
        self.assertIn("Status codes", out.stdout)
        self.assertIn("200: 10", out.stdout)

    def test_no_url_exits_2(self):
        out = self.run_cli("-n", "5")
        self.assertEqual(out.returncode, 2)

    def test_missing_file_exits_2(self):
        out = self.run_cli("-f", "/nonexistent/urls.txt", "-n", "5")
        self.assertEqual(out.returncode, 2)
        self.assertIn("error", out.stderr)

    def test_bad_scheme_exits_2(self):
        out = self.run_cli("-u", "ftp://example.com/x", "-n", "1")
        self.assertEqual(out.returncode, 2)


# ---- HTTPS (verified, self-signed local cert) ------------------------

@unittest.skipUnless(shutil.which("openssl"), "openssl not available")
class TestHTTPS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cert = os.path.join(cls.tmp, "cert.pem")
        cls.key = os.path.join(cls.tmp, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048",
                        "-keyout", cls.key, "-out", cls.cert,
                        "-days", "1", "-nodes", "-subj",
                        "/CN=127.0.0.1"],
                       check=True, capture_output=True, timeout=60)
        # One cert file holding cert+key for load_cert_chain.
        with open(cls.cert) as f:
            cert_data = f.read()
        with open(cls.key) as f:
            key_data = f.read()
        cls.combined = os.path.join(cls.tmp, "combined.pem")
        with open(cls.combined, "w") as f:
            f.write(cert_data + key_data)
        CountingHandler.counts = {}
        cls.server = start_server(secure=True, certfile=cls.combined)
        cls.port = cls.server.server_address[1]
        cls.base = f"https://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_insecure_succeeds(self):
        r = do_request(f"{self.base}/ok", insecure=True)
        self.assertEqual(r.status, 200)

    def test_verified_self_signed_fails_cleanly(self):
        r = do_request(f"{self.base}/ok", insecure=False)
        self.assertIsNone(r.status)
        self.assertIsNotNone(r.error)

    def test_cli_insecure(self):
        out = subprocess.run([sys.executable, MAIN, "-u",
                              f"{self.base}/ok", "-n", "1", "--insecure"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "Response code: 200")


if __name__ == "__main__":
    unittest.main()

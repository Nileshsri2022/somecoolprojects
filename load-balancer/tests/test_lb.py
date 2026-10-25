"""Tests for lb.py. Run from load-balancer/:
python3 -m unittest discover -s tests -v

Live tests: real backend servers and a real LB on
ephemeral ports, real HTTP requests via urllib.
"""

import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lb import Backend, Balancer, make_server  # noqa: E402


def make_backend(name, port=0):
    """A backend server replying 'Hello from backend <name>'
    to GET, echoing POST bodies, 200 everywhere. Pass a
    port to rebind a restarted backend to the same port."""

    class BackendHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _reply(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            self._reply(f"Hello from backend {name}".encode())

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
            self._reply(body)

    server = ThreadingHTTPServer(("127.0.0.1", port), BackendHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def backend_origin(server):
    return f"http://127.0.0.1:{server.server_address[1]}"


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait_until(predicate, timeout=3.0, step=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


class LbTestCase(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.balancers = []

    def tearDown(self):
        # Stop health threads first, so they do not log
        # "unhealthy" lines for servers being torn down.
        for balancer in self.balancers:
            balancer.stop()
        for server in self.servers:
            server.shutdown()
            server.server_close()

    def start_backend(self, name, port=0):
        server = make_backend(name, port)
        self.servers.append(server)
        return server

    def start_lb(self, origins, interval=0.2):
        backends = [Backend(origin) for origin in origins]
        server, balancer = make_server(0, backends, "/", interval)
        self.servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        balancer.health_check_once()
        balancer.start_health_thread()
        self.balancers.append(balancer)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        return url, balancer


class TestPicker(unittest.TestCase):
    def test_round_robin_skips_unhealthy(self):
        backends = [Backend(f"http://127.0.0.1:{8000 + i}")
                    for i in range(3)]
        balancer = Balancer(backends)
        backends[1].healthy = False
        picks = [balancer.next_healthy() for _ in range(4)]
        self.assertEqual(picks, [backends[0], backends[2],
                                 backends[0], backends[2]])
        for backend in backends:
            backend.healthy = False
        self.assertIsNone(balancer.next_healthy())


class TestLive(LbTestCase):
    def test_single_backend(self):
        backend = self.start_backend("A")
        url, _ = self.start_lb([backend_origin(backend)])
        status, body = get(url + "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"Hello from backend A")

    def test_round_robin(self):
        a = self.start_backend("A")
        b = self.start_backend("B")
        url, _ = self.start_lb([backend_origin(a), backend_origin(b)])
        bodies = [get(url + "/")[1] for _ in range(6)]
        self.assertEqual(bodies, [b"Hello from backend A",
                                  b"Hello from backend B"] * 3)

    def test_post_body_forwarded(self):
        backend = self.start_backend("A")
        url, _ = self.start_lb([backend_origin(backend)])
        req = urllib.request.Request(url + "/", data=b"hello body",
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.read(), b"hello body")

    def test_health_ejection_and_reentry(self):
        a = self.start_backend("A")
        b = self.start_backend("B")
        url, balancer = self.start_lb([backend_origin(a),
                                       backend_origin(b)])
        self.assertEqual([get(url + "/")[1] for _ in range(2)],
                         [b"Hello from backend A", b"Hello from backend B"])
        # Kill B: it must leave the rotation without client errors.
        port = b.server_address[1]
        b.shutdown()
        b.server_close()
        self.servers.remove(b)
        self.assertTrue(wait_until(
            lambda: balancer.healthy_count() == 1))
        self.assertEqual({get(url + "/")[1] for _ in range(4)},
                         {b"Hello from backend A"})
        # Restart B on the same port: a passing health check
        # must bring it back into rotation.
        self.start_backend("B", port=port)
        self.assertTrue(wait_until(
            lambda: balancer.healthy_count() == 2))
        bodies = {get(url + "/")[1] for _ in range(6)}
        self.assertEqual(bodies, {b"Hello from backend A",
                                  b"Hello from backend B"})

    def test_all_down_gives_502(self):
        a = self.start_backend("A")
        b = self.start_backend("B")
        url, balancer = self.start_lb([backend_origin(a),
                                       backend_origin(b)])
        for backend in (a, b):
            backend.shutdown()
            backend.server_close()
            self.servers.remove(backend)
        self.assertTrue(wait_until(
            lambda: balancer.healthy_count() == 0))
        status, _ = get(url + "/")
        self.assertEqual(status, 502)

    def test_concurrent_requests(self):
        a = self.start_backend("A")
        b = self.start_backend("B")
        url, _ = self.start_lb([backend_origin(a), backend_origin(b)])
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: get(url + "/"),
                                    range(20)))
        self.assertTrue(all(status == 200 for status, _ in results))
        bodies = {body for _, body in results}
        self.assertEqual(bodies, {b"Hello from backend A",
                                  b"Hello from backend B"})


if __name__ == "__main__":
    unittest.main()

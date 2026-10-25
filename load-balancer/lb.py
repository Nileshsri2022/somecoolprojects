#!/usr/bin/env python3
"""load-balancer - Build Your Own Load Balancer (Coding Challenges #5).

Layer-7 HTTP load balancer: round robin over healthy
backends, background health checks, failover to the next
healthy backend when one dies mid-request.

Usage:
  lb.py --port 8000 --backends http://127.0.0.1:8081 http://127.0.0.1:8082
        [--health-path /] [--health-interval 10]

Python standard library only, single file. Threads, not
asyncio: ThreadingHTTPServer handles concurrency, and the
proxy code stays straight-line.
"""

import argparse
import http.client
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOP_BY_HOP = {
    "connection", "keep-alive", "transfer-encoding", "te",
    "trailer", "proxy-connection", "upgrade",
}


class Backend:
    def __init__(self, origin):
        parsed = urlparse(origin)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError(f"invalid backend origin {origin!r} "
                             "(expected http://host[:port])")
        self.origin = origin
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.healthy = True

    def __repr__(self):
        return f"Backend({self.origin}, healthy={self.healthy})"


class Balancer:
    """Round robin over healthy backends, under one lock."""

    def __init__(self, backends, health_path="/", health_interval=10):
        self.backends = backends
        self.health_path = health_path
        self.health_interval = health_interval
        self._lock = threading.Lock()
        self._index = 0
        self._stop = threading.Event()

    def next_healthy(self):
        """Next healthy backend in rotation, or None. Advances
        the index past the backend returned."""
        with self._lock:
            for i in range(len(self.backends)):
                backend = self.backends[(self._index + i) % len(self.backends)]
                if backend.healthy:
                    self._index = (self._index + i + 1) % len(self.backends)
                    return backend
            return None

    def healthy_count(self):
        with self._lock:
            return sum(1 for b in self.backends if b.healthy)

    def mark_unhealthy(self, backend):
        with self._lock:
            if backend.healthy:
                backend.healthy = False
                print(f"Backend {backend.origin} is unhealthy, "
                      "removed from rotation", flush=True)

    def mark_healthy(self, backend):
        with self._lock:
            if not backend.healthy:
                backend.healthy = True
                print(f"Backend {backend.origin} is healthy again, "
                      "back in rotation", flush=True)

    def health_check_once(self):
        for backend in self.backends:
            try:
                conn = http.client.HTTPConnection(
                    backend.host, backend.port, timeout=2)
                conn.request("GET", self.health_path)
                response = conn.getresponse()
                response.read()
                conn.close()
                ok = response.status == 200
            except Exception:
                ok = False
            if ok:
                self.mark_healthy(backend)
            else:
                self.mark_unhealthy(backend)

    def health_loop(self):
        while not self._stop.is_set():
            self.health_check_once()
            self._stop.wait(self.health_interval)

    def start_health_thread(self):
        thread = threading.Thread(target=self.health_loop, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self._stop.set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "lb/1.0"

    # Quiet the default stderr logging; we log our own lines.
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_PUT(self):
        self.handle_request()

    def do_DELETE(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_PATCH(self):
        self.handle_request()

    def handle_request(self):
        balancer = self.server.balancer
        length = self.headers.get("Content-Length")
        body = self.rfile.read(int(length)) if length else b""
        print(f"Received request from {self.client_address[0]}", flush=True)
        print(f"{self.command} {self.path} HTTP/1.1", flush=True)
        for key, value in self.headers.items():
            print(f"{key}: {value}", flush=True)

        tried = set()
        while len(tried) < len(balancer.backends):
            backend = balancer.next_healthy()
            if backend is None or backend in tried:
                break
            tried.add(backend)
            try:
                status, headers, resp_body = self.forward(backend, body)
            except Exception as exc:
                print(f"Backend {backend.origin} failed ({exc}), "
                      "marking unhealthy and trying next", flush=True)
                balancer.mark_unhealthy(backend)
                continue
            print(f"Response from server: HTTP/1.1 {status}", flush=True)
            self.send_response(status)
            for key, value in headers:
                if key.lower() not in HOP_BY_HOP:
                    self.send_header(key, value)
            if self.command != "HEAD":
                self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            if self.command != "HEAD" and resp_body:
                self.wfile.write(resp_body)
            return

        self.send_response(502)
        msg = b"Bad Gateway: no healthy backends available"
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def forward(self, backend, body):
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in HOP_BY_HOP
                   and k.lower() not in ("host", "content-length")}
        headers["X-Forwarded-For"] = self.client_address[0]
        headers["X-Forwarded-Proto"] = "http"
        conn = http.client.HTTPConnection(
            backend.host, backend.port, timeout=10)
        try:
            conn.request(self.command, self.path,
                         body=body if body else None, headers=headers)
            response = conn.getresponse()
            resp_headers = response.getheaders()
            resp_body = response.read()
            status = response.status
        finally:
            conn.close()
        return status, resp_headers, resp_body


class LoadBalancerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, balancer):
        super().__init__(address, Handler)
        self.balancer = balancer


def make_server(port, backends, health_path="/", health_interval=10):
    balancer = Balancer(backends, health_path, health_interval)
    server = LoadBalancerServer(("0.0.0.0", port), balancer)
    return server, balancer


def main(argv):
    parser = argparse.ArgumentParser(
        prog="lb.py", description="HTTP load balancer (round robin).")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--backends", nargs="+", required=True,
                        help="backend origins, e.g. http://127.0.0.1:8081")
    parser.add_argument("--health-path", default="/")
    parser.add_argument("--health-interval", type=float, default=10)
    args = parser.parse_args(argv)

    try:
        backends = [Backend(origin) for origin in args.backends]
    except ValueError as exc:
        print(f"lb: {exc}", file=sys.stderr)
        return 1
    server, balancer = make_server(args.port, backends,
                                   args.health_path, args.health_interval)
    # Initial check, so an already-dead backend never gets
    # the first request (see DESIGN.md).
    balancer.health_check_once()
    balancer.start_health_thread()
    print(f"Load balancer listening on port {args.port}, "
          f"backends: {', '.join(args.backends)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        balancer.stop()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

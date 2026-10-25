#!/usr/bin/env python3
"""Echo server implementing RFC 862 (Coding Challenge #101).

Echoes back to the originating client any data it receives, until the
connection is terminated (TCP) or per datagram (UDP).

Usage:
    python3 echo_server.py [--host HOST] [--port PORT] [--udp]

Defaults: host "" (all local interfaces), port 7 (the Echo Protocol
port; use a high port without privileges, e.g. --port 7007), TCP mode.
Pass --udp (also accepted as -udp, as in the challenge example
`ccecho -udp`) for UDP mode.

Python 3 standard library only.
"""

import argparse
import signal
import socket
import sys
import threading

TCP_CHUNK = 65536
UDP_MAX = 65535
LOOP_TIMEOUT = 0.5


class TCPServer:
    """TCP echo server: main thread accepts, one thread per client."""

    def __init__(self, host="", port=7):
        self.host = host
        self.port = port
        self._stop = threading.Event()
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._accept_thread = None
        self._handlers = []
        self.sock = None

    @property
    def actual_port(self):
        return self.sock.getsockname()[1] if self.sock else self.port

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen()
        self.sock.settimeout(LOOP_TIMEOUT)
        print(f"TCP Echo server listening on :{self.actual_port}", flush=True)
        self._accept_thread = threading.Thread(
            target=self._accept_loop, daemon=True
        )
        self._accept_thread.start()

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            print(f"Accepted connection from: {addr[0]}:{addr[1]}", flush=True)
            with self._clients_lock:
                self._clients.add(conn)
            thread = threading.Thread(
                target=self._handle_client, args=(conn,), daemon=False
            )
            thread.start()
            self._handlers.append(thread)

    def _handle_client(self, conn):
        try:
            while not self._stop.is_set():
                try:
                    data = conn.recv(TCP_CHUNK)
                except OSError:
                    break
                if not data:
                    print("Client disconnected", flush=True)
                    break
                try:
                    conn.sendall(data)
                except OSError:
                    break
        finally:
            with self._clients_lock:
                self._clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        with self._clients_lock:
            clients = list(self._clients)
        for conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=5)
        for thread in self._handlers:
            thread.join(timeout=5)
        print("Server shutting down", flush=True)

    def wait(self):
        self._stop.wait()


class UDPServer:
    """UDP echo server: each datagram is sent back to its sender."""

    def __init__(self, host="", port=7):
        self.host = host
        self.port = port
        self._stop = threading.Event()
        self._loop_thread = None
        self.sock = None

    @property
    def actual_port(self):
        return self.sock.getsockname()[1] if self.sock else self.port

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(LOOP_TIMEOUT)
        print(f"UDP Echo server listening on :{self.actual_port}", flush=True)
        self._loop_thread = threading.Thread(target=self._loop, daemon=True)
        self._loop_thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(UDP_MAX)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self.sock.sendto(data, addr)
            except OSError:
                break

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5)
        print("Server shutting down", flush=True)

    def wait(self):
        self._stop.wait()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="RFC 862 echo server")
    parser.add_argument("--host", default="",
                        help="address to bind (default: all interfaces)")
    parser.add_argument("--port", "-p", type=int, default=7,
                        help="port to listen on (default: 7)")
    parser.add_argument("--udp", "-udp", dest="udp", action="store_true",
                        help="use UDP instead of TCP")
    parser.add_argument("--tcp", dest="udp", action="store_false",
                        help="use TCP (default)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    server = UDPServer(args.host, args.port) if args.udp \
        else TCPServer(args.host, args.port)
    try:
        server.start()
    except OSError as exc:
        print(f"error: cannot start server: {exc}", file=sys.stderr)
        return 1

    def _on_signal(_signum, _frame):
        server.stop()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    server.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Minimal Memcached text-protocol server (Coding Challenges #17).

Python 3 standard library only. In-memory store, thread per client,
lazy expiration. See docs/SPEC.md for the protocol as implemented.

Usage:
    python3 memcached_server.py            # 127.0.0.1:11211
    python3 memcached_server.py -p 9999    # 127.0.0.1:9999
"""

import argparse
import socket
import socketserver
import sys
import threading
import time
from dataclasses import dataclass

DEFAULT_PORT = 11211
HOST = "127.0.0.1"


@dataclass
class Item:
    flags: int
    expires_at: float | None  # None = never expires (monotonic clock)
    data: bytes


class Store:
    """Thread-safe in-memory store with lazy expiration."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[bytes, Item] = {}

    def _is_expired(self, item: Item) -> bool:
        return item.expires_at is not None and time.monotonic() >= item.expires_at

    def _live(self, key: bytes) -> Item | None:
        """Return the live item for key, lazily removing it if expired."""
        item = self._items.get(key)
        if item is None:
            return None
        if self._is_expired(item):
            del self._items[key]
            return None
        return item

    def get(self, keys: list[bytes]) -> list[tuple[bytes, Item]]:
        with self._lock:
            return [(k, item) for k in keys if (item := self._live(k)) is not None]

    def set(self, key: bytes, item: Item) -> None:
        with self._lock:
            self._items[key] = item

    def add(self, key: bytes, item: Item) -> bool:
        with self._lock:
            if self._live(key) is not None:
                return False
            self._items[key] = item
            return True

    def replace(self, key: bytes, item: Item) -> bool:
        with self._lock:
            if self._live(key) is None:
                return False
            self._items[key] = item
            return True

    def append(self, key: bytes, item: Item) -> bool:
        with self._lock:
            old = self._live(key)
            if old is None:
                return False
            self._items[key] = Item(item.flags, item.expires_at, old.data + item.data)
            return True

    def prepend(self, key: bytes, item: Item) -> bool:
        with self._lock:
            old = self._live(key)
            if old is None:
                return False
            self._items[key] = Item(item.flags, item.expires_at, item.data + old.data)
            return True

    def delete(self, key: bytes) -> bool:
        with self._lock:
            if self._live(key) is None:
                return False
            del self._items[key]
            return True


STORE_COMMANDS = {"set", "add", "replace", "append", "prepend"}


def _deadline(exptime: int) -> float | None:
    if exptime == 0:
        return None
    # Negative exptime: already expired (deadline in the past), so the
    # first access lazily removes it. Positive: seconds into the future.
    return time.monotonic() + exptime


class MemcachedHandler(socketserver.BaseRequestHandler):
    """One client connection. Reads command lines + data blocks as bytes."""

    store: Store  # set by make_server

    def setup(self) -> None:
        self.rfile = self.request.makefile("rb")

    def handle(self) -> None:
        while True:
            line = self.rfile.readline()
            if not line:  # client disconnected
                return
            line = line.rstrip(b"\r\n")
            if not line:  # bare CRLF (e.g. stray telnet newline): ignore
                continue
            parts = line.split()
            if not parts:
                continue
            cmd = parts[0].decode("ascii", "replace").lower()
            try:
                if cmd in STORE_COMMANDS:
                    self._handle_storage(cmd, parts)
                elif cmd == "get":
                    self._handle_get(parts)
                elif cmd == "delete":
                    self._handle_delete(parts)
                else:
                    self._send(b"ERROR\r\n")
            except (ConnectionError, BrokenPipeError):
                return

    def _send(self, data: bytes) -> None:
        self.request.sendall(data)

    def _read_exact(self, n: int) -> bytes | None:
        """Read exactly n bytes, or None if the client disconnected."""
        chunks = []
        remaining = n
        while remaining > 0:
            chunk = self.rfile.read(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _handle_storage(self, cmd: str, parts: list[bytes]) -> None:
        # <cmd> <key> <flags> <exptime> <bytes> [noreply]
        if len(parts) not in (5, 6):
            self._send(b"ERROR\r\n")
            return
        try:
            flags = int(parts[2])
            exptime = int(parts[3])
            nbytes = int(parts[4])
        except ValueError:
            self._send(b"ERROR\r\n")
            return
        if flags < 0 or nbytes < 0:
            self._send(b"ERROR\r\n")
            return
        noreply = len(parts) == 6 and parts[5] == b"noreply"
        if len(parts) == 6 and not noreply:
            self._send(b"ERROR\r\n")
            return
        data = self._read_exact(nbytes)
        if data is None:
            return  # client went away mid-block; end this connection
        if self._read_exact(2) is None:
            return  # missing trailing CRLF; end this connection
        item = Item(flags, _deadline(exptime), data)
        store = self.store
        if cmd == "set":
            store.set(parts[1], item)
            stored = True
        elif cmd == "add":
            stored = store.add(parts[1], item)
        elif cmd == "replace":
            stored = store.replace(parts[1], item)
        elif cmd == "append":
            stored = store.append(parts[1], item)
        else:  # prepend
            stored = store.prepend(parts[1], item)
        if not noreply:
            self._send(b"STORED\r\n" if stored else b"NOT_STORED\r\n")

    def _handle_get(self, parts: list[bytes]) -> None:
        if len(parts) < 2:
            self._send(b"ERROR\r\n")
            return
        out = []
        for key, item in self.store.get(parts[1:]):
            out.append(b"VALUE %s %d %d\r\n" % (key, item.flags, len(item.data)))
            out.append(item.data + b"\r\n")
        out.append(b"END\r\n")
        self._send(b"".join(out))

    def _handle_delete(self, parts: list[bytes]) -> None:
        # delete <key> [noreply]
        if len(parts) not in (2, 3):
            self._send(b"ERROR\r\n")
            return
        noreply = len(parts) == 3 and parts[2] == b"noreply"
        if len(parts) == 3 and not noreply:
            self._send(b"ERROR\r\n")
            return
        deleted = self.store.delete(parts[1])
        if not noreply:
            self._send(b"DELETED\r\n" if deleted else b"NOT_FOUND\r\n")


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(port: int) -> ThreadingTCPServer:
    handler = type("BoundHandler", (MemcachedHandler,), {"store": Store()})
    return ThreadingTCPServer((HOST, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal Memcached server.")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = make_server(args.port)
    host, port = server.server_address
    print(f"Serving on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

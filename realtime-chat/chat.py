#!/usr/bin/env python3
"""Realtime chat client and server (Coding Challenges, challenge-realtime-chat).

Usage:
    python3 chat.py server [--host HOST] [--port PORT] [--echo]
    python3 chat.py client [--host HOST] [--port PORT] [--name NAME]

Wire protocol (line-based, UTF-8, see docs/SPEC.md): on connect the
server sends "Welcome to the chatroom!"; the client's first line is
its nickname; later lines are message bodies broadcast to every other
client as "Name: body". In --echo mode lines are sent back to the
sender instead. Python 3 standard library only.
"""

import argparse
import select
import socket
import sys
import threading

WELCOME = "Welcome to the chatroom!"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7007


def _send(sock, line):
    """Send one line; return False if the peer is gone."""
    try:
        sock.sendall((line + "\n").encode("utf-8"))
        return True
    except OSError:
        return False


class ChatServer:
    """Thread-per-client TCP chat (or echo) server."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, echo=False):
        self.host = host
        self.port = port
        self.echo = echo
        self._clients = {}  # socket -> nickname, guarded by _lock
        self._lock = threading.Lock()
        self._listener = None
        self._accept_thread = None
        self._running = False

    @property
    def client_count(self):
        with self._lock:
            return len(self._clients)

    def start(self):
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((self.host, self.port))
        self.port = self._listener.getsockname()[1]  # ephemeral port, if 0
        self._listener.listen()
        self._listener.settimeout(0.5)  # let the accept loop notice stop()
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop,
                                               daemon=True)
        self._accept_thread.start()
        return self

    def stop(self):
        self._running = False
        if self._listener is not None:
            try:
                # shutdown() wakes a thread blocked in accept(); close()
                # alone does not reliably interrupt it on Linux.
                self._listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._listener.close()
            except OSError:
                pass
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for sock in clients:
            try:
                sock.close()
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2)

    def _accept_loop(self):
        while self._running:
            try:
                conn, _addr = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _broadcast(self, line, exclude=None):
        """Send line to all registered clients except exclude."""
        with self._lock:
            peers = [s for s in self._clients if s is not exclude]
        dead = []
        for sock in peers:
            if not _send(sock, line):
                dead.append(sock)
        if dead:
            with self._lock:
                for sock in dead:
                    self._clients.pop(sock, None)

    def _handle(self, conn):
        name = None
        try:
            reader = conn.makefile("r", encoding="utf-8", errors="replace")
            if not _send(conn, WELCOME):
                return
            first = reader.readline()
            if not first:  # client left before naming itself
                return
            name = first.strip() or "Anonymous"
            if self.echo:
                with self._lock:
                    self._clients[conn] = name
                for line in reader:
                    body = line.rstrip("\r\n")
                    if body and not _send(conn, body):
                        break
                return
            with self._lock:
                self._clients[conn] = name
            self._broadcast("%s has joined the chatroom." % name,
                            exclude=conn)
            for line in reader:
                body = line.rstrip("\r\n")
                if not body:
                    continue
                self._broadcast("%s: %s" % (name, body), exclude=conn)
        except OSError:
            pass
        finally:
            with self._lock:
                was_registered = self._clients.pop(conn, None) is not None
            try:
                conn.close()
            except OSError:
                pass
            if was_registered and not self.echo and name is not None:
                self._broadcast("%s has left the chatroom." % name)


def run_client(host, port, name, stdin, stdout):
    """Interactive client: select() over stdin and the socket.

    Socket reads are unbuffered recv() + a line buffer on purpose:
    a buffered reader could hold lines select() cannot see, delaying
    messages that already arrived until the next packet.
    """
    sock = socket.create_connection((host, port))
    buf = b""

    # Welcome line: read until the first newline, chunk by chunk.
    while b"\n" not in buf:
        try:
            chunk = sock.recv(4096)
        except OSError:
            chunk = b""
        if not chunk:
            break
        buf += chunk
    if b"\n" in buf:
        welcome, buf = buf.split(b"\n", 1)
        print(welcome.decode("utf-8", "replace"), file=stdout, flush=True)
    sock.sendall((name + "\n").encode("utf-8"))
    print("Type messages, or 'quit' / 'exit' to leave.",
          file=stdout, flush=True)
    while True:
        # Drain any complete lines already buffered before blocking.
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            print(line.decode("utf-8", "replace"), file=stdout, flush=True)
        ready, _w, _x = select.select([stdin, sock], [], [])
        if sock in ready:
            try:
                chunk = sock.recv(4096)
            except OSError:
                break
            if not chunk:  # server closed the connection
                break
            buf += chunk
        if stdin in ready:
            typed = stdin.readline()
            if not typed:  # EOF (Ctrl-D / piped input exhausted)
                break
            body = typed.rstrip("\r\n")
            if body.lower() in ("quit", "exit"):
                break
            if not body:
                continue
            print("%s: %s" % (name, body), file=stdout, flush=True)
            try:
                sock.sendall((body + "\n").encode("utf-8"))
            except OSError:
                break
    try:
        sock.close()
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Realtime chat client/server")
    sub = parser.add_subparsers(dest="command", required=True)
    p_server = sub.add_parser("server", help="run the chat server")
    p_server.add_argument("--host", default=DEFAULT_HOST)
    p_server.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_server.add_argument("--echo", action="store_true",
                          help="Step 1/2 mode: echo lines back to sender")
    p_client = sub.add_parser("client", help="run the chat client")
    p_client.add_argument("--host", default=DEFAULT_HOST)
    p_client.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_client.add_argument("--name", default=None)
    args = parser.parse_args(argv)

    if args.command == "server":
        server = ChatServer(args.host, args.port, echo=args.echo)
        server.start()
        print("Chat server listening on %s:%d%s"
              % (args.host, server.port, " (echo mode)" if args.echo else ""),
              flush=True)
        try:
            server._accept_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
        return 0

    name = args.name
    if name is None:
        try:
            name = input("name: ").strip()
        except EOFError:
            return 0
        if not name:
            name = "Anonymous"
    run_client(args.host, args.port, name, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

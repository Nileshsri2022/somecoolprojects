#!/usr/bin/env python3
"""Command-line client for a Memcached server (plain-text protocol).

Python 3 standard library only. One-shot mode takes a subcommand;
with no subcommand it enters an interactive REPL.

    python3 memcached_cli.py --host 127.0.0.1 --port 11211 set k v
    python3 memcached_cli.py --host 127.0.0.1 --port 11211 get k
    python3 memcached_cli.py --host 127.0.0.1 --port 11211   # REPL
"""

import argparse
import shlex
import socket
import sys


class MemcachedError(Exception):
    """A server error line, or a protocol/connection failure."""


class MemcachedClient:
    """Minimal client for the Memcached plain-text protocol over TCP."""

    def __init__(self, host="localhost", port=11211, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None
        self._buf = b""

    def connect(self):
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise MemcachedError(
                f"cannot connect to {self.host}:{self.port}: {exc}") from exc
        self._buf = b""
        return self

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()
        return False

    # -- low-level IO ---------------------------------------------------

    def _send(self, data):
        try:
            self._sock.sendall(data)
        except OSError as exc:
            raise MemcachedError(f"connection lost: {exc}") from exc

    def _readline(self):
        while b"\r\n" not in self._buf:
            try:
                chunk = self._sock.recv(4096)
            except OSError as exc:
                raise MemcachedError(f"connection lost: {exc}") from exc
            if not chunk:
                raise MemcachedError("connection closed by server")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line.decode("utf-8", errors="replace")

    def _read_exact(self, n):
        while len(self._buf) < n:
            try:
                chunk = self._sock.recv(4096)
            except OSError as exc:
                raise MemcachedError(f"connection lost: {exc}") from exc
            if not chunk:
                raise MemcachedError("connection closed by server")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def _read_reply(self):
        """Read one single-word reply, raising on server error lines."""
        line = self._readline()
        if line.startswith(("ERROR", "CLIENT_ERROR", "SERVER_ERROR")):
            raise MemcachedError(line)
        return line

    # -- storage commands ------------------------------------------------

    def _storage(self, cmd, key, value, flags=0, exptime=0):
        raw = value.encode("utf-8")
        self._send(
            f"{cmd} {key} {flags} {exptime} {len(raw)}\r\n".encode() + raw + b"\r\n")
        return self._read_reply()

    def set(self, key, value, flags=0, exptime=0):
        return self._storage("set", key, value, flags, exptime)

    def add(self, key, value, flags=0, exptime=0):
        return self._storage("add", key, value, flags, exptime)

    def replace(self, key, value, flags=0, exptime=0):
        return self._storage("replace", key, value, flags, exptime)

    def append(self, key, value, flags=0, exptime=0):
        return self._storage("append", key, value, flags, exptime)

    def prepend(self, key, value, flags=0, exptime=0):
        return self._storage("prepend", key, value, flags, exptime)

    # -- retrieval ---------------------------------------------------------

    def _retrieve(self, cmd, keys):
        self._send(f"{cmd} {' '.join(keys)}\r\n".encode())
        results = {}
        while True:
            line = self._readline()
            if line == "END":
                return results
            if line.startswith(("ERROR", "CLIENT_ERROR", "SERVER_ERROR")):
                raise MemcachedError(line)
            parts = line.split()
            if len(parts) < 4 or parts[0] != "VALUE":
                raise MemcachedError(f"unexpected reply: {line}")
            key, flags, nbytes = parts[1], int(parts[2]), int(parts[3])
            cas = int(parts[4]) if len(parts) > 4 else None
            data = self._read_exact(nbytes)
            trailer = self._read_exact(2)
            if trailer != b"\r\n":
                raise MemcachedError("malformed value block")
            results[key] = (flags, data.decode("utf-8"), cas)

    def get_multi(self, keys):
        return {k: (f, v) for k, (f, v, _c) in
                self._retrieve("get", keys).items()}

    def get(self, key):
        result = self.get_multi([key])
        return result.get(key)

    def gets_multi(self, keys):
        return self._retrieve("gets", keys)

    def gets(self, key):
        result = self.gets_multi([key])
        return result.get(key)

    # -- other commands ----------------------------------------------------

    def delete(self, key):
        self._send(f"delete {key}\r\n".encode())
        return self._read_reply()

    def _counter(self, cmd, key, amount):
        self._send(f"{cmd} {key} {amount}\r\n".encode())
        reply = self._read_reply()
        if reply == "NOT_FOUND":
            raise MemcachedError("NOT_FOUND")
        try:
            return int(reply)
        except ValueError:
            raise MemcachedError(f"unexpected reply: {reply}") from None

    def incr(self, key, amount=1):
        return self._counter("incr", key, amount)

    def decr(self, key, amount=1):
        return self._counter("decr", key, amount)

    def touch(self, key, exptime):
        self._send(f"touch {key} {exptime}\r\n".encode())
        return self._read_reply()

    def flush_all(self):
        self._send(b"flush_all\r\n")
        return self._read_reply()

    def stats(self):
        self._send(b"stats\r\n")
        result = {}
        while True:
            line = self._readline()
            if line == "END":
                return result
            if line.startswith(("ERROR", "CLIENT_ERROR", "SERVER_ERROR")):
                raise MemcachedError(line)
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[0] == "STAT":
                result[parts[1]] = parts[2]
            else:
                raise MemcachedError(f"unexpected reply: {line}")

    def version(self):
        self._send(b"version\r\n")
        line = self._readline()
        if line.startswith(("ERROR", "CLIENT_ERROR", "SERVER_ERROR")):
            raise MemcachedError(line)
        return line


# -- CLI -------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Memcached command-line client (text protocol).")
    # Page form is -host / -p (ccmc -host <host> -p <port> ...);
    # the --host / --port forms are accepted as well.
    parser.add_argument("-host", "--host", default="localhost")
    parser.add_argument("-p", "--port", type=int, default=11211)
    parser.add_argument("--timeout", type=float, default=5)
    sub = parser.add_subparsers(dest="command")

    for cmd in ("set", "add", "replace", "append", "prepend"):
        p = sub.add_parser(cmd)
        p.add_argument("key")
        p.add_argument("value")
        p.add_argument("--flags", type=int, default=0)
        p.add_argument("--exptime", type=int, default=0)
    for cmd in ("get", "gets"):
        p = sub.add_parser(cmd)
        p.add_argument("keys", nargs="+")
    p = sub.add_parser("delete")
    p.add_argument("key")
    for cmd in ("incr", "decr"):
        p = sub.add_parser(cmd)
        p.add_argument("key")
        p.add_argument("amount", type=int, nargs="?", default=1)
    p = sub.add_parser("touch")
    p.add_argument("key")
    p.add_argument("exptime", type=int)
    sub.add_parser("flush_all")
    sub.add_parser("stats")
    sub.add_parser("version")
    return parser


def _run_parsed(client, args):
    """Execute one parsed command; return an exit code."""
    cmd = args.command
    try:
        if cmd in ("set", "add", "replace", "append", "prepend"):
            print(getattr(client, cmd)(
                args.key, args.value, args.flags, args.exptime))
        elif cmd == "get":
            for key, (_flags, value) in client.get_multi(args.keys).items():
                print(f"{key}: {value}")
        elif cmd == "gets":
            for key, (_flags, value, cas) in client.gets_multi(args.keys).items():
                print(f"{key}: {value} (cas={cas})")
        elif cmd == "delete":
            print(client.delete(args.key))
        elif cmd in ("incr", "decr"):
            print(getattr(client, cmd)(args.key, args.amount))
        elif cmd == "touch":
            print(client.touch(args.key, args.exptime))
        elif cmd == "flush_all":
            print(client.flush_all())
        elif cmd == "stats":
            for key, value in client.stats().items():
                print(f"STAT {key} {value}")
        elif cmd == "version":
            print(client.version())
        else:  # pragma: no cover - argparse/REPL guard this
            raise MemcachedError(f"unknown command: {cmd}")
    except MemcachedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


REPL_HELP = """Commands: set/add/replace/append/prepend KEY VALUE [--flags N] [--exptime N]
  get/gets KEY [KEY ...]  delete KEY  incr/decr KEY [AMOUNT]
  touch KEY SECONDS  flush_all  stats  version  help  quit"""


def repl(client):
    """Interactive loop; returns an exit code."""
    print("Connected. Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = input("memcached> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0
        if not line.strip():
            continue
        if line.strip() in ("quit", "exit"):
            return 0
        if line.strip() == "help":
            print(REPL_HELP)
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            continue
        # Storage commands are parsed by hand so the value may contain
        # spaces; everything else reuses the one-shot parser.
        if tokens[0] in ("set", "add", "replace", "append", "prepend"):
            args = _repl_storage_args(tokens)
            if args is None:
                continue
        else:
            try:
                args = build_parser().parse_args(tokens)
            except SystemExit:
                continue
            if args.command is None:
                print("error: unknown command", file=sys.stderr)
                continue
        _run_parsed(client, args)


def _repl_storage_args(tokens):
    """Parse a REPL storage line, keeping spaces in the value.

    Returns an argparse namespace like the one-shot parser, or None after
    printing an error. The value is everything after the key, minus any
    trailing --flags/--exptime options.
    """
    cmd, key = tokens[0], tokens[1] if len(tokens) > 1 else None
    if key is None:
        print("error: missing key", file=sys.stderr)
        return None
    rest, flags, exptime = [], 0, 0
    i = 2
    while i < len(tokens):
        if tokens[i] == "--flags" and i + 1 < len(tokens):
            try:
                flags = int(tokens[i + 1])
            except ValueError:
                print("error: --flags must be an integer", file=sys.stderr)
                return None
            i += 2
        elif tokens[i] == "--exptime" and i + 1 < len(tokens):
            try:
                exptime = int(tokens[i + 1])
            except ValueError:
                print("error: --exptime must be an integer", file=sys.stderr)
                return None
            i += 2
        else:
            rest.append(tokens[i])
            i += 1
    if not rest:
        print("error: missing value", file=sys.stderr)
        return None
    return argparse.Namespace(command=cmd, key=key, value=" ".join(rest),
                              flags=flags, exptime=exptime)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    client = MemcachedClient(args.host, args.port, args.timeout)
    try:
        client.connect()
    except MemcachedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command is None:
            return repl(client)
        return _run_parsed(client, args)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())

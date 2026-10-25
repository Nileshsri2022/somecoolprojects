#!/usr/bin/env python3
"""Lite Redis server: threaded TCP server speaking RESP.

Python 3 standard library only. Commands: PING, ECHO, SET (with
EX/PX/EXAT/PXAT expiry), GET, EXISTS, DEL, INCR, DECR, LPUSH, RPUSH,
LRANGE (extra, so list contents are observable), SAVE.

Usage: python3 redis_server.py [--host 127.0.0.1] [--port 6379]
           [--dump-file dump.rdb]
"""

import argparse
import base64
import json
import os
import socketserver
import sys
import threading
import time

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1


class NeedMoreData(Exception):
    """Buffer holds only a partial RESP message."""


class RespError(Exception):
    """Malformed RESP input."""


class SimpleString:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, SimpleString) and self.value == other.value

    def __repr__(self):
        return "SimpleString(%r)" % (self.value,)


class Error:
    def __init__(self, message):
        self.message = message

    def __eq__(self, other):
        return isinstance(other, Error) and self.message == other.message

    def __repr__(self):
        return "Error(%r)" % (self.message,)


def _read_line(data, pos):
    """Return (line_without_crlf, next_pos) or raise NeedMoreData."""
    end = data.find(b"\r\n", pos)
    if end == -1:
        raise NeedMoreData()
    return data[pos:end], end + 2


def _read_int(line):
    try:
        return int(line)
    except ValueError:
        raise RespError("Protocol error: invalid integer %r" % (line,))


def _parse_at(data, pos):
    """parse_one variant that works with an absolute position."""
    if pos >= len(data):
        raise NeedMoreData()
    prefix = data[pos:pos + 1]
    if prefix == b"+":
        line, nxt = _read_line(data, pos + 1)
        return SimpleString(line.decode("utf-8", "replace")), nxt
    if prefix == b"-":
        line, nxt = _read_line(data, pos + 1)
        return Error(line.decode("utf-8", "replace")), nxt
    if prefix == b":":
        line, nxt = _read_line(data, pos + 1)
        return _read_int(line), nxt
    if prefix == b"$":
        line, p = _read_line(data, pos + 1)
        length = _read_int(line)
        if length == -1:
            return None, p
        if length < -1:
            raise RespError("Protocol error: invalid bulk length")
        if len(data) < p + length + 2:
            raise NeedMoreData()
        if data[p + length:p + length + 2] != b"\r\n":
            raise RespError("Protocol error: bulk string not CRLF-terminated")
        return data[p:p + length], p + length + 2
    if prefix == b"*":
        line, p = _read_line(data, pos + 1)
        count = _read_int(line)
        if count == -1:
            return None, p
        if count < -1:
            raise RespError("Protocol error: invalid array length")
        items = []
        for _ in range(count):
            item, p = _parse_at(data, p)
            items.append(item)
        return items, p
    raise RespError("Protocol error: unknown prefix %r" % (prefix,))


def parse_one(data):
    """Parse one RESP value from the start of ``data``.

    Returns (value, bytes_consumed). Raises NeedMoreData for a partial
    message and RespError for a malformed one. Values: SimpleString,
    Error, int, bytes (bulk string), list (array), None (null).
    """
    value, consumed = _parse_at(data, 0)
    return value, consumed


def encode(value):
    """Serialise a value to RESP bytes."""
    if isinstance(value, SimpleString):
        return b"+" + value.value.encode("utf-8") + b"\r\n"
    if isinstance(value, Error):
        return b"-" + value.message.encode("utf-8") + b"\r\n"
    if isinstance(value, int):
        return b":" + str(value).encode("ascii") + b"\r\n"
    if isinstance(value, bytes):
        return b"$" + str(len(value)).encode("ascii") + b"\r\n" + value + b"\r\n"
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, list):
        out = [b"*" + str(len(value)).encode("ascii") + b"\r\n"]
        out.extend(encode(item) for item in value)
        return b"".join(out)
    raise TypeError("cannot encode %r" % (value,))


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _unb64(text):
    return base64.b64decode(text.encode("ascii"))


class Store:
    """The dictionary: key (bytes) -> [kind, value, expire_at]."""

    def __init__(self):
        self.lock = threading.Lock()
        self.data = {}
        self.dump_file = "dump.rdb"

    def _purge_if_expired(self, key):
        entry = self.data.get(key)
        if entry is not None and entry[2] is not None and time.time() > entry[2]:
            del self.data[key]
            return True
        return False

    def get_entry(self, key):
        self._purge_if_expired(key)
        return self.data.get(key)

    def set(self, key, value, expire_at=None):
        self.data[key] = ["string", value, expire_at]

    def delete(self, keys):
        removed = 0
        for key in keys:
            self._purge_if_expired(key)
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed

    def count_existing(self, keys):
        count = 0
        for key in keys:
            if self.get_entry(key) is not None:
                count += 1
        return count

    def save(self, path):
        snapshot = {}
        now = time.time()
        for key, (kind, value, expire_at) in self.data.items():
            if expire_at is not None and now > expire_at:
                continue
            if kind == "string":
                snapshot[_b64(key)] = {"type": "string", "value": _b64(value),
                                        "expire_at": expire_at}
            else:
                snapshot[_b64(key)] = {"type": "list",
                                        "value": [_b64(v) for v in value],
                                        "expire_at": expire_at}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh)
        os.replace(tmp, path)

    def load(self, path):
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        now = time.time()
        for key_b64, entry in snapshot.items():
            expire_at = entry.get("expire_at")
            if expire_at is not None and now > expire_at:
                continue
            key = _unb64(key_b64)
            if entry["type"] == "string":
                self.data[key] = ["string", _unb64(entry["value"]), expire_at]
            elif entry["type"] == "list":
                self.data[key] = ["list", [_unb64(v) for v in entry["value"]],
                                  expire_at]


def _wrongtype():
    return Error("WRONGTYPE Operation against a key holding the wrong kind "
                 "of value")


def _arity(name):
    return Error("ERR wrong number of arguments for '%s' command" % name)


def _parse_expiry(args):
    """Parse SET expiry options. Returns (expire_at, error_or_None).

    args are the tokens after key and value. At most one expiry option.
    """
    if not args:
        return None, None
    if len(args) != 2:
        return None, Error("ERR syntax error")
    option = args[0].decode("ascii", "replace").upper()
    if option not in ("EX", "PX", "EXAT", "PXAT"):
        return None, Error("ERR syntax error")
    try:
        amount = int(args[1])
    except ValueError:
        return None, Error("ERR value is not an integer or out of range")
    if option == "EX":
        return time.time() + amount, None
    if option == "PX":
        return time.time() + amount / 1000.0, None
    if option == "EXAT":
        return float(amount), None
    return amount / 1000.0, None  # PXAT


def _int_value(raw):
    try:
        value = int(raw)
    except ValueError:
        return None, Error("ERR value is not an integer or out of range")
    if value < INT64_MIN or value > INT64_MAX:
        return None, Error("ERR value is not an integer or out of range")
    return value, None


def execute(store, command):
    """Run one command (list of bytes) against the store; return a reply."""
    if not command:
        return Error("ERR empty command")
    name = command[0].decode("ascii", "replace").lower()
    args = command[1:]
    with store.lock:
        if name == "ping":
            if len(args) == 0:
                return SimpleString("PONG")
            if len(args) == 1:
                return args[0]
            return _arity("ping")
        if name == "echo":
            if len(args) != 1:
                return _arity("echo")
            return args[0]
        if name == "set":
            if len(args) < 2:
                return _arity("set")
            expire_at, err = _parse_expiry(args[2:])
            if err is not None:
                return err
            store.set(args[0], args[1], expire_at)
            return SimpleString("OK")
        if name == "get":
            if len(args) != 1:
                return _arity("get")
            entry = store.get_entry(args[0])
            if entry is None:
                return None
            if entry[0] != "string":
                return _wrongtype()
            return entry[1]
        if name == "exists":
            if len(args) < 1:
                return _arity("exists")
            return store.count_existing(args)
        if name == "del":
            if len(args) < 1:
                return _arity("del")
            return store.delete(args)
        if name == "incr" or name == "decr":
            if len(args) != 1:
                return _arity(name)
            delta = 1 if name == "incr" else -1
            entry = store.get_entry(args[0])
            if entry is None:
                value = delta
            else:
                if entry[0] != "string":
                    return _wrongtype()
                value, err = _int_value(entry[1])
                if err is not None:
                    return err
                value += delta
                if value < INT64_MIN or value > INT64_MAX:
                    return Error("ERR increment or decrement would overflow")
            expire_at = entry[2] if entry is not None else None
            store.data[args[0]] = ["string", str(value).encode("ascii"),
                                   expire_at]
            return value
        if name == "lpush" or name == "rpush":
            if len(args) < 2:
                return _arity(name)
            entry = store.get_entry(args[0])
            if entry is None:
                items = []
                expire_at = None
            else:
                if entry[0] != "list":
                    return _wrongtype()
                items = entry[1]
                expire_at = entry[2]
            if name == "lpush":
                for element in args[1:]:
                    items.insert(0, element)
            else:
                items.extend(args[1:])
            store.data[args[0]] = ["list", items, expire_at]
            return len(items)
        if name == "lrange":
            if len(args) != 3:
                return _arity("lrange")
            entry = store.get_entry(args[0])
            if entry is None:
                return []
            if entry[0] != "list":
                return _wrongtype()
            items = entry[1]
            start, err1 = _int_value(args[1])
            stop, err2 = _int_value(args[2])
            if err1 is not None or err2 is not None:
                return Error("ERR value is not an integer or out of range")
            n = len(items)
            if start < 0:
                start += n
            if stop < 0:
                stop += n
            start = max(start, 0)
            stop = min(stop, n - 1)
            if start > stop or n == 0:
                return []
            return items[start:stop + 1]
        if name == "save":
            if len(args) != 0:
                return _arity("save")
            try:
                store.save(store.dump_file)
            except OSError as exc:
                return Error("ERR %s" % exc)
            return SimpleString("OK")
        return Error("ERR unknown command '%s'" % name)


class RedisHandler(socketserver.BaseRequestHandler):
    def handle(self):
        buf = b""
        try:
            while True:
                try:
                    value, consumed = parse_one(buf)
                except NeedMoreData:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                    continue
                except RespError:
                    self.request.sendall(
                        b"-ERR Protocol error\r\n")
                    return
                buf = buf[consumed:]
                if not isinstance(value, list) or any(
                        not isinstance(item, bytes) for item in value):
                    self.request.sendall(
                        b"-ERR Protocol error: expected array of bulk strings\r\n")
                    continue
                reply = execute(self.server.store, value)
                self.request.sendall(encode(reply))
        except (ConnectionResetError, BrokenPipeError):
            return


class RedisTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, dump_file):
        self.store = store
        self.store.dump_file = dump_file
        super().__init__(address, RedisHandler)


def create_server(host, port, dump_file):
    """Build (but do not start) a server, loading the dump file if any."""
    store = Store()
    store.dump_file = dump_file
    store.load(dump_file)
    return RedisTCPServer((host, port), store, dump_file)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lite Redis server (RESP).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--dump-file", default="dump.rdb")
    options = parser.parse_args(argv)
    server = create_server(options.host, options.port, options.dump_file)
    actual_port = server.server_address[1]
    print("Redis Lite listening on %s:%d (dump file: %s)"
          % (options.host, actual_port, options.dump_file), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

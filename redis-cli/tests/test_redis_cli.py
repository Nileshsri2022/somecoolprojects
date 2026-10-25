#!/usr/bin/env python3
"""Tests for redis_cli.py — fake in-process RESP server, ephemeral port."""

import io
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redis_cli import (  # noqa: E402
    HELP,
    RedisClient,
    RedisError,
    RespError,
    encode_command,
    format_reply,
    help_text,
    main,
    parse_reply_bytes,
    run_repl,
)


# ------------------------------------------------------------ fake server

def _encode_reply(value):
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, RedisError):
        return ("-%s\r\n" % value.message).encode()
    if isinstance(value, int):
        return (":%d\r\n" % value).encode()
    if isinstance(value, str):
        data = value.encode()
        return b"$%d\r\n%s\r\n" % (len(data), data)
    if isinstance(value, list):
        out = [("*%d\r\n" % len(value)).encode()]
        for item in value:
            out.append(_encode_reply(item))
        return b"".join(out)
    raise TypeError(value)


class FakeRedisServer:
    """Minimal RESP2 server: strings + lists, Redis-style errors."""

    def __init__(self):
        self.store = {}
        self.lists = {}
        self.received = []  # commands seen, for asserting quit sends none
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=5)

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (OSError, socket.timeout):
                continue
            threading.Thread(target=self._handle, args=(conn,),
                             daemon=True).start()

    def _handle(self, conn):
        buf = b""
        try:
            while True:
                while b"\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                line, buf = buf.split(b"\r\n", 1)
                if not line.startswith(b"*"):
                    return
                count = int(line[1:])
                args = []
                for _ in range(count):
                    while b"\r\n" not in buf:
                        chunk = conn.recv(4096)
                        if not chunk:
                            return
                        buf += chunk
                    hline, buf = buf.split(b"\r\n", 1)
                    n = int(hline[1:])
                    while len(buf) < n + 2:
                        chunk = conn.recv(4096)
                        if not chunk:
                            return
                        buf += chunk
                    args.append(buf[:n].decode())
                    buf = buf[n + 2:]
                self.received.append(args)
                conn.sendall(_encode_reply(self._execute(args)))
        except (OSError, ValueError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _need(self, args, n, name):
        if len(args) != n:
            return RedisError("ERR wrong number of arguments for '%s' command"
                              % name)
        return None

    def _execute(self, args):
        if not args:
            return RedisError("ERR empty command")
        name, rest = args[0].lower(), args[1:]
        err = None
        if name == "ping":
            if len(rest) > 1:
                err = self._need(args, 2, name)
            return err if err else (rest[0] if rest else "PONG")
        if name == "echo":
            err = self._need(args, 2, name)
            return err if err else rest[0]
        if name == "set":
            if len(rest) < 2:
                return self._need(args, 3, name)
            self.store[rest[0]] = rest[1]
            self.lists.pop(rest[0], None)
            return "OK"
        if name == "get":
            err = self._need(args, 2, name)
            return err if err else self.store.get(rest[0])
        if name == "del":
            if not rest:
                return self._need(args, 2, name)
            n = sum(1 for k in rest if self.store.pop(k, None) is not None
                    or self.lists.pop(k, None) is not None)
            return n
        if name == "exists":
            if not rest:
                return self._need(args, 2, name)
            return sum(1 for k in rest if k in self.store or k in self.lists)
        if name in ("incr", "decr"):
            err = self._need(args, 2, name)
            if err:
                return err
            try:
                val = int(self.store.get(rest[0], "0"))
            except ValueError:
                return RedisError("ERR value is not an integer or out of range")
            val += 1 if name == "incr" else -1
            self.store[rest[0]] = str(val)
            return val
        if name in ("lpush", "rpush"):
            if len(rest) < 2:
                return self._need(args, 3, name)
            lst = self.lists.setdefault(rest[0], [])
            if name == "lpush":
                for el in rest[1:]:
                    lst.insert(0, el)
            else:
                lst.extend(rest[1:])
            return len(lst)
        if name == "lrange":
            err = self._need(args, 4, name)
            if err:
                return err
            lst = self.lists.get(rest[0], [])
            start, stop = int(rest[1]), int(rest[2])
            if stop < 0:
                stop += len(lst)
            return lst[start:stop + 1] if lst else []
        if name == "llen":
            err = self._need(args, 2, name)
            return err if err else len(self.lists.get(rest[0], []))
        return RedisError("ERR unknown command '%s'" % name)


# ------------------------------------------------------------- RESP codec

class TestEncode(unittest.TestCase):
    def test_page_examples_byte_exact(self):
        self.assertEqual(encode_command(["ping"]), b"*1\r\n$4\r\nping\r\n")
        self.assertEqual(encode_command(["echo", "hello world"]),
                         b"*2\r\n$4\r\necho\r\n$11\r\nhello world\r\n")
        self.assertEqual(encode_command(["get", "key"]),
                         b"*2\r\n$3\r\nget\r\n$3\r\nkey\r\n")
        self.assertEqual(encode_command(["set", "key", "value"]),
                         b"*3\r\n$3\r\nset\r\n$3\r\nkey\r\n$5\r\nvalue\r\n")

    def test_empty_and_unicode(self):
        self.assertEqual(encode_command(["set", "k", ""]),
                         b"*3\r\n$3\r\nset\r\n$1\r\nk\r\n$0\r\n\r\n")
        self.assertEqual(encode_command(["echo", "héllo"]),
                         b"*2\r\n$4\r\necho\r\n$6\r\nh\xc3\xa9llo\r\n")


class TestDecodePageExamples(unittest.TestCase):
    def test_all_page_examples(self):
        self.assertIsNone(parse_reply_bytes(b"$-1\r\n"))
        self.assertIsNone(parse_reply_bytes(b"*-1\r\n"))
        self.assertEqual(parse_reply_bytes(b"+OK\r\n"), "OK")
        self.assertEqual(parse_reply_bytes(b"+hello world\r\n"), "hello world")
        self.assertEqual(parse_reply_bytes(b"$0\r\n\r\n"), "")
        err = parse_reply_bytes(b"-Error message\r\n")
        self.assertIsInstance(err, RedisError)
        self.assertEqual(err.message, "Error message")

    def test_nested_array_and_integer(self):
        self.assertEqual(parse_reply_bytes(b"*2\r\n$3\r\nget\r\n$3\r\nkey\r\n"),
                         ["get", "key"])
        self.assertEqual(
            parse_reply_bytes(b"*2\r\n:1\r\n*2\r\n$1\r\na\r\n$1\r\nb\r\n"),
            [1, ["a", "b"]])
        self.assertEqual(parse_reply_bytes(b":42\r\n"), 42)
        self.assertEqual(parse_reply_bytes(b":-3\r\n"), -3)

    def test_invalid_inputs_raise(self):
        bad = [
            b"", b"+OK", b"?OK\r\n", b":abc\r\n", b"$x\r\n\r\n",
            b"$-2\r\n", b"*-2\r\n", b"$5\r\nabc\r\n",
            b"$3\r\nabcXX\r\n", b"*2\r\n$1\r\na\r\n",
        ]
        for data in bad:
            with self.subTest(data=data):
                with self.assertRaises(RespError):
                    parse_reply_bytes(data)

    def test_encode_decode_round_trip(self):
        args = ["set", "my key", "hello world", ""]
        self.assertEqual(parse_reply_bytes(encode_command(args)), args)


class TestFormat(unittest.TestCase):
    def test_scalars(self):
        self.assertEqual(format_reply("PONG"), "PONG")
        self.assertEqual(format_reply(None), "(nil)")
        self.assertEqual(format_reply(3), "(integer) 3")
        self.assertEqual(format_reply(RedisError("ERR nope")),
                         "(error) ERR nope")

    def test_arrays(self):
        self.assertEqual(format_reply([]), "(empty array)")
        self.assertEqual(format_reply(["a", "b", None]),
                         "1) a\n2) b\n3) (nil)")
        self.assertEqual(format_reply([1, ["a", "b"]]),
                         "1) (integer) 1\n2)\n  1) a\n  2) b")


class TestHelp(unittest.TestCase):
    def test_intro_and_command_and_group(self):
        self.assertIn("help @<group>", help_text())
        self.assertIn("quit", help_text())
        set_help = help_text("set")
        self.assertIn("SET key value", set_help)
        self.assertIn("summary: Set the string value of a key", set_help)
        self.assertIn("since: 1.0.0", set_help)
        self.assertIn("group: string", set_help)
        self.assertIn("SET", help_text("@string"))
        self.assertIn("GET", help_text("@string"))
        self.assertNotIn("LPUSH", help_text("@string"))

    def test_unknown(self):
        self.assertIn("(error)", help_text("nosuchcmd"))
        self.assertIn("(error)", help_text("@nosuchgroup"))
        self.assertEqual(help_text("SET"), help_text("set"))  # case-insensitive


# ------------------------------------------------------- wire-level tests

class FakeServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeRedisServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def client(self):
        return RedisClient("127.0.0.1", self.server.port, timeout=5).connect()


class TestClientOverWire(FakeServerTestCase):
    def test_ping_and_echo(self):
        c = self.client()
        try:
            self.assertEqual(c.command("PING"), "PONG")
            self.assertEqual(c.command("PING", "Hello"), "Hello")
            self.assertEqual(c.command("ECHO", "HI!"), "HI!")
        finally:
            c.close()

    def test_string_commands(self):
        c = self.client()
        try:
            self.assertEqual(c.command("SET", "key", "value"), "OK")
            self.assertEqual(c.command("GET", "key"), "value")
            self.assertIsNone(c.command("GET", "missing"))
            self.assertEqual(c.command("EXISTS", "key", "missing"), 1)
            self.assertEqual(c.command("DEL", "key"), 1)
            self.assertEqual(c.command("DEL", "key"), 0)
            self.assertEqual(c.command("EXISTS", "key"), 0)
        finally:
            c.close()

    def test_incr_decr(self):
        c = self.client()
        try:
            self.assertEqual(c.command("INCR", "counter"), 1)
            self.assertEqual(c.command("INCR", "counter"), 2)
            self.assertEqual(c.command("DECR", "counter"), 1)
            c.command("SET", "notint", "abc")
            err = c.command("INCR", "notint")
            self.assertIsInstance(err, RedisError)
            self.assertIn("not an integer", err.message)
        finally:
            c.close()

    def test_lists(self):
        c = self.client()
        try:
            self.assertEqual(c.command("RPUSH", "mylist", "a", "b"), 2)
            self.assertEqual(c.command("LPUSH", "mylist", "z"), 3)
            self.assertEqual(c.command("LLEN", "mylist"), 3)
            self.assertEqual(c.command("LRANGE", "mylist", "0", "-1"),
                             ["z", "a", "b"])
            self.assertEqual(c.command("LRANGE", "nolist", "0", "-1"), [])
        finally:
            c.close()

    def test_unknown_command_is_error_value_not_exception(self):
        c = self.client()
        try:
            err = c.command("FROBNICATE")
            self.assertIsInstance(err, RedisError)
            self.assertIn("unknown command", err.message)
        finally:
            c.close()

    def test_connection_failure(self):
        closed = FakeRedisServer()
        closed.start()
        port = closed.port
        closed.stop()
        with self.assertRaises(RespError):
            RedisClient("127.0.0.1", port, timeout=2).connect()


class TestRepl(FakeServerTestCase):
    def run_text(self, text):
        stdin, stdout = io.StringIO(text), io.StringIO()
        c = self.client()
        try:
            code = run_repl(c, stdin, stdout)
        finally:
            c.close()
        return code, stdout.getvalue()

    def test_session(self):
        code, out = self.run_text("ping\nping Hello\nset k v\nget k\nquit\n")
        self.assertEqual(code, 0)
        self.assertIn("127.0.0.1:%d> " % self.server.port, out)
        self.assertIn("PONG", out)
        self.assertIn("Hello", out)
        self.assertIn("OK", out)
        self.assertIn("v", out)

    def test_quit_not_sent_and_exit_alias(self):
        before = len(self.server.received)
        code, _ = self.run_text("quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.server.received), before)
        code, _ = self.run_text("exit\n")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.server.received), before)

    def test_blank_lines_and_quotes(self):
        code, out = self.run_text('\nset qk "hello world"\nget qk\nquit\n')
        self.assertEqual(code, 0)
        self.assertIn("hello world", out)

    def test_bare_command_shows_hint_and_sends_nothing(self):
        before = len(self.server.received)
        code, out = self.run_text("get\nquit\n")
        self.assertEqual(code, 0)
        self.assertIn("GET key", out)
        self.assertEqual(len(self.server.received), before)

    def test_help_commands(self):
        _, out = self.run_text("help\nhelp set\nhelp @list\nhelp nosuch\nquit\n")
        self.assertIn("help @<group>", out)
        self.assertIn("SET key value", out)
        self.assertIn("LPUSH", out)
        self.assertIn("(error) unknown command", out)

    def test_server_error_printed_not_fatal(self):
        code, out = self.run_text("frob\nping\nquit\n")
        self.assertEqual(code, 0)
        self.assertIn("(error) ERR unknown command", out)
        self.assertIn("PONG", out)

    def test_eof_exits_cleanly(self):
        code, _ = self.run_text("ping\n")
        self.assertEqual(code, 0)


class TestMain(FakeServerTestCase):
    def test_one_shot(self):
        out, err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = main(["--host", "127.0.0.1", "-p", str(self.server.port),
                         "PING"])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.assertEqual(code, 0)
        self.assertIn("PONG", out.getvalue())

    def test_one_shot_alias_spelling(self):
        out = io.StringIO()
        old_out = sys.stdout
        sys.stdout = out
        try:
            code = main(["-host", "127.0.0.1", "-p", str(self.server.port),
                         "SET", "ak", "av"])
        finally:
            sys.stdout = old_out
        self.assertEqual(code, 0)
        self.assertIn("OK", out.getvalue())

    def test_connection_failure_exit_1(self):
        closed = FakeRedisServer()
        closed.start()
        port = closed.port
        closed.stop()
        err = io.StringIO()
        old_err = sys.stderr
        sys.stderr = err
        try:
            code = main(["--host", "127.0.0.1", "-p", str(port), "PING"])
        finally:
            sys.stderr = old_err
        self.assertEqual(code, 1)
        self.assertIn("cannot connect", err.getvalue())


if __name__ == "__main__":
    unittest.main()

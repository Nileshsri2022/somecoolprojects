#!/usr/bin/env python3
"""Tests for the lite Redis server: RESP codec + live server.

The live server runs on an ephemeral port; the client speaks raw RESP
over a socket. Run from redis-server/:
    python3 -m unittest discover -s tests -v
"""

import os
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from redis_server import (  # noqa: E402
    Error, NeedMoreData, RespError, SimpleString, create_server, encode,
    parse_one,
)


def encode_command(*parts):
    out = [b"*" + str(len(parts)).encode() + b"\r\n"]
    for part in parts:
        raw = part if isinstance(part, bytes) else str(part).encode()
        out.append(b"$" + str(len(raw)).encode() + b"\r\n" + raw + b"\r\n")
    return b"".join(out)


class Client:
    """Minimal raw-socket RESP client."""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port))
        self.buf = b""

    def command(self, *parts):
        self.sock.sendall(encode_command(*parts))
        return self.read_reply()

    def send_raw(self, data):
        self.sock.sendall(data)

    def read_reply(self):
        while True:
            try:
                value, consumed = parse_one(self.buf)
                self.buf = self.buf[consumed:]
                return value
            except NeedMoreData:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("server closed connection")
                self.buf += chunk

    def close(self):
        self.sock.close()


class ParserTests(unittest.TestCase):
    # Challenge-page examples, decoded exactly.
    def test_page_examples(self):
        cases = [
            (b"$-1\r\n", None),
            (b"*1\r\n$4\r\nping\r\n", [b"ping"]),
            (b"*2\r\n$4\r\necho\r\n$11\r\nhello world\r\n",
             [b"echo", b"hello world"]),
            (b"*2\r\n$3\r\nget\r\n$3\r\nkey\r\n", [b"get", b"key"]),
            (b"+OK\r\n", SimpleString("OK")),
            (b"-Error message\r\n", Error("Error message")),
            (b"$0\r\n\r\n", b""),
            (b"+hello world\r\n", SimpleString("hello world")),
        ]
        for raw, expected in cases:
            value, consumed = parse_one(raw)
            self.assertEqual(value, expected, raw)
            self.assertEqual(consumed, len(raw), raw)

    def test_integers_and_nested_arrays(self):
        self.assertEqual(parse_one(b":42\r\n"), (42, 5))
        self.assertEqual(parse_one(b":-7\r\n"), (-7, 5))
        self.assertEqual(parse_one(b"*-1\r\n"), (None, 5))
        self.assertEqual(parse_one(b"*2\r\n*1\r\n$1\r\na\r\n$1\r\nb\r\n"),
                         ([[b"a"], b"b"], 22))

    def test_encode_round_trip(self):
        values = [SimpleString("OK"), Error("boom"), 0, -123, b"",
                  b"hello world", None, [b"a", 3, None, [b"x"]]]
        for value in values:
            decoded, consumed = parse_one(encode(value))
            self.assertEqual(decoded, value)
            self.assertEqual(consumed, len(encode(value)))

    def test_partial_input_needs_more_data(self):
        for raw in (b"$5\r\nhel", b"*2\r\n$1\r\na\r\n", b"+OK", b""):
            with self.assertRaises(NeedMoreData, msg=raw):
                parse_one(raw)

    def test_invalid_input_raises(self):
        for raw in (b"?hi\r\n", b"$x\r\n", b"$-2\r\n", b"*-2\r\n",
                    b"$3\r\nabX!\r\n", b":1x\r\n", b"$2\r\nabXX"):
            with self.assertRaises(RespError, msg=raw):
                parse_one(raw)


def start_server(dump_file):
    server = create_server("127.0.0.1", 0, dump_file)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.dump = os.path.join(cls.tmpdir.name, "dump.rdb")
        cls.server, cls.port = start_server(cls.dump)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmpdir.cleanup()

    def setUp(self):
        self.c = Client(self.port)

    def tearDown(self):
        self.c.close()

    def test_ping_and_echo(self):
        self.assertEqual(self.c.command("PING"), SimpleString("PONG"))
        self.assertEqual(self.c.command("ping"), SimpleString("PONG"))
        self.assertEqual(self.c.command("PING", "hello"), b"hello")
        self.assertEqual(self.c.command("ECHO", "Hello World"), b"Hello World")

    def test_set_get_and_overwrite(self):
        self.assertEqual(self.c.command("SET", "Name", "John"),
                         SimpleString("OK"))
        self.assertEqual(self.c.command("GET", "Name"), b"John")
        self.assertIsNone(self.c.command("GET", "no-such-key"))
        self.assertEqual(self.c.command("SET", "Name", "Jane"),
                         SimpleString("OK"))
        self.assertEqual(self.c.command("GET", "Name"), b"Jane")
        self.assertEqual(self.c.command("SET", "empty", ""), SimpleString("OK"))
        self.assertEqual(self.c.command("GET", "empty"), b"")

    def test_set_expiry_ex_and_px(self):
        self.c.command("SET", "exkey", "v", "EX", "1")
        self.assertEqual(self.c.command("GET", "exkey"), b"v")
        time.sleep(1.2)
        self.assertIsNone(self.c.command("GET", "exkey"))
        self.c.command("SET", "pxkey", "v", "PX", "200")
        self.assertEqual(self.c.command("GET", "pxkey"), b"v")
        time.sleep(0.35)
        self.assertIsNone(self.c.command("GET", "pxkey"))

    def test_set_expiry_exat_pxat(self):
        future = int(time.time()) + 10
        self.c.command("SET", "exatkey", "v", "EXAT", str(future))
        self.assertEqual(self.c.command("GET", "exatkey"), b"v")
        past = int(time.time()) - 10
        self.c.command("SET", "exatold", "v", "EXAT", str(past))
        self.assertIsNone(self.c.command("GET", "exatold"))
        future_ms = int(time.time() * 1000) + 10000
        self.c.command("SET", "pxatkey", "v", "PXAT", str(future_ms))
        self.assertEqual(self.c.command("GET", "pxatkey"), b"v")
        past_ms = int(time.time() * 1000) - 10000
        self.c.command("SET", "pxatold", "v", "PXAT", str(past_ms))
        self.assertIsNone(self.c.command("GET", "pxatold"))

    def test_set_bad_expiry_is_error_and_sets_nothing(self):
        for opts in (("BOGUS", "10"), ("EX", "10", "PX", "100"),
                     ("EX", "notanumber")):
            reply = self.c.command("SET", "badkey", "v", *opts)
            self.assertIsInstance(reply, Error, opts)
            self.assertIsNone(self.c.command("GET", "badkey"))

    def test_expired_key_not_counted_by_exists(self):
        self.c.command("SET", "gone", "v", "PX", "100")
        self.assertEqual(self.c.command("EXISTS", "gone"), 1)
        time.sleep(0.2)
        self.assertEqual(self.c.command("EXISTS", "gone"), 0)

    def test_exists_and_del(self):
        self.c.command("SET", "a", "1")
        self.c.command("SET", "b", "2")
        self.assertEqual(self.c.command("EXISTS", "a"), 1)
        self.assertEqual(self.c.command("EXISTS", "a", "b", "missing"), 2)
        self.assertEqual(self.c.command("EXISTS", "missing"), 0)
        self.assertEqual(self.c.command("DEL", "a", "missing"), 1)
        self.assertIsNone(self.c.command("GET", "a"))
        self.assertEqual(self.c.command("DEL", "a"), 0)
        self.assertEqual(self.c.command("DEL", "b"), 1)

    def test_incr_decr(self):
        self.assertEqual(self.c.command("INCR", "counter"), 1)
        self.assertEqual(self.c.command("INCR", "counter"), 2)
        self.assertEqual(self.c.command("DECR", "counter"), 1)
        self.assertEqual(self.c.command("DECR", "newcounter"), -1)
        self.c.command("SET", "notnum", "abc")
        reply = self.c.command("INCR", "notnum")
        self.assertIsInstance(reply, Error)
        self.assertEqual(self.c.command("GET", "notnum"), b"abc")
        self.c.command("SET", "big", "9223372036854775807")
        reply = self.c.command("INCR", "big")
        self.assertIsInstance(reply, Error)

    def test_lists(self):
        self.assertEqual(self.c.command("LPUSH", "mylist", "a", "b", "c"), 3)
        self.assertEqual(self.c.command("LRANGE", "mylist", "0", "-1"),
                         [b"c", b"b", b"a"])
        self.assertEqual(self.c.command("RPUSH", "mylist", "d"), 4)
        self.assertEqual(self.c.command("LRANGE", "mylist", "0", "-1"),
                         [b"c", b"b", b"a", b"d"])
        self.assertEqual(self.c.command("LRANGE", "mylist", "1", "2"),
                         [b"b", b"a"])
        self.assertEqual(self.c.command("LRANGE", "mylist", "-2", "-1"),
                         [b"a", b"d"])
        self.assertEqual(self.c.command("LRANGE", "nosuchlist", "0", "-1"), [])
        self.c.command("SET", "strkey", "x")
        reply = self.c.command("LPUSH", "strkey", "y")
        self.assertIsInstance(reply, Error)
        self.assertIn("WRONGTYPE", reply.message)
        reply = self.c.command("GET", "mylist")
        self.assertIsInstance(reply, Error)
        self.assertIn("WRONGTYPE", reply.message)

    def test_errors_keep_connection_usable(self):
        reply = self.c.command("NOSUCHCMD")
        self.assertIsInstance(reply, Error)
        reply = self.c.command("GET")
        self.assertIsInstance(reply, Error)
        reply = self.c.command("SET", "onlykey")
        self.assertIsInstance(reply, Error)
        self.assertEqual(self.c.command("PING"), SimpleString("PONG"))

    def test_pipelining(self):
        self.c.send_raw(encode_command("SET", "pipe", "yes")
                        + encode_command("GET", "pipe"))
        self.assertEqual(self.c.read_reply(), SimpleString("OK"))
        self.assertEqual(self.c.read_reply(), b"yes")


class ConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.server, cls.port = start_server(
            os.path.join(cls.tmpdir.name, "dump.rdb"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmpdir.cleanup()

    def test_many_clients_set_get(self):
        errors = []

        def worker(n):
            try:
                client = Client(self.port)
                for i in range(50):
                    client.command("SET", "w%d-k%d" % (n, i), "v%d" % i)
                    got = client.command("GET", "w%d-k%d" % (n, i))
                    assert got == ("v%d" % i).encode(), (n, i, got)
                client.close()
            except Exception as exc:  # noqa: BLE001 - collected, asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,))
                   for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_concurrent_incr_is_exact(self):
        client = Client(self.port)
        client.command("DEL", "shared")
        client.close()

        def worker():
            c = Client(self.port)
            for _ in range(50):
                c.command("INCR", "shared")
            c.close()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        client = Client(self.port)
        self.assertEqual(client.command("GET", "shared"), b"250")
        client.close()


class SaveLoadTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        tmpdir = tempfile.TemporaryDirectory()
        dump = os.path.join(tmpdir.name, "dump.rdb")
        server, port = start_server(dump)
        try:
            c = Client(port)
            c.command("SET", "keep", "yes")
            c.command("RPUSH", "nums", "1", "2", "3")
            c.command("SET", "stale", "no", "PX", "100")
            time.sleep(0.2)
            self.assertEqual(c.command("SAVE"), SimpleString("OK"))
            c.close()
        finally:
            server.shutdown()
            server.server_close()
        self.assertTrue(os.path.exists(dump))
        server2, port2 = start_server(dump)
        try:
            c = Client(port2)
            self.assertEqual(c.command("GET", "keep"), b"yes")
            self.assertEqual(c.command("LRANGE", "nums", "0", "-1"),
                             [b"1", b"2", b"3"])
            self.assertIsNone(c.command("GET", "stale"))
            c.close()
        finally:
            server2.shutdown()
            server2.server_close()
            tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()

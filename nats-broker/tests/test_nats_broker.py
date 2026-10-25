"""Tests for nats_broker.py. Starts a real server on an ephemeral port."""
import json
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nats_broker import NATSClient, NATSServer, subject_matches  # noqa: E402


class RawConn:
    """Minimal raw-socket helper speaking exact wire bytes."""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port),
                                             timeout=5.0)
        self.buf = b""

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def readline(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.rstrip(b"\r").decode()

    def read_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed connection")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.sock.sendall(data)

    def read_msg(self):
        """Read one MSG frame: (subject, sid, reply_to, payload)."""
        while True:
            line = self.readline()
            if line.startswith("MSG "):
                parts = line.split(" ")
                if len(parts) == 4:
                    _, subject, sid, size = parts
                    reply_to = None
                else:
                    _, subject, sid, reply_to, size = parts
                payload = self.read_exact(int(size))
                self.read_exact(2)  # trailing CRLF
                return subject, int(sid), reply_to, payload


class BrokerTestCase(unittest.TestCase):
    def setUp(self):
        self.server = NATSServer("127.0.0.1", 0).start()
        self.port = self.server.port
        self.clients = []
        self.raws = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        for r in self.raws:
            r.close()
        self.server.stop()

    def client(self):
        c = NATSClient("127.0.0.1", self.port).connect()
        self.clients.append(c)
        return c

    def raw(self):
        r = RawConn(self.port)
        self.raws.append(r)
        return r


class TestWireProtocol(BrokerTestCase):
    def test_info_and_connect_and_ping(self):
        r = self.raw()
        info = r.readline()
        self.assertTrue(info.startswith("INFO "))
        data = json.loads(info[5:])
        self.assertEqual(data["port"], self.port)
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertIn("client_ip", data)
        r.send("CONNECT {}\r\n")
        self.assertEqual(r.readline(), "+OK")
        r.send("PING\r\n")
        self.assertEqual(r.readline(), "PONG")

    def test_page_step3_sub_pub_msg(self):
        r = self.raw()
        r.readline()  # INFO
        r.send("CONNECT {}\r\n")
        self.assertEqual(r.readline(), "+OK")
        r.send("SUB CC 10\r\n")
        self.assertEqual(r.readline(), "+OK")
        r.send("PUB CC 4\r\nJOHN\r\n")
        self.assertEqual(r.readline(), "+OK")
        self.assertEqual(r.read_msg(), ("CC", 10, None, b"JOHN"))

    def test_unknown_command_is_err_not_disconnect(self):
        r = self.raw()
        r.readline()
        r.send("CONNECT {}\r\n")
        self.assertEqual(r.readline(), "+OK")
        r.send("BOGUS hello\r\n")
        self.assertTrue(r.readline().startswith("-ERR"))
        r.send("PING\r\n")
        self.assertEqual(r.readline(), "PONG")

    def test_pub_payload_with_crlf_and_binary(self):
        sub = self.client()
        pub = self.client()
        sub.subscribe("bin", sid=1)
        payload = b"a\r\nb\x00\xff\r\n"
        pub.publish("bin", payload)
        subject, sid, reply, got = sub.read_msg()
        self.assertEqual((subject, sid, reply, got),
                         ("bin", 1, None, payload))


class TestClientBehaviour(BrokerTestCase):
    def test_publish_subscribe_two_clients(self):
        sub = self.client()
        pub = self.client()
        other = self.client()
        sub.subscribe("news", sid=7)
        pub.publish("news", "hello")
        self.assertEqual(sub.read_msg()[3], b"hello")
        with self.assertRaises(TimeoutError):
            other.read_msg(timeout=0.5)

    def test_wildcard_star_single_token(self):
        sub = self.client()
        pub = self.client()
        sub.subscribe("foo.*", sid=1)
        pub.publish("foo.bar", "one")
        self.assertEqual(sub.read_msg()[3], b"one")
        pub.publish("foo.bar.baz", "two")
        pub.publish("other.bar", "three")
        with self.assertRaises(TimeoutError):
            sub.read_msg(timeout=0.5)

    def test_wildcard_gt_multi_token(self):
        sub = self.client()
        pub = self.client()
        sub.subscribe("foo.>", sid=1)
        pub.publish("foo.bar", "one")
        self.assertEqual(sub.read_msg()[3], b"one")
        pub.publish("foo.bar.baz", "two")
        self.assertEqual(sub.read_msg()[3], b"two")
        pub.publish("foo", "three")
        pub.publish("other.bar", "four")
        with self.assertRaises(TimeoutError):
            sub.read_msg(timeout=0.5)

    def test_unsubscribe_stops_delivery_but_publish_still_works(self):
        sub = self.client()
        other = self.client()
        sub.subscribe("CC", sid=10)
        other.subscribe("CC", sid=20)
        sub.publish("CC", "first")
        self.assertEqual(sub.read_msg()[3], b"first")
        self.assertEqual(other.read_msg()[3], b"first")
        sub.unsubscribe(10)
        sub.publish("CC", "second")
        self.assertEqual(other.read_msg()[3], b"second")
        with self.assertRaises(TimeoutError):
            sub.read_msg(timeout=0.5)

    def test_unsub_with_max_msgs(self):
        sub = self.client()
        pub = self.client()
        sub.subscribe("lim", sid=3)
        sub.unsubscribe(3, max_msgs=1)
        pub.publish("lim", "one")
        self.assertEqual(sub.read_msg()[3], b"one")
        pub.publish("lim", "two")
        with self.assertRaises(TimeoutError):
            sub.read_msg(timeout=0.5)

    def test_reply_to_is_carried_in_msg(self):
        sub = self.client()
        pub = self.client()
        sub.subscribe("req", sid=5)
        pub.publish("req", "ping", reply_to="inbox.1")
        subject, sid, reply, payload = sub.read_msg()
        self.assertEqual((subject, sid, reply, payload),
                         ("req", 5, "inbox.1", b"ping"))

    def test_queue_group_delivers_to_one_member(self):
        a = self.client()
        b = self.client()
        plain = self.client()
        pub = self.client()
        a.subscribe("work", sid=1, queue="workers")
        b.subscribe("work", sid=2, queue="workers")
        plain.subscribe("work", sid=3)
        pub.publish("work", "m1")
        pub.publish("work", "m2")
        # Plain subscriber gets both.
        self.assertEqual(plain.read_msg()[3], b"m1")
        self.assertEqual(plain.read_msg()[3], b"m2")
        # Queue members split the two messages one each.
        got = sorted([a.read_msg(timeout=2.0)[3],
                      b.read_msg(timeout=2.0)[3]])
        self.assertEqual(got, [b"m1", b"m2"])

    def test_concurrent_publishers_and_subscribers(self):
        subs = [self.client() for _ in range(3)]
        for s in subs:
            s.subscribe("fan", sid=1)
        pubs = [self.client() for _ in range(3)]
        errors = []

        def publish_all(pub, n):
            try:
                for i in range(n):
                    pub.publish("fan", "x%d" % i)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=publish_all, args=(p, 10))
                   for p in pubs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        for s in subs:
            msgs = [s.read_msg(timeout=5.0)[3] for _ in range(30)]
            self.assertEqual(sorted(msgs),
                             sorted([b"x%d" % i for i in range(10)] * 3))


class TestSubjectMatching(unittest.TestCase):
    def test_subject_matching_table(self):
        cases = [
            ("foo", "foo", True),
            ("foo", "bar", False),
            ("foo.*", "foo.bar", True),
            ("foo.*", "foo.bar.baz", False),
            ("foo.*", "foo", False),
            ("*.bar", "foo.bar", True),
            ("foo.>", "foo.bar", True),
            ("foo.>", "foo.bar.baz", True),
            ("foo.>", "foo", False),
            ("foo.>", "other.bar", False),
            (">", "a.b.c", True),
            ("foo.>.bar", "foo.x.bar", False),  # > non-final: no match
        ]
        for pattern, subject, expected in cases:
            with self.subTest(pattern=pattern, subject=subject):
                self.assertEqual(subject_matches(pattern, subject),
                                 expected)


if __name__ == "__main__":
    unittest.main()

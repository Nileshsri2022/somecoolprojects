"""Tests for dns_resolver.py.

No test contacts a public DNS server: network tests use a fake UDP DNS
server bound to 127.0.0.1 on an ephemeral port.
"""

import io
import socket
import struct
import sys
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dns_resolver
from dns_resolver import (CLASS_IN, TYPE_A, TYPE_AAAA, TYPE_CNAME, TYPE_NS,
                          DNSError, Header, Message, Question,
                          ResourceRecord, build_query, decode_name,
                          encode_name, resolve_iterative, resolve_recursive,
                          send_query)

# Page Step 2 example response (hex), Step 3 expected decode.
PAGE_RESPONSE_HEX = (
    "00168080000100020000000003646e7306676f6f676c6503636f6d0000010001"
    "c00c0001000100000214000408080808c00c0001000100000214000408080404"
)
PAGE_QUERY_HEX = (
    "00160100000100000000000003646e7306676f6f676c6503636f6d0000010001"
)


def make_message(id_, flags, questions, answers=(), authorities=(),
                 additionals=()):
    header = Header(id_, flags, len(questions), len(answers),
                    len(authorities), len(additionals))
    return Message(header, list(questions), list(answers),
                   list(authorities), list(additionals))


def question(name="example.com", qtype=TYPE_A):
    return Question(name, qtype, CLASS_IN)


def record(name, rtype, rdata, ttl=300):
    return ResourceRecord(name, rtype, CLASS_IN, ttl, rdata)


class FakeDNSServer:
    """UDP server on 127.0.0.1:0; handler(request) -> Message, bytes, None."""

    def __init__(self, handler):
        self.handler = handler
        self.seen = []  # request Messages, in order
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self.thread.join(timeout=5)
        self.sock.close()
        return False

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                request = Message.from_bytes(data)
            except ValueError:
                continue
            self.seen.append(request)
            reply = self.handler(request)
            if reply is None:
                continue  # simulate a silent server (timeout on client)
            if isinstance(reply, Message):
                reply.header.id = request.header.id
                reply.header.flags |= 0x8000
                payload = reply.to_bytes()
            else:
                payload = bytes(reply)
            # Reply from this same socket, which the client connected
            # to: the sandbox blocks unconnected UDP sendto, and a
            # reply from any other source port is dropped by the
            # client's connected socket. After replying, rebind a fresh
            # socket on the same port: a socket left connected to one
            # client would drop the next query, which arrives from a
            # new client source port.
            try:
                self.sock.connect(addr)
                self.sock.send(payload)
            except OSError:
                continue
            self.sock.close()
            fresh = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            fresh.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            fresh.bind(("127.0.0.1", self.port))
            fresh.settimeout(0.2)
            self.sock = fresh


def canned_a_handler(answers):
    def handler(request):
        return make_message(0, 0x8180, request.questions,
                            [record(request.questions[0].name, TYPE_A, ip)
                             for ip in answers])
    return handler


class TestEncoding(unittest.TestCase):
    def test_encode_name_page_example(self):
        self.assertEqual(encode_name("dns.google.com"),
                         b"\x03dns\x06google\x03com\x00")

    def test_encode_root_and_trailing_dot(self):
        self.assertEqual(encode_name("."), b"\x00")
        self.assertEqual(encode_name("example.com."),
                         encode_name("example.com"))

    def test_encode_label_too_long(self):
        with self.assertRaises(ValueError):
            encode_name("a" * 64 + ".com")

    def test_page_query_hex(self):
        query = build_query("dns.google.com", TYPE_A, True, id_=22)
        self.assertEqual(query.to_bytes().hex(), PAGE_QUERY_HEX)

    def test_flags_rd_bit(self):
        self.assertEqual(build_query("example.com", TYPE_A, True).header.flags,
                         0x0100)
        self.assertEqual(build_query("example.com", TYPE_A, False).header.flags,
                         0)


class TestDecoding(unittest.TestCase):
    def test_page_response_hex(self):
        msg = Message.from_bytes(bytes.fromhex(PAGE_RESPONSE_HEX))
        self.assertEqual(msg.header.id, 22)
        self.assertTrue(msg.header.is_response)
        self.assertEqual(len(msg.questions), 1)
        self.assertEqual(msg.questions[0].name, "dns.google.com")
        self.assertEqual(msg.questions[0].qtype, TYPE_A)
        self.assertEqual(len(msg.answers), 2)
        self.assertEqual(len(msg.authorities), 0)
        self.assertEqual(len(msg.additionals), 0)
        for answer in msg.answers:
            self.assertEqual(answer.name, "dns.google.com")
            self.assertEqual(answer.rtype, TYPE_A)
            self.assertEqual(answer.rclass, CLASS_IN)
            self.assertGreater(answer.ttl, 0)
        self.assertEqual([a.rdata for a in msg.answers],
                         ["8.8.8.8", "8.8.4.4"])

    def test_compressed_name_and_following_record(self):
        # Header + question, then two answers whose names are pointers
        # to the question name (offset 12). The second record must
        # still parse, proving the offset after a pointer is correct.
        raw = bytearray()
        raw += struct.pack(">HHHHHH", 7, 0x8180, 1, 2, 0, 0)
        raw += encode_name("example.com") + struct.pack(">HH", 1, 1)
        for ip in ("1.2.3.4", "5.6.7.8"):
            raw += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 300, 4)
            raw += socket.inet_aton(ip)
        msg = Message.from_bytes(bytes(raw))
        self.assertEqual([a.name for a in msg.answers],
                         ["example.com", "example.com"])
        self.assertEqual([a.rdata for a in msg.answers],
                         ["1.2.3.4", "5.6.7.8"])

    def test_pointer_loop_raises(self):
        # One answer whose name points at itself (offset 12).
        raw = struct.pack(">HHHHHH", 1, 0x8180, 0, 1, 0, 0)
        raw += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 300, 4)
        raw += socket.inet_aton("1.2.3.4")
        with self.assertRaises(ValueError):
            Message.from_bytes(raw)

    def test_pointer_out_of_bounds_raises(self):
        with self.assertRaises(ValueError):
            decode_name(b"\xc0\xff", 0)

    def test_round_trip_all_types(self):
        msg = make_message(
            99, 0x8180, [question("example.com", TYPE_A)],
            [record("example.com", TYPE_A, "93.184.216.34"),
             record("example.com", TYPE_AAAA, "2606:2800:220:1:248:1893:25c8:1946"),
             record("example.com", TYPE_NS, "ns.example.com"),
             record("example.com", TYPE_CNAME, "target.example.com"),
             record("example.com", 99, b"\x01\x02\x03")])
        parsed = Message.from_bytes(msg.to_bytes())
        self.assertEqual([r.rdata for r in parsed.answers],
                         ["93.184.216.34",
                          "2606:2800:220:1:248:1893:25c8:1946",
                          "ns.example.com", "target.example.com",
                          b"\x01\x02\x03"])

    def test_truncated_message_raises(self):
        with self.assertRaises(ValueError):
            Message.from_bytes(b"\x00\x01\x80")
        with self.assertRaises(ValueError):
            Message.from_bytes(bytes.fromhex(PAGE_RESPONSE_HEX)[:-3])


class TestNetwork(unittest.TestCase):
    def test_recursive_query_fake_server(self):
        with FakeDNSServer(canned_a_handler(["93.184.216.34"])) as server:
            values = resolve_recursive("127.0.0.1", "example.com",
                                       TYPE_A, server.port, timeout=2)
        self.assertEqual(values, ["93.184.216.34"])
        self.assertEqual(len(server.seen), 1)
        self.assertTrue(server.seen[0].header.flags & 0x0100)  # RD set

    def test_id_mismatch_raises(self):
        def handler(request):
            reply = canned_a_handler(["1.2.3.4"])(request)
            payload = bytearray(reply.to_bytes())
            payload[0:2] = struct.pack(">H", (request.header.id + 1) % 65536)
            return bytes(payload)
        with FakeDNSServer(handler) as server:
            with self.assertRaises(DNSError):
                send_query("127.0.0.1", "example.com", TYPE_A,
                           server.port, timeout=2)

    def test_error_rcode_raises(self):
        def handler(request):
            return make_message(0, 0x8183, request.questions)  # NXDOMAIN
        with FakeDNSServer(handler) as server:
            with self.assertRaises(DNSError):
                send_query("127.0.0.1", "example.com", TYPE_A,
                           server.port, timeout=2)

    def test_timeout_raises(self):
        with FakeDNSServer(lambda request: None) as server:
            with self.assertRaises(DNSError):
                send_query("127.0.0.1", "example.com", TYPE_A,
                           server.port, timeout=0.3)

    def test_iterative_follows_referral_with_glue(self):
        def handler(request):
            if len(handler.calls) == 0:
                handler.calls.append(1)
                return make_message(
                    0, 0x8000, request.questions, (),
                    [record("example.com", TYPE_NS, "ns.example.com")],
                    [record("ns.example.com", TYPE_A, "127.0.0.1")])
            return make_message(0, 0x8000, request.questions,
                                [record("example.com", TYPE_A,
                                        "93.184.216.34")])
        handler.calls = []
        with FakeDNSServer(handler) as server:
            with redirect_stdout(io.StringIO()):
                values = resolve_iterative("example.com", TYPE_A,
                                           "127.0.0.1", server.port,
                                           timeout=2)
        self.assertEqual(values, ["93.184.216.34"])
        self.assertEqual(len(server.seen), 2)
        self.assertFalse(server.seen[0].header.flags & 0x0100)  # RD clear

    def test_iterative_dead_end_raises(self):
        def handler(request):
            return make_message(0, 0x8000, request.questions)
        with FakeDNSServer(handler) as server:
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(DNSError):
                    resolve_iterative("example.com", TYPE_A, "127.0.0.1",
                                      server.port, timeout=2)

    def test_cname_followed(self):
        def handler(request):
            name = request.questions[0].name
            if name == "example.com":
                return make_message(0, 0x8180, request.questions,
                                    [record("example.com", TYPE_CNAME,
                                            "target.example.com")])
            return make_message(0, 0x8180, request.questions,
                                [record("target.example.com", TYPE_A,
                                        "93.184.216.34")])
        with FakeDNSServer(handler) as server:
            values = resolve_recursive("127.0.0.1", "example.com",
                                       TYPE_A, server.port, timeout=2)
        self.assertEqual(values, ["93.184.216.34"])
        self.assertEqual(len(server.seen), 2)


class TestCLI(unittest.TestCase):
    def test_cli_recursive(self):
        with FakeDNSServer(canned_a_handler(["93.184.216.34"])) as server:
            out = io.StringIO()
            with redirect_stdout(out):
                code = dns_resolver.main(["example.com", "--server",
                                          "127.0.0.1", "--port",
                                          str(server.port)])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "93.184.216.34")

    def test_cli_bad_type_exits_nonzero(self):
        out = io.StringIO()
        with redirect_stdout(out):
            with self.assertRaises(SystemExit) as ctx:
                dns_resolver.main(["example.com", "--type", "MX"])
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

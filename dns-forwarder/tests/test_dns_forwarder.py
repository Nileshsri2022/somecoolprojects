#!/usr/bin/env python3
"""Tests for dns_forwarder.py. Local fake upstreams on ephemeral ports
only; no public DNS server is contacted."""

import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dns_forwarder as df


# --- helpers ---------------------------------------------------------------

def a_record(name, ip, ttl=300):
    return df.Record(name, df.TYPE_A, df.CLASS_IN, ttl,
                     bytes(int(p) for p in ip.split(".")))


def aaaa_record(name, ip, ttl=300):
    # ip as 8 colon-separated hex groups, e.g. "2606:4700:4700::1111"
    groups = []
    if "::" in ip:
        left, right = ip.split("::")
        lparts = [int(x, 16) for x in left.split(":")] if left else []
        rparts = [int(x, 16) for x in right.split(":")] if right else []
        groups = lparts + [0] * (8 - len(lparts) - len(rparts)) + rparts
    else:
        groups = [int(x, 16) for x in ip.split(":")]
    return df.Record(name, df.TYPE_AAAA, df.CLASS_IN, ttl,
                     struct.pack("!8H", *groups))


class FakeUpstream(threading.Thread):
    """UDP server that answers from a handler; counts queries."""

    def __init__(self, handler, respond=True):
        super().__init__(daemon=True)
        self.handler = handler
        self.respond = respond
        self.count = 0
        # NOTE: do not name the flag `_stop`: threading.Thread already
        # defines a `_stop` method, so a loop checking
        # `getattr(self, "_stop", False)` would see the truthy method
        # and exit on the first recv timeout. That bug killed this
        # server 0.2 s after start in an earlier run.
        self._stop_event = threading.Event()
        self._connected = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.2)

    def run(self):
        while not self._stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            self.count += 1
            if not self.respond:
                continue
            try:
                query = df.parse_message(data)
            except df.DnsError:
                continue
            reply = self.handler(query)
            if reply is not None:
                # Reply must originate from this socket's port: the
                # forwarder's upstream socket is connected to it, so a
                # reply from any other source port would be dropped.
                # Try sendto() first; in this sandbox it raises EPERM,
                # so connect to the (single) peer and send(). The
                # socket stays connected afterwards — this server only
                # ever talks to one peer — so no rebind is needed.
                try:
                    if self._connected:
                        self.sock.send(reply)
                    else:
                        self.sock.sendto(reply, addr)
                except OSError:
                    try:
                        self.sock.connect(addr)
                        self.sock.send(reply)
                        self._connected = True
                    except OSError:
                        continue

    def stop(self):
        self._stop_event.set()
        self.sock.close()


def standard_handler(answer_map, ttl=300, rcode=0):
    """answer_map: (name, qtype) -> [Record, ...]."""

    def handler(query):
        if not query.questions:
            return df.build_response(query, [], rcode=df.RCODE_FORMERR)
        q = query.questions[0]
        answers = answer_map.get((q.name, q.qtype), [])
        if rcode:
            return df.build_response(query, [], rcode=rcode)
        return df.build_response(query, answers)
    return handler


class ForwarderHarness:
    """A Forwarder running in a thread, plus a client socket."""

    def __init__(self, upstream_port, timeout=5.0, use_cache=True):
        self.fwd = df.Forwarder(bind="127.0.0.1", port=0,
                                upstream="127.0.0.1",
                                upstream_port=upstream_port,
                                timeout=timeout, use_cache=use_cache)
        self.thread = threading.Thread(target=self.fwd.serve_forever,
                                       daemon=True)
        self.thread.start()
        # serve_forever binds port 0 -> OS port; wait for the socket.
        deadline = time.time() + 5
        while self.fwd._listen_sock is None and time.time() < deadline:
            time.sleep(0.01)
        self.port = self.fwd._listen_sock.getsockname()[1]
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.connect(("127.0.0.1", self.port))
        self.client.settimeout(2)

    def query(self, qname, qtype=df.TYPE_A, tx_id=0x1234):
        # Retries on ConnectionRefusedError AND on timeout, same
        # transaction id: this sandbox silently drops a UDP datagram
        # sent immediately after the server swapped its listening
        # socket (close-then-bind in the sendto fallback) — reproduced
        # in isolation, server alive, datagram simply never arriving.
        # A retry is what a real DNS client does, and it is safe for
        # the count assertions here: the observed losses are all on a
        # query leg (the failed query never reached the upstream, so
        # retrying does not double-count it). A reply-leg loss on a
        # forwarded query WOULD double-count and fail loudly, as it
        # should. A genuine hang still fails, after 3 attempts.
        last_error = None
        for attempt in range(3):
            self.client.send(df.build_query(qname, qtype, tx_id=tx_id))
            try:
                data = self.client.recv(4096)
            except (ConnectionRefusedError, socket.timeout,
                    TimeoutError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2)
                    continue
                raise
            return df.parse_message(data)
        raise AssertionError("unreachable: %r" % (last_error,))

    def raw(self, data):
        self.client.send(data)

    def drain(self):
        """Drop any pending reply (e.g. the FORMERR for a raw packet)."""
        old = self.client.gettimeout()
        self.client.settimeout(0.3)
        try:
            self.client.recv(4096)
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        finally:
            self.client.settimeout(old)

    def stop(self):
        self.fwd.stop()
        self.thread.join(timeout=5)
        self.client.close()


# --- unit: wire format ------------------------------------------------------

class TestWireFormat(unittest.TestCase):
    def test_encode_name_page_example(self):
        self.assertEqual(df.encode_name("dns.google.com"),
                         b"\x03dns\x06google\x03com\x00")

    def test_encode_root(self):
        self.assertEqual(df.encode_name(""), b"\x00")
        self.assertEqual(df.encode_name("."), b"\x00")

    def test_parse_plain_name(self):
        data = b"\x03www\x06google\x03com\x00"
        name, nxt = df.parse_name(data, 0)
        self.assertEqual(name, "www.google.com")
        self.assertEqual(nxt, len(data))

    def test_parse_compressed_name(self):
        # Question at 12, answer name = pointer to offset 12.
        query = df.build_query("www.google.com", tx_id=7)
        answer = df.Record("www.google.com", 1, 1, 118,
                           bytes([142, 250, 179, 228]))
        # Build a response whose answer name is a pointer to the question.
        header = struct.pack("!HHHHHH", 7, 0x8180, 1, 1, 0, 0)
        body = query[12:]  # question section
        body += b"\xc0\x0c" + struct.pack(
            "!HHIH", 1, 1, 118, 4) + bytes([142, 250, 179, 228])
        msg = df.parse_message(header + body)
        self.assertEqual(msg.answers[0].name, "www.google.com")
        self.assertEqual(msg.answers[0].rdata_text(), "142.250.179.228")
        self.assertEqual(msg.answers[0].ttl, 118)

    def test_parse_pointer_loop_rejected(self):
        with self.assertRaises(df.DnsError):
            df.parse_name(b"\xc0\x00", 0)

    def test_query_round_trip(self):
        raw = df.build_query("www.google.com", tx_id=40500)
        msg = df.parse_message(raw)
        self.assertEqual(msg.tx_id, 40500)
        self.assertEqual(msg.flags, df.FLAG_RD)
        self.assertEqual(len(msg.questions), 1)
        self.assertEqual(msg.questions[0].name, "www.google.com")
        self.assertEqual(msg.questions[0].qtype, 1)
        self.assertEqual(msg.questions[0].qclass, 1)
        self.assertEqual(msg.answers, [])

    def test_answer_round_trip_a_and_aaaa(self):
        query = df.Message(1, df.FLAG_RD,
                           [df.Question("example.com", 1, 1)], [], [], [])
        recs = [a_record("example.com", "93.184.216.34", ttl=60),
                aaaa_record("example.com", "2606:4700:4700::1111",
                            ttl=60)]
        raw = df.build_response(query, recs)
        msg = df.parse_message(raw)
        self.assertEqual(msg.tx_id, 1)
        self.assertTrue(msg.flags & df.FLAG_QR)
        self.assertEqual(len(msg.answers), 2)
        self.assertEqual(msg.answers[0].rdata_text(), "93.184.216.34")
        self.assertEqual(msg.answers[0].ttl, 60)
        self.assertEqual(msg.answers[1].rtype, df.TYPE_AAAA)

    def test_short_packet_rejected(self):
        with self.assertRaises(df.DnsError):
            df.parse_message(b"\x00\x01\x02")

    def test_truncated_question_rejected(self):
        with self.assertRaises(df.DnsError):
            df.parse_message(struct.pack("!HHHHHH", 1, 0x100, 1, 0, 0, 0)
                             + b"\x03www")


# --- unit: cache -------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestCache(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.cache = df.DnsCache(time_fn=self.clock)

    def test_put_get_unchanged(self):
        recs = [a_record("example.com", "93.184.216.34", ttl=300)]
        self.cache.put(("example.com", 1, 1), recs)
        got = self.cache.get(("example.com", 1, 1))
        self.assertEqual(got, recs)

    def test_expired_is_miss(self):
        self.cache.put(("example.com", 1, 1),
                       [a_record("example.com", "93.184.216.34", ttl=10)])
        self.clock.now += 11
        self.assertIsNone(self.cache.get(("example.com", 1, 1)))

    def test_ttl_decremented_on_hit(self):
        self.cache.put(("example.com", 1, 1),
                       [a_record("example.com", "93.184.216.34", ttl=300)])
        self.clock.now += 100
        got = self.cache.get(("example.com", 1, 1))
        self.assertEqual(got[0].ttl, 200)

    def test_one_expired_record_expires_whole_entry(self):
        self.cache.put(("example.com", 1, 1),
                       [a_record("example.com", "1.2.3.4", ttl=5),
                        a_record("example.com", "5.6.7.8", ttl=300)])
        self.clock.now += 6
        self.assertIsNone(self.cache.get(("example.com", 1, 1)))

    def test_keys_do_not_collide(self):
        self.cache.put(("example.com", 1, 1),
                       [a_record("example.com", "93.184.216.34")])
        self.assertIsNone(self.cache.get(("other.com", 1, 1)))
        self.assertIsNone(self.cache.get(("example.com", 28, 1)))
        self.assertIsNone(self.cache.get(("example.com", 1, 2)))

    def test_case_insensitive_lookup_via_key(self):
        # Keys are built lower-cased by Question.key(); check that path.
        q = df.Question("Example.COM", 1, 1)
        self.cache.put(q.key(), [a_record("example.com", "93.184.216.34")])
        self.assertIsNotNone(
            self.cache.get(df.Question("example.com", 1, 1).key()))

    def test_cap_evicts_oldest(self):
        cache = df.DnsCache(time_fn=self.clock, max_entries=2)
        cache.put(("a.com", 1, 1), [a_record("a.com", "1.1.1.1")])
        cache.put(("b.com", 1, 1), [a_record("b.com", "2.2.2.2")])
        cache.put(("c.com", 1, 1), [a_record("c.com", "3.3.3.3")])
        self.assertEqual(len(cache), 2)
        self.assertIsNone(cache.get(("a.com", 1, 1)))
        self.assertIsNotNone(cache.get(("c.com", 1, 1)))


# --- integration: forwarding + caching over UDP ------------------------------

class TestForwarding(unittest.TestCase):
    def setUp(self):
        answers = {("example.com", df.TYPE_A):
                   [a_record("example.com", "93.184.216.34", ttl=300)],
                   ("example.com", df.TYPE_AAAA):
                   [aaaa_record("example.com",
                                "2606:4700:4700::1111", ttl=300)]}
        self.upstream = FakeUpstream(standard_handler(answers))
        self.upstream.start()
        self.harness = ForwarderHarness(self.upstream.port)

    def tearDown(self):
        self.harness.stop()
        self.upstream.stop()

    def test_forward_returns_upstream_answer_with_client_id(self):
        msg = self.harness.query("example.com", tx_id=0x1234)
        self.assertEqual(msg.tx_id, 0x1234)
        self.assertEqual(msg.rcode, 0)
        self.assertEqual(len(msg.answers), 1)
        self.assertEqual(msg.answers[0].rdata_text(), "93.184.216.34")
        self.assertEqual(self.upstream.count, 1)

    def test_cache_hit_does_not_requery_upstream(self):
        self.harness.query("example.com")
        self.harness.query("example.com")
        self.assertEqual(self.upstream.count, 1)

    def test_cache_isolation_by_name_and_type(self):
        self.harness.query("example.com", df.TYPE_A)
        self.harness.query("other.com", df.TYPE_A)  # unanswered upstream
        self.harness.query("example.com", df.TYPE_AAAA)
        # other.com has no answer so it is not cached: 3 upstream hits.
        self.assertEqual(self.upstream.count, 3)
        self.harness.query("example.com", df.TYPE_A)
        self.harness.query("example.com", df.TYPE_AAAA)
        self.assertEqual(self.upstream.count, 3)  # both now cached

    def test_aaaa_forwarded_and_cached(self):
        msg = self.harness.query("example.com", df.TYPE_AAAA)
        self.assertEqual(msg.answers[0].rtype, df.TYPE_AAAA)
        self.harness.query("example.com", df.TYPE_AAAA)
        self.assertEqual(self.upstream.count, 1)

    def test_malformed_packet_does_not_kill_server(self):
        self.harness.raw(b"\x00\x01garbage-not-dns")
        # The garbage packet earns a FORMERR reply; drain it so the
        # next recv() reads the real answer, not the stale FORMERR.
        self.harness.drain()
        msg = self.harness.query("example.com")
        self.assertEqual(msg.answers[0].rdata_text(), "93.184.216.34")

    def test_short_packet_ignored_then_server_alive(self):
        self.harness.raw(b"\x00\x01")
        msg = self.harness.query("example.com")
        self.assertEqual(len(msg.answers), 1)


class TestTtlExpiry(unittest.TestCase):
    def setUp(self):
        answers = {("shortlived.com", df.TYPE_A):
                   [a_record("shortlived.com", "9.9.9.9", ttl=1)]}
        self.upstream = FakeUpstream(standard_handler(answers))
        self.upstream.start()
        self.harness = ForwarderHarness(self.upstream.port)

    def tearDown(self):
        self.harness.stop()
        self.upstream.stop()

    def test_expired_entry_is_forwarded_again(self):
        first = self.harness.query("shortlived.com")
        self.assertEqual(first.answers[0].rdata_text(), "9.9.9.9")
        self.assertEqual(self.upstream.count, 1)
        time.sleep(1.2)
        second = self.harness.query("shortlived.com")
        self.assertEqual(second.answers[0].rdata_text(), "9.9.9.9")
        self.assertEqual(self.upstream.count, 2)


class TestNxdomainNotCached(unittest.TestCase):
    def setUp(self):
        self.upstream = FakeUpstream(
            standard_handler({}, rcode=df.RCODE_NXDOMAIN))
        self.upstream.start()
        self.harness = ForwarderHarness(self.upstream.port)

    def tearDown(self):
        self.harness.stop()
        self.upstream.stop()

    def test_nxdomain_forwarded_but_not_cached(self):
        first = self.harness.query("missing.example")
        self.assertEqual(first.rcode, df.RCODE_NXDOMAIN)
        second = self.harness.query("missing.example")
        self.assertEqual(second.rcode, df.RCODE_NXDOMAIN)
        self.assertEqual(self.upstream.count, 2)


class TestUpstreamTimeout(unittest.TestCase):
    def setUp(self):
        self.upstream = FakeUpstream(None, respond=False)
        self.upstream.start()
        self.harness = ForwarderHarness(self.upstream.port, timeout=0.5)

    def tearDown(self):
        self.harness.stop()
        self.upstream.stop()

    def test_timeout_yields_servfail_and_server_survives(self):
        msg = self.harness.query("example.com")
        self.assertEqual(msg.rcode, df.RCODE_SERVFAIL)
        self.assertEqual(len(msg.questions), 1)
        self.assertEqual(msg.questions[0].name, "example.com")
        # Server still alive: a second timeout, not a hang or crash.
        msg2 = self.harness.query("example.com")
        self.assertEqual(msg2.rcode, df.RCODE_SERVFAIL)


class TestNoCacheMode(unittest.TestCase):
    def setUp(self):
        answers = {("example.com", df.TYPE_A):
                   [a_record("example.com", "93.184.216.34", ttl=300)]}
        self.upstream = FakeUpstream(standard_handler(answers))
        self.upstream.start()
        self.harness = ForwarderHarness(self.upstream.port, use_cache=False)

    def tearDown(self):
        self.harness.stop()
        self.upstream.stop()

    def test_repeated_queries_each_reach_upstream(self):
        self.harness.query("example.com")
        self.harness.query("example.com")
        self.assertEqual(self.upstream.count, 2)


if __name__ == "__main__":
    unittest.main()

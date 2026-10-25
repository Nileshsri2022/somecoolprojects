"""Unit tests for traceroute.py — no sockets, no privileges, no network.

Packet fixtures are hand-built byte strings fed to parse_icmp_packet.
The trace loop is exercised through a fake transport.
"""

import io
import socket
import struct
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

import traceroute as tr


def ip_header(protocol, payload=b""):
    """Minimal 20-byte IPv4 header; only IHL (byte 0) and protocol
    (byte 9) are read by the parser, the rest is filler."""
    return struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload),
                       0, 0, 64, protocol, 0,
                       b"\x01\x02\x03\x04", b"\x05\x06\x07\x08")


def icmp_packet(icmp_type, icmp_code, inner=b"", ident=0, seq=0):
    """Outer IP + ICMP header (type, code, cksum, id, seq) + body."""
    header = struct.pack("!BBHHH", icmp_type, icmp_code, 0, ident, seq)
    return ip_header(1, header + inner) + header + inner


def udp_probe_packet(icmp_type, icmp_code, dst_port):
    inner_ip = ip_header(17, b"\x00" * 8)
    udp = struct.pack("!HHHH", 12345, dst_port, 8, 0)
    return icmp_packet(icmp_type, icmp_code, inner_ip + udp)


class TestPayloadAndPorts(unittest.TestCase):
    def test_payload_is_page_string_32_bytes(self):
        self.assertEqual(tr.PAYLOAD, b"codingchallenges.fyi trace route")
        self.assertEqual(len(tr.PAYLOAD), 32)

    def test_port_starts_at_33434_and_increments(self):
        self.assertEqual(tr.port_for(1, 0, 3), 33434)
        self.assertEqual(tr.port_for(1, 1, 3), 33435)
        self.assertEqual(tr.port_for(1, 2, 3), 33436)
        self.assertEqual(tr.port_for(2, 0, 3), 33437)

    def test_port_stays_in_range_and_wraps(self):
        ports = {tr.port_for(ttl, i, 3)
                 for ttl in range(1, 200) for i in range(3)}
        self.assertTrue(all(33434 <= p <= 33534 for p in ports))
        # Global probe 101 wraps: 33434 + (101 % 101) == 33434.
        self.assertEqual(tr.port_for(102, 0, 1), 33434)
        self.assertEqual(tr.port_for(102, 1, 1), 33435)


class TestEchoBuilding(unittest.TestCase):
    def test_checksum_known_vector(self):
        # Echo header with zero checksum + empty payload: one's complement
        # of 0x0800 is 0xf7ff.
        self.assertEqual(tr.checksum(b"\x08\x00\x00\x00\x00\x00\x00\x00"), 0xF7FF)
        self.assertEqual(tr.checksum(b""), 0xFFFF)

    def test_echo_request_fields_and_self_consistent_checksum(self):
        pkt = tr.build_echo_request(0x1234, 7)
        icmp_type, code, chk, ident, seq = struct.unpack("!BBHHH", pkt[:8])
        self.assertEqual((icmp_type, code, ident, seq), (8, 0, 0x1234, 7))
        self.assertEqual(pkt[8:], tr.PAYLOAD)
        self.assertEqual(tr.checksum(pkt), 0)  # valid packet re-sums to 0


class TestIcmpParsing(unittest.TestCase):
    def test_time_exceeded_recovers_embedded_udp_port(self):
        info = tr.parse_icmp_packet(udp_probe_packet(11, 0, 33434))
        self.assertIsNotNone(info)
        self.assertEqual((info.type, info.code), (11, 0))
        self.assertEqual(info.inner_dst_port, 33434)
        self.assertFalse(tr.is_destination_reached(info))

    def test_dest_unreachable_port_unreachable_is_reached(self):
        info = tr.parse_icmp_packet(udp_probe_packet(3, 3, 33440))
        self.assertEqual((info.type, info.code), (3, 3))
        self.assertEqual(info.inner_dst_port, 33440)
        self.assertTrue(tr.is_destination_reached(info))

    def test_dest_unreachable_other_code_is_not_reached(self):
        info = tr.parse_icmp_packet(udp_probe_packet(3, 1, 33440))
        self.assertFalse(tr.is_destination_reached(info))

    def test_echo_reply_is_reached_with_id_and_seq(self):
        info = tr.parse_icmp_packet(icmp_packet(0, 0, ident=0xCC01, seq=2))
        self.assertEqual((info.type, info.code), (0, 0))
        self.assertEqual((info.inner_id, info.inner_seq), (0xCC01, 2))
        self.assertTrue(tr.is_destination_reached(info))

    def test_time_exceeded_with_embedded_icmp_recovers_id_seq(self):
        inner_ip = ip_header(1, b"\x00" * 8)
        inner_icmp = struct.pack("!BBHHH", 8, 0, 0, 0xCC01, 2)
        pkt = icmp_packet(11, 0, inner_ip + inner_icmp)
        info = tr.parse_icmp_packet(pkt)
        self.assertEqual((info.inner_id, info.inner_seq), (0xCC01, 2))
        self.assertFalse(tr.is_destination_reached(info))

    def test_malformed_packets_return_none_not_raise(self):
        for bad in (b"", b"\x45", b"\x45" * 10,
                    ip_header(1),  # IP header only, no ICMP header
                    icmp_packet(11, 0, b"\x45\x00")):  # truncated inner header
            self.assertIsNone(tr.parse_icmp_packet(bad))

    def test_reached_truth_table(self):
        self.assertFalse(tr.is_destination_reached(None))
        self.assertFalse(tr.is_destination_reached(tr.IcmpInfo(11, 0)))
        self.assertFalse(tr.is_destination_reached(tr.IcmpInfo(8, 0)))
        self.assertTrue(tr.is_destination_reached(tr.IcmpInfo(0, 0)))
        self.assertTrue(tr.is_destination_reached(tr.IcmpInfo(3, 3)))


class TestFormatting(unittest.TestCase):
    def test_header_matches_page_step1_form(self):
        self.assertEqual(
            tr.format_header("dns.google.com", "8.8.4.4", 64),
            "traceroute to dns.google.com (8.8.4.4), 64 hops max, 32 byte packets")

    def test_resolve_display_fallback(self):
        with mock.patch("socket.gethostbyaddr",
                        side_effect=socket.herror("no host")):
            self.assertEqual(tr.resolve_display("192.168.68.1"),
                             "192.168.68.1 (192.168.68.1)")
        with mock.patch("socket.gethostbyaddr",
                        return_value=("broadband", [], ["192.168.1.1"])):
            self.assertEqual(tr.resolve_display("192.168.1.1"),
                             "broadband (192.168.1.1)")

    def test_hop_all_timeouts(self):
        hop = tr.HopRecord(3, [tr.ProbeResult(), tr.ProbeResult(),
                               tr.ProbeResult()])
        self.assertEqual(tr.format_hop(hop, resolve=False), " 3  * * *")

    def test_hop_single_probe_with_timing(self):
        hop = tr.HopRecord(1, [tr.ProbeResult("192.168.68.1", 5.131)])
        self.assertEqual(tr.format_hop(hop, resolve=False),
                         " 1  192.168.68.1 (192.168.68.1) 5.131 ms")

    def test_hop_same_host_appends_timings(self):
        hop = tr.HopRecord(1, [tr.ProbeResult("10.0.0.1", 1.0),
                               tr.ProbeResult("10.0.0.1", 2.0),
                               tr.ProbeResult("10.0.0.1", 3.0)])
        self.assertEqual(tr.format_hop(hop, resolve=False),
                         " 1  10.0.0.1 (10.0.0.1) 1.000 ms  "
                         "10.0.0.1 (10.0.0.1) 2.000 ms  "
                         "10.0.0.1 (10.0.0.1) 3.000 ms")

    def test_hop_different_responders_use_continuation_lines(self):
        hop = tr.HopRecord(5, [tr.ProbeResult("72.14.216.236", 41.609),
                               tr.ProbeResult("195.66.236.125", 33.368),
                               tr.ProbeResult("72.14.216.236", 38.354)])
        # Third probe differs from the second responder, so it too
        # starts a continuation line (each host change = new line).
        self.assertEqual(
            tr.format_hop(hop, resolve=False),
            " 5  72.14.216.236 (72.14.216.236) 41.609 ms\n"
            "     195.66.236.125 (195.66.236.125) 33.368 ms\n"
            "     72.14.216.236 (72.14.216.236) 38.354 ms")

    def test_hop_mixed_timeout_and_answer(self):
        hop = tr.HopRecord(6, [tr.ProbeResult("108.170.246.161", 44.235),
                               tr.ProbeResult(),
                               tr.ProbeResult("108.170.246.129", 37.994)])
        self.assertEqual(
            tr.format_hop(hop, resolve=False),
            " 6  108.170.246.161 (108.170.246.161) 44.235 ms  *\n"
            "     108.170.246.129 (108.170.246.129) 37.994 ms")


class FakeTransport:
    """Scripted probe answers: {(ttl, probe_index): (addr, rtt, reached)}."""

    def __init__(self, script):
        self.script = script

    def probe(self, ttl, probe_index, probes_per_hop, dest_ip, timeout):
        addr, rtt, reached = self.script.get(
            (ttl, probe_index), (None, None, False))
        return tr.ProbeResult(addr, rtt), reached


class TestTraceLoop(unittest.TestCase):
    def test_stops_at_destination_hop(self):
        transport = FakeTransport({
            (1, 0): ("192.168.68.1", 5.0, False),
            (2, 0): ("8.8.4.4", 40.0, True),
        })
        hops = tr.trace("8.8.4.4", 30, 1, 3.0, "udp", transport)
        self.assertEqual([h.ttl for h in hops], [1, 2])
        self.assertTrue(hops[1].reached)

    def test_all_timeout_hop_does_not_stop_trace(self):
        transport = FakeTransport({(2, 0): ("8.8.4.4", 40.0, True)})
        hops = tr.trace("8.8.4.4", 3, 1, 3.0, "udp", transport)
        self.assertEqual([h.ttl for h in hops], [1, 2])
        self.assertEqual(hops[0].probes[0].addr, None)

    def test_stops_at_max_hops_when_never_reached(self):
        hops = tr.trace("10.255.255.1", 3, 2, 3.0, "udp", FakeTransport({}))
        self.assertEqual(len(hops), 3)
        self.assertFalse(any(h.reached for h in hops))

    def test_reached_only_on_last_probe_of_hop_still_stops(self):
        transport = FakeTransport({(1, 2): ("8.8.4.4", 40.0, True)})
        hops = tr.trace("8.8.4.4", 30, 3, 3.0, "udp", transport)
        self.assertEqual(len(hops), 1)
        self.assertTrue(hops[0].reached)


class TestCli(unittest.TestCase):
    def test_no_args_exits_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            tr.main([])
        self.assertNotEqual(ctx.exception.code, 0)

    def test_main_with_fake_transport_prints_header_and_hops(self):
        script = {(1, 0): ("192.168.68.1", 5.131, False),
                  (2, 0): ("8.8.4.4", 35.859, True)}
        out = io.StringIO()
        with mock.patch("traceroute.resolve_host", return_value="8.8.4.4"), \
             mock.patch("traceroute.resolve_display",
                        side_effect=lambda ip, resolve=True: "%s (%s)" % (ip, ip)), \
             redirect_stdout(out):
            code = tr.main(["-q", "1", "--no-resolve", "dns.google.com"],
                           transport_factory=lambda method: FakeTransport(script))
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0],
                         "traceroute to dns.google.com (8.8.4.4), "
                         "30 hops max, 32 byte packets")
        self.assertIn("192.168.68.1 (192.168.68.1) 5.131 ms", lines[1])
        self.assertIn("8.8.4.4 (8.8.4.4) 35.859 ms", lines[2])

    def test_bad_option_values_exit_2(self):
        self.assertEqual(tr.main(["-m", "0", "example.com"]), 2)


if __name__ == "__main__":
    unittest.main()

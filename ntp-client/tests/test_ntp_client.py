#!/usr/bin/env python3
"""Tests for ntp_client.py. All network tests use a LOCAL fake NTP server
bound to 127.0.0.1 on an ephemeral port. No real public NTP server is ever
contacted by this suite, and the system clock is never touched.
"""

import socket
import struct
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ntp_client
from ntp_client import (
    MODE_CLIENT, MODE_SERVER, NTP_EPOCH_OFFSET, NtpError, build_request,
    compute_offset_delay, ntp_to_unix, parse_response, query,
    unix_to_ntp,
)


def _loopback_udp_blocked():
    """Probe once: can this sandbox send a UDP datagram to 127.0.0.1?

    In this sandbox the answer is no: sendto raises PermissionError
    (Errno 1, "Operation not permitted") — the same sandbox UDP block
    seen by earlier waves (e.g. Netcat UDP). The probe closes both
    sockets; it leaves no server running. Result is cached.
    """
    if _loopback_udp_blocked.cache is not None:
        return _loopback_udp_blocked.cache
    blocked = False
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(1)
        port = receiver.getsockname()[1]
        try:
            sender.sendto(b"probe", ("127.0.0.1", port))
            receiver.recvfrom(64)
        except PermissionError:
            blocked = True
        except socket.timeout:
            blocked = True  # loopback datagram never arrived either
    finally:
        sender.close()
        receiver.close()
    _loopback_udp_blocked.cache = blocked
    return blocked


_loopback_udp_blocked.cache = None
LOOPBACK_BLOCKED = _loopback_udp_blocked()
skip_if_loopback_blocked = unittest.skipIf(
    LOOPBACK_BLOCKED,
    "UDP loopback blocked in this sandbox (sendto -> EPERM); "
    "see docs/TEST_PLAN.md")


def make_response(request_data, stratum=2, receive_unix=1700000001.0,
                  transmit_unix=1700000001.5, version=4, mode=MODE_SERVER,
                  reference_unix=1700000000.0):
    """Build a fake server response echoing the request's transmit field."""
    # The response's origin field echoes the request's TRANSMIT field,
    # which sits at bytes 40-47 of the request (not 24-31: those are the
    # request's own, zero, origin field).
    origin = request_data[40:48] if len(request_data) >= 48 else b"\x00" * 8
    packet = bytearray(48)
    packet[0] = (0 << 6) | (version << 3) | mode
    packet[1] = stratum
    packet[2] = 6  # poll
    packet[3] = 0xEC  # precision, as signed byte -20
    packet[12:16] = b"GPS\x00"
    packet[16:24] = struct.pack(">II", *unix_to_ntp(reference_unix))
    packet[24:32] = origin
    packet[32:40] = struct.pack(">II", *unix_to_ntp(receive_unix))
    packet[40:48] = struct.pack(">II", *unix_to_ntp(transmit_unix))
    return bytes(packet)


class FakeNtpServer(threading.Thread):
    """One-shot UDP server: replies to a single request, then exits."""

    def __init__(self, reply_fn):
        super().__init__(daemon=True)
        self.reply_fn = reply_fn
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(10)
        self.port = self.sock.getsockname()[1]
        self.received = None

    def run(self):
        try:
            data, addr = self.sock.recvfrom(512)
            self.received = data
            self.sock.sendto(self.reply_fn(data), addr)
        except socket.timeout:
            pass
        finally:
            self.sock.close()


class TestConversions(unittest.TestCase):
    def test_unix_epoch_maps_to_ntp_epoch_offset(self):
        self.assertEqual(unix_to_ntp(0.0), (NTP_EPOCH_OFFSET, 0))

    def test_roundtrip(self):
        for value in (0.0, 1.5, 1700000000.25, 1700000000.999999):
            self.assertAlmostEqual(ntp_to_unix(*unix_to_ntp(value)), value,
                                   places=5)

    def test_half_second_fraction(self):
        sec, frac = unix_to_ntp(0.5)
        self.assertEqual((sec, frac), (NTP_EPOCH_OFFSET, 1 << 31))

    def test_negative_unix_rejected(self):
        with self.assertRaises(ValueError):
            unix_to_ntp(-1.0)


class TestRequestPacket(unittest.TestCase):
    def test_length_and_first_byte(self):
        packet, _ = build_request(1700000000.0)
        self.assertEqual(len(packet), 48)
        # LI 0, version 4, mode 3 (client) -> 0x23
        self.assertEqual(packet[0], 0x23)

    def test_transmit_field_matches_given_time(self):
        packet, transmit = build_request(1700000000.5)
        self.assertEqual(struct.unpack_from(">II", packet, 40), transmit)
        self.assertEqual(ntp_to_unix(*transmit), 1700000000.5)

    def test_other_fields_zero(self):
        packet, _ = build_request(1700000000.0)
        self.assertEqual(packet[1:40], b"\x00" * 39)


class TestParseResponse(unittest.TestCase):
    def test_decode_all_fields(self):
        request, transmit = build_request(1700000000.0)
        parsed = parse_response(make_response(request),
                                expected_origin=transmit)
        self.assertEqual(parsed["version"], 4)
        self.assertEqual(parsed["mode"], MODE_SERVER)
        self.assertEqual(parsed["stratum"], 2)
        self.assertEqual(parsed["reference_id"], b"GPS\x00")
        self.assertAlmostEqual(parsed["origin_timestamp"], 1700000000.0)
        self.assertAlmostEqual(parsed["receive_timestamp"], 1700000001.0)
        self.assertAlmostEqual(parsed["transmit_timestamp"], 1700000001.5)

    def test_short_packet_rejected(self):
        with self.assertRaises(NtpError):
            parse_response(b"\x00" * 20)

    def test_client_mode_response_rejected(self):
        request, _ = build_request(1700000000.0)
        bad = bytearray(make_response(request))
        bad[0] = (0 << 6) | (4 << 3) | MODE_CLIENT
        with self.assertRaises(NtpError):
            parse_response(bytes(bad))

    def test_stratum_zero_rejected(self):
        request, _ = build_request(1700000000.0)
        with self.assertRaises(NtpError):
            parse_response(make_response(request, stratum=0))

    def test_origin_mismatch_rejected(self):
        _request, transmit = build_request(1700000000.0)
        other, _ = build_request(1700000005.0)
        # Response echoes `other`'s transmit field, not `transmit`.
        with self.assertRaises(NtpError):
            parse_response(make_response(other), expected_origin=transmit)

    def test_longer_packet_accepted(self):
        request, transmit = build_request(1700000000.0)
        parsed = parse_response(make_response(request) + b"\x00" * 16,
                                expected_origin=transmit)
        self.assertEqual(parsed["stratum"], 2)


class TestOffsetDelay(unittest.TestCase):
    def test_formulas_from_page(self):
        # t0=0, t1=10, t2=12, t3=22: theta=((10-0)+(12-22))/2=0, delta=20
        offset, delay = compute_offset_delay(0, 10, 12, 22)
        self.assertEqual(offset, 0.0)
        self.assertEqual(delay, 20.0)

    def test_positive_offset_means_server_ahead(self):
        # Server clock 5 s ahead, 2 s round trip, 1 s each way.
        offset, delay = compute_offset_delay(100, 106, 106, 102)
        self.assertEqual(offset, 5.0)
        self.assertEqual(delay, 2.0)

    def test_zero_delay_symmetric(self):
        offset, delay = compute_offset_delay(100, 101, 101, 102)
        self.assertEqual(offset, 0.0)
        self.assertEqual(delay, 2.0)


class TestQueryAgainstFakeServer(unittest.TestCase):
    @skip_if_loopback_blocked
    def test_full_exchange(self):
        server = FakeNtpServer(
            lambda req: make_response(req, receive_unix=1700000001.0,
                                      transmit_unix=1700000001.5))
        server.start()
        try:
            result = query("127.0.0.1", port=server.port, timeout=5.0)
        finally:
            server.join(timeout=10)
        self.assertEqual(result["stratum"], 2)
        self.assertEqual(result["host"], "127.0.0.1")
        self.assertAlmostEqual(result["receive_timestamp"], 1700000001.0)
        self.assertAlmostEqual(result["transmit_timestamp"], 1700000001.5)
        # Delay on loopback must be small and non-negative-ish; offset is
        # dominated by the fake server's fixed timestamps vs real now, so
        # only check it is a finite number, not a plausible clock offset.
        self.assertTrue(result["delay_seconds"] >= 0)
        self.assertLess(result["delay_seconds"], 5.0)
        self.assertEqual(result["delay_seconds"],
                         (result["client_receive_timestamp"]
                          - result["client_send_timestamp"])
                         - (result["transmit_timestamp"]
                            - result["receive_timestamp"]))

    @skip_if_loopback_blocked
    def test_request_seen_by_server_is_a_client_packet(self):
        server = FakeNtpServer(lambda req: make_response(req))
        server.start()
        try:
            query("127.0.0.1", port=server.port, timeout=5.0)
        finally:
            server.join(timeout=10)
        self.assertIsNotNone(server.received)
        self.assertEqual(len(server.received), 48)
        self.assertEqual(server.received[0], 0x23)

    @skip_if_loopback_blocked
    def test_timeout_raises(self):
        # Bind a socket that never replies, on an ephemeral port.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            with self.assertRaises(NtpError):
                query("127.0.0.1", port=port, timeout=0.5)
        finally:
            sock.close()

    @skip_if_loopback_blocked
    def test_stratum_zero_server_raises(self):
        server = FakeNtpServer(lambda req: make_response(req, stratum=0))
        server.start()
        try:
            with self.assertRaises(NtpError):
                query("127.0.0.1", port=server.port, timeout=5.0)
        finally:
            server.join(timeout=10)


class TestCli(unittest.TestCase):
    @skip_if_loopback_blocked
    def test_main_against_fake_server(self):
        import io
        from contextlib import redirect_stdout
        server = FakeNtpServer(lambda req: make_response(req))
        server.start()
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = ntp_client.main(
                    ["127.0.0.1", "--port", str(server.port),
                     "--timeout", "5"])
            self.assertEqual(code, 0)
            self.assertIn("Offset:", buf.getvalue())
            self.assertIn("Round-trip delay:", buf.getvalue())
            self.assertIn("NOT changed", buf.getvalue())
        finally:
            server.join(timeout=10)

    @skip_if_loopback_blocked
    def test_main_timeout_exit_code(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            code = ntp_client.main(["127.0.0.1", "--port", str(port),
                                    "--timeout", "0.5"])
            self.assertEqual(code, 1)
        finally:
            sock.close()


class TestLoopbackAttempt(unittest.TestCase):
    def test_loopback_udp_attempt_is_documented(self):
        # This test IS the loopback attempt: it probes UDP to 127.0.0.1
        # and reports the outcome instead of pretending an exchange ran.
        if LOOPBACK_BLOCKED:
            self.skipTest("UDP loopback blocked in this sandbox "
                          "(sendto -> EPERM); exchange tests skipped, "
                          "encode/decode/formula tests still run")
        self.assertFalse(LOOPBACK_BLOCKED)


if __name__ == "__main__":
    unittest.main()

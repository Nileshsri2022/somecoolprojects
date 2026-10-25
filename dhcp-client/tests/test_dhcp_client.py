#!/usr/bin/env python3
"""Tests for dhcp_client.py. All network tests use a fake DHCP server
on 127.0.0.1 with an ephemeral port — never a real network broadcast,
never a real DHCP server, never a host-configuration change."""
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dhcp_client import (ACK, DECLINE, DISCOVER, NAK, OFFER, RELEASE,
                         REQUEST, DhcpClient, DhcpMessage, DhcpNakError,
                         Lease, build_decline, build_discover, build_release,
                         build_request, format_mac, parse_mac)

MAC = "aa:bb:cc:dd:ee:ff"
OFFERED = "192.168.1.100"
SERVER = "192.168.1.1"
MASK, ROUTER, DNS = "255.255.255.0", "192.168.1.1", "8.8.8.8"


def offer_msg(xid):
    return DhcpMessage(op=2, xid=xid, yiaddr=OFFERED, siaddr=SERVER,
                       chaddr=parse_mac(MAC), options={
                           53: bytes((OFFER,)), 54: bytes((192, 168, 1, 1)),
                           1: bytes((255, 255, 255, 0)),
                           3: bytes((192, 168, 1, 1)),
                           6: bytes((8, 8, 8, 8)), 51: (3600).to_bytes(4, "big"),
                       })


def ack_msg(xid):
    msg = offer_msg(xid)
    msg.options[53] = bytes((ACK,))
    return msg


class FakeServer:
    """Minimal DHCP server on loopback. mode: 'ack' or 'nak'."""

    def __init__(self, mode="ack", wrong_xid_first=False):
        self.mode = mode
        self.wrong_xid_first = wrong_xid_first
        self.received = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self._connected = False
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.2)
        self._stop = threading.Event()
        self._wrong_sent = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self.thread.join(timeout=5)
        self.sock.close()

    def _reply(self, addr, payload):
        # Connected UDP (the sandbox blocks unconnected sendto).
        # One socket, connected to the client on first contact and
        # kept for the whole handshake. Two earlier patterns failed
        # here and are deliberately NOT used: (1) a fresh reply
        # socket bound to the same port steals later incoming
        # packets (last-bound wins), and (2) closing/rebinding the
        # listener opens a window that drops the client's next
        # packet. Each FakeServer instance serves exactly one
        # client, so keeping the connection is safe.
        try:
            if not self._connected:
                self.sock.connect(addr)
                self._connected = True
            self.sock.send(payload)
        except OSError:
            return

    def _run(self):
        while not self._stop.is_set():
            try:
                if self._connected:
                    # recv(), NOT recvfrom(): calling recvfrom() on
                    # an already-connected socket makes its next
                    # send fail with EPERM in this sandbox
                    # (verified by experiment); recv() does not.
                    data = self.sock.recv(1500)
                    addr = None
                else:
                    data, addr = self.sock.recvfrom(1500)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                msg = DhcpMessage.from_bytes(data)
            except ValueError:
                continue
            self.received.append(msg)
            if msg.message_type == DISCOVER:
                if self.wrong_xid_first and not self._wrong_sent:
                    self._wrong_sent = True
                    self._reply(addr, offer_msg(msg.xid + 1).to_bytes())
                self._reply(addr, offer_msg(msg.xid).to_bytes())
            elif msg.message_type == REQUEST:
                reply = ack_msg(msg.xid) if self.mode == "ack" else \
                    DhcpMessage(op=2, xid=msg.xid, siaddr=SERVER,
                                chaddr=parse_mac(MAC),
                                options={53: bytes((NAK,))})
                self._reply(addr, reply.to_bytes())
            # DECLINE / RELEASE: recorded, no reply (per RFC 2131).


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestPackets(unittest.TestCase):
    def test_discover_round_trip(self):
        msg = build_discover(MAC, xid=0x12345678)
        raw = msg.to_bytes()
        self.assertEqual(raw[0:4], bytes((1, 1, 6, 0)))
        self.assertEqual(raw[236:240], bytes((99, 130, 83, 99)))
        back = DhcpMessage.from_bytes(raw)
        self.assertEqual(back.message_type, DISCOVER)
        self.assertEqual(back.xid, 0x12345678)
        self.assertEqual(back.flags, 0x8000)
        self.assertEqual(format_mac(back.chaddr), MAC)
        self.assertEqual(back.to_bytes(), raw)

    def test_all_types_round_trip(self):
        cases = [
            build_discover(MAC, xid=1),
            offer_msg(2),
            build_request(MAC, OFFERED, SERVER, xid=3),
            ack_msg(4),
            DhcpMessage(op=2, xid=5, options={53: bytes((NAK,))}),
            build_decline(MAC, OFFERED, SERVER, xid=6),
            build_release(MAC, OFFERED, SERVER, xid=7),
        ]
        for msg in cases:
            back = DhcpMessage.from_bytes(msg.to_bytes())
            self.assertEqual(back.message_type, msg.message_type)
            self.assertEqual(back.xid, msg.xid)

    def test_request_options(self):
        msg = build_request(MAC, OFFERED, SERVER, xid=9)
        self.assertEqual(msg.option_ip(50), OFFERED)
        self.assertEqual(msg.option_ip(54), SERVER)
        self.assertEqual(msg.options[55], bytes((1, 3, 6, 51)))

    def test_malformed_rejected(self):
        good = build_discover(MAC, xid=1).to_bytes()
        with self.assertRaises(ValueError):
            DhcpMessage.from_bytes(good[:100])
        bad_cookie = bytearray(good)
        bad_cookie[236] = 0
        with self.assertRaises(ValueError):
            DhcpMessage.from_bytes(bytes(bad_cookie))
        # Option length past end of packet: header + cookie + an
        # option claiming 200 bytes but supplying only 10.
        bad_opt = good[:240] + bytes((1, 200)) + bytes(10) + bytes((255,))
        with self.assertRaises(ValueError):
            DhcpMessage.from_bytes(bad_opt)
        no_type = DhcpMessage(op=2, xid=1)
        self.assertIsNone(DhcpMessage.from_bytes(no_type.to_bytes()).message_type)

    def test_mac_parsing(self):
        for text in ("aa:bb:cc:dd:ee:ff", "aa-bb-cc-dd-ee-ff", "aabbccddeeff"):
            self.assertEqual(parse_mac(text), parse_mac(MAC))
        for bad in ("aa:bb:cc", "aa:bb:cc:dd:ee:gg", "aabbccddeeff00"):
            with self.assertRaises(ValueError):
                parse_mac(bad)

    def test_ip_and_lease_helpers(self):
        ack = ack_msg(11)
        self.assertEqual(ack.option_ips(3), [ROUTER])
        self.assertEqual(ack.option_ips(6), [DNS])
        self.assertEqual(ack.option_u32(51), 3600)
        lease = Lease.from_ack(ack)
        self.assertEqual((lease.ip, lease.subnet_mask, lease.routers,
                          lease.dns_servers, lease.lease_time,
                          lease.server_id),
                         (OFFERED, MASK, [ROUTER], [DNS], 3600, SERVER))
        with self.assertRaises(ValueError):
            Lease.from_ack(offer_msg(12))
        with self.assertRaises(ValueError):
            Lease.from_ack(DhcpMessage(op=2, xid=13, yiaddr="0.0.0.0",
                                       options={53: bytes((ACK,))}))


class TestHandshake(unittest.TestCase):
    def test_full_dora(self):
        with FakeServer() as srv, DhcpClient(
                MAC, server="127.0.0.1", server_port=srv.port,
                timeout=5) as client:
            lease = client.obtain_lease()
        self.assertEqual((lease.ip, lease.subnet_mask, lease.routers,
                          lease.dns_servers, lease.lease_time,
                          lease.server_id),
                         (OFFERED, MASK, [ROUTER], [DNS], 3600, SERVER))

    def test_nak_is_error_not_lease(self):
        with FakeServer(mode="nak") as srv, DhcpClient(
                MAC, server="127.0.0.1", server_port=srv.port,
                timeout=5) as client:
            with self.assertRaises(DhcpNakError):
                client.obtain_lease()

    def test_timeout_no_server(self):
        with DhcpClient(MAC, server="127.0.0.1", server_port=free_port(),
                        timeout=0.5) as client:
            with self.assertRaises(TimeoutError):
                client.discover()

    def test_wrong_xid_offer_ignored(self):
        with FakeServer(wrong_xid_first=True) as srv, DhcpClient(
                MAC, server="127.0.0.1", server_port=srv.port,
                timeout=5) as client:
            lease = client.obtain_lease()
        self.assertEqual(lease.ip, OFFERED)

    def test_release_and_decline_packets(self):
        with FakeServer() as srv, DhcpClient(
                MAC, server="127.0.0.1", server_port=srv.port,
                timeout=5) as client:
            lease = client.obtain_lease()
            client.release(lease)
            offer = client.discover()
            client.decline(offer)
            # DECLINE is fire-and-forget (no reply), so wait until
            # the server thread has actually recorded it instead
            # of racing its shutdown: without this, the packet can
            # still be sitting in the socket buffer when the server
            # stops and the assertion then flakes.
            import time as _time
            _deadline = _time.time() + 2
            while (DECLINE not in
                   [m.message_type for m in srv.received]
                   and _time.time() < _deadline):
                _time.sleep(0.05)
        types = [m.message_type for m in srv.received]
        self.assertIn(RELEASE, types)
        self.assertIn(DECLINE, types)
        rel = [m for m in srv.received if m.message_type == RELEASE][0]
        self.assertEqual(rel.ciaddr, OFFERED)
        self.assertEqual(rel.option_ip(54), SERVER)
        dec = [m for m in srv.received if m.message_type == DECLINE][0]
        self.assertEqual(dec.option_ip(50), OFFERED)


class TestCli(unittest.TestCase):
    def test_cli_obtain_prints_lease(self):
        with FakeServer() as srv:
            proc = subprocess.run(
                [sys.executable, "dhcp_client.py", "--mac", MAC,
                 "--server", "127.0.0.1", "--server-port", str(srv.port)],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"ip: {OFFERED}", proc.stdout)
        self.assertIn("lease_time: 3600", proc.stdout)

    def test_cli_nak_exits_nonzero(self):
        with FakeServer(mode="nak") as srv:
            proc = subprocess.run(
                [sys.executable, "dhcp_client.py", "--mac", MAC,
                 "--server", "127.0.0.1", "--server-port", str(srv.port)],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn(f"ip: {OFFERED}", proc.stdout)


if __name__ == "__main__":
    unittest.main()

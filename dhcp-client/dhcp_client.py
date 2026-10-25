#!/usr/bin/env python3
"""DHCP client (RFC 2131) — Coding Challenge #94.

Python 3 standard library only. Builds, sends, receives and parses
DHCPDISCOVER / DHCPOFFER / DHCPREQUEST / DHCPACK / DHCPNAK /
DHCPDECLINE / DHCPRELEASE packets, and runs the DORA handshake
against a DHCP server.

Safety: by default the client unicasts to a given server address
(for loopback testing). Live broadcast use (--broadcast, port 68)
needs broadcast privileges and is documented in README.md; this
program never changes the host's network configuration — on ACK it
returns and prints the Lease, and RELEASE only sends a packet.

Usage:
    python3 dhcp_client.py --mac aa:bb:cc:dd:ee:ff \
        --server 127.0.0.1 --server-port 6767 --timeout 5
"""

import argparse
import ipaddress
import random
import socket
import struct
import sys

MAGIC_COOKIE = bytes((99, 130, 83, 99))
HEADER = struct.Struct("!BBBBIHH4s4s4s4s16s64s128s")
HEADER_SIZE = HEADER.size  # 236
MIN_PACKET = HEADER_SIZE + 4

# DHCP message types (option 53).
DISCOVER, OFFER, REQUEST, DECLINE, ACK, NAK, RELEASE, INFORM = range(1, 9)
TYPE_NAMES = {1: "DHCPDISCOVER", 2: "DHCPOFFER", 3: "DHCPREQUEST",
              4: "DHCPDECLINE", 5: "DHCPACK", 6: "DHCPNAK",
              7: "DHCPRELEASE", 8: "DHCPINFORM"}

# Option codes (RFC 2132).
OPT_PAD, OPT_SUBNET, OPT_ROUTER, OPT_DNS = 0, 1, 3, 6
OPT_HOSTNAME, OPT_REQUESTED_IP, OPT_LEASE = 12, 50, 51
OPT_MSG_TYPE, OPT_SERVER_ID, OPT_PARAM_LIST = 53, 54, 55
OPT_END = 255

BROADCAST_FLAG = 0x8000
SERVER_PORT, CLIENT_PORT = 67, 68
ZERO_IP = "0.0.0.0"


class DhcpError(Exception):
    """Base class for DHCP client errors."""


class DhcpNakError(DhcpError):
    """The server refused the request (DHCPNAK)."""


def parse_mac(text):
    """Accept aa:bb:cc:dd:ee:ff, aa-bb-..., or 12 bare hex digits."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) != 6:
            raise ValueError("MAC must be 6 bytes")
        return bytes(text)
    cleaned = text.replace(":", "").replace("-", "").strip()
    if len(cleaned) != 12:
        raise ValueError(f"bad MAC address: {text!r}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError(f"bad MAC address: {text!r}") from None


def format_mac(mac):
    return ":".join(f"{b:02x}" for b in mac)


def _ip_to_bytes(addr):
    return ipaddress.IPv4Address(addr).packed


def _bytes_to_ip(data):
    return str(ipaddress.IPv4Address(data))


def _opt_ip(value):
    return _ip_to_bytes(value)


def _opt_ips(values):
    return b"".join(_ip_to_bytes(v) for v in values)


def _opt_u32(value):
    return struct.pack("!I", value)


class DhcpMessage:
    """One DHCP packet: fixed header + options dict (code -> bytes)."""

    def __init__(self, op=1, xid=0, flags=0, ciaddr=ZERO_IP, yiaddr=ZERO_IP,
                 siaddr=ZERO_IP, giaddr=ZERO_IP, chaddr=b"\x00" * 6,
                 secs=0, hops=0, options=None):
        self.op = op
        self.htype = 1
        self.hlen = 6
        self.hops = hops
        self.xid = xid
        self.secs = secs
        self.flags = flags
        self.ciaddr = ciaddr
        self.yiaddr = yiaddr
        self.siaddr = siaddr
        self.giaddr = giaddr
        self.chaddr = bytes(chaddr)[:6].ljust(6, b"\x00")
        self.options = dict(options or {})

    @property
    def message_type(self):
        raw = self.options.get(OPT_MSG_TYPE)
        return raw[0] if raw else None

    @property
    def type_name(self):
        return TYPE_NAMES.get(self.message_type, "UNKNOWN")

    def option_ip(self, code):
        raw = self.options.get(code)
        return _bytes_to_ip(raw[:4]) if raw and len(raw) >= 4 else None

    def option_ips(self, code):
        raw = self.options.get(code) or b""
        return [_bytes_to_ip(raw[i:i + 4]) for i in range(0, len(raw) - 3, 4)]

    def option_u32(self, code):
        raw = self.options.get(code)
        return struct.unpack("!I", raw[:4])[0] if raw and len(raw) >= 4 else None

    def option_string(self, code):
        raw = self.options.get(code)
        return raw.decode("ascii", "replace") if raw is not None else None

    def to_bytes(self):
        chaddr = self.chaddr.ljust(16, b"\x00")
        header = HEADER.pack(self.op, self.htype, self.hlen, self.hops,
                             self.xid, self.secs, self.flags,
                             _ip_to_bytes(self.ciaddr),
                             _ip_to_bytes(self.yiaddr),
                             _ip_to_bytes(self.siaddr),
                             _ip_to_bytes(self.giaddr),
                             chaddr, b"\x00" * 64, b"\x00" * 128)
        opts = bytearray(MAGIC_COOKIE)
        for code, value in self.options.items():
            if len(value) > 255:
                raise ValueError(f"option {code} too long")
            opts += bytes((code, len(value))) + value
        opts.append(OPT_END)
        return header + bytes(opts)

    @classmethod
    def from_bytes(cls, data):
        if len(data) < MIN_PACKET:
            raise ValueError(f"DHCP packet too short: {len(data)} bytes")
        if data[HEADER_SIZE:HEADER_SIZE + 4] != MAGIC_COOKIE:
            raise ValueError("bad DHCP magic cookie")
        (op, _htype, hlen, hops, xid, secs, flags, ciaddr, yiaddr,
         siaddr, giaddr, chaddr, _sname, _file) = HEADER.unpack(
            data[:HEADER_SIZE])
        msg = cls(op=op, xid=xid, flags=flags, secs=secs, hops=hops,
                  ciaddr=_bytes_to_ip(ciaddr), yiaddr=_bytes_to_ip(yiaddr),
                  siaddr=_bytes_to_ip(siaddr), giaddr=_bytes_to_ip(giaddr),
                  chaddr=chaddr[:hlen] if hlen <= 16 else chaddr[:6])
        pos = HEADER_SIZE + 4
        while pos < len(data):
            code = data[pos]
            if code == OPT_END:
                break
            if code == OPT_PAD:
                pos += 1
                continue
            if pos + 1 >= len(data):
                raise ValueError("truncated DHCP option")
            length = data[pos + 1]
            if pos + 2 + length > len(data):
                raise ValueError("DHCP option length past end of packet")
            msg.options[code] = data[pos + 2:pos + 2 + length]
            pos += 2 + length
        return msg


def _new_xid(xid):
    return xid if xid is not None else random.getrandbits(32)


def build_discover(mac, xid=None, hostname=None):
    return DhcpMessage(xid=_new_xid(xid), flags=BROADCAST_FLAG,
                       chaddr=parse_mac(mac), options={
                           OPT_MSG_TYPE: bytes((DISCOVER,)),
                           OPT_PARAM_LIST: bytes((OPT_SUBNET, OPT_ROUTER,
                                                  OPT_DNS, OPT_LEASE)),
                           **({OPT_HOSTNAME: hostname.encode("ascii")}
                              if hostname else {}),
                       })


def build_request(mac, offered_ip, server_id, xid=None, hostname=None):
    opts = {OPT_MSG_TYPE: bytes((REQUEST,)),
            OPT_REQUESTED_IP: _opt_ip(offered_ip),
            OPT_SERVER_ID: _opt_ip(server_id),
            OPT_PARAM_LIST: bytes((OPT_SUBNET, OPT_ROUTER, OPT_DNS,
                                   OPT_LEASE))}
    if hostname:
        opts[OPT_HOSTNAME] = hostname.encode("ascii")
    return DhcpMessage(xid=_new_xid(xid), flags=BROADCAST_FLAG,
                       chaddr=parse_mac(mac), options=opts)


def build_decline(mac, offered_ip, server_id, xid=None):
    return DhcpMessage(xid=_new_xid(xid), chaddr=parse_mac(mac), options={
        OPT_MSG_TYPE: bytes((DECLINE,)),
        OPT_REQUESTED_IP: _opt_ip(offered_ip),
        OPT_SERVER_ID: _opt_ip(server_id),
    })


def build_release(mac, leased_ip, server_id, xid=None):
    return DhcpMessage(xid=_new_xid(xid), ciaddr=leased_ip,
                       chaddr=parse_mac(mac), options={
                           OPT_MSG_TYPE: bytes((RELEASE,)),
                           OPT_SERVER_ID: _opt_ip(server_id),
                       })


class Lease:
    """A confirmed lease from a DHCPACK."""

    def __init__(self, ip, subnet_mask=None, routers=None, dns_servers=None,
                 lease_time=None, server_id=None, xid=None):
        self.ip, self.subnet_mask = ip, subnet_mask
        self.routers, self.dns_servers = routers or [], dns_servers or []
        self.lease_time, self.server_id, self.xid = lease_time, server_id, xid

    @classmethod
    def from_ack(cls, msg):
        if msg.message_type != ACK:
            raise ValueError(f"expected DHCPACK, got {msg.type_name}")
        if msg.yiaddr == ZERO_IP:
            raise ValueError("DHCPACK with no assigned address")
        return cls(ip=msg.yiaddr, subnet_mask=msg.option_ip(OPT_SUBNET),
                   routers=msg.option_ips(OPT_ROUTER),
                   dns_servers=msg.option_ips(OPT_DNS),
                   lease_time=msg.option_u32(OPT_LEASE),
                   server_id=msg.option_ip(OPT_SERVER_ID), xid=msg.xid)

    def __str__(self):
        lines = [f"ip: {self.ip}",
                 f"subnet_mask: {self.subnet_mask or '(none)'}",
                 f"routers: {', '.join(self.routers) or '(none)'}",
                 f"dns_servers: {', '.join(self.dns_servers) or '(none)'}",
                 f"lease_time: {self.lease_time if self.lease_time is not None else '(none)'}",
                 f"server_id: {self.server_id or '(none)'}"]
        return "\n".join(lines)


class DhcpClient:
    """UDP DHCP client. Default target is unicast (loopback-safe);
    pass broadcast=True for real-network use (see README.md)."""

    def __init__(self, mac, server="255.255.255.255", server_port=SERVER_PORT,
                 client_port=0, timeout=5.0, broadcast=False, hostname=None,
                 xid_factory=None):
        self.mac = parse_mac(mac)
        self.server, self.server_port = server, server_port
        self.timeout, self.hostname = timeout, hostname
        self._xid_factory = xid_factory or (lambda: random.getrandbits(32))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", client_port))
        self.sock.settimeout(timeout)
        self.target = ("255.255.255.255" if broadcast else server, server_port)
        # Connected UDP for unicast: equivalent to sendto/recvfrom for a
        # single peer, and required in sandboxes where unconnected UDP
        # sendto is blocked (same workaround as the dns-resolver
        # project). Broadcast mode keeps sendto/recvfrom, since a
        # broadcast peer cannot be a connected peer.
        self._connected = not broadcast
        if self._connected:
            self.sock.connect(self.target)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.sock.close()

    def _send(self, msg):
        if self._connected:
            self.sock.send(msg.to_bytes())
        else:
            self.sock.sendto(msg.to_bytes(), self.target)

    def _wait_for(self, xid, wanted_type):
        """Wait (bounded) for a BOOTREPLY with this xid and type,
        ignoring unrelated traffic. Raises TimeoutError."""
        while True:
            try:
                if self._connected:
                    data = self.sock.recv(1500)
                else:
                    data, _addr = self.sock.recvfrom(1500)
            except ConnectionRefusedError:
                # Connected UDP: an ICMP port-unreachable for a packet
                # sent to a momentarily closed port surfaces here once
                # and then clears; it is not a reply, so keep waiting
                # until the real timeout. (This is also how the
                # no-server timeout test behaves in the sandbox.)
                continue
            except socket.timeout:
                raise TimeoutError(
                    f"no {TYPE_NAMES.get(wanted_type, wanted_type)} "
                    f"for xid {xid:#x} within {self.timeout}s") from None
            try:
                msg = DhcpMessage.from_bytes(data)
            except ValueError:
                continue  # malformed traffic is not our reply
            if msg.op != 2 or msg.xid != xid:
                continue
            if msg.message_type == wanted_type:
                return msg
            if wanted_type == ACK and msg.message_type == NAK:
                raise DhcpNakError("server sent DHCPNAK")

    def discover(self, xid=None):
        xid = xid if xid is not None else self._xid_factory()
        msg = build_discover(self.mac, xid=xid, hostname=self.hostname)
        self._send(msg)
        return self._wait_for(xid, OFFER)

    def request(self, offer, xid=None):
        xid = xid if xid is not None else self._xid_factory()
        server_id = offer.option_ip(OPT_SERVER_ID) or offer.siaddr
        if server_id == ZERO_IP:
            raise DhcpError("OFFER carries no server identifier")
        msg = build_request(self.mac, offer.yiaddr, server_id, xid=xid,
                            hostname=self.hostname)
        self._send(msg)
        return self._wait_for(xid, ACK)

    def obtain_lease(self):
        offer = self.discover()
        ack = self.request(offer)
        return Lease.from_ack(ack)

    def release(self, lease):
        msg = build_release(self.mac, lease.ip, lease.server_id or ZERO_IP)
        self._send(msg)
        return msg.to_bytes()

    def decline(self, offer):
        server_id = offer.option_ip(OPT_SERVER_ID) or offer.siaddr
        msg = build_decline(self.mac, offer.yiaddr, server_id)
        self._send(msg)
        return msg.to_bytes()


def main(argv=None):
    parser = argparse.ArgumentParser(description="DHCP client (RFC 2131)")
    parser.add_argument("--mac", required=True, help="client MAC address")
    parser.add_argument("--server", default="127.0.0.1",
                        help="DHCP server address (default: 127.0.0.1)")
    parser.add_argument("--server-port", type=int, default=SERVER_PORT)
    parser.add_argument("--client-port", type=int, default=0,
                        help="local UDP port (default: ephemeral; "
                        "use 68 for live use, needs privileges)")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--hostname", default=None)
    parser.add_argument("--xid", type=int, default=None,
                        help="fixed transaction id (for testing)")
    parser.add_argument("--broadcast", action="store_true",
                        help="send to 255.255.255.255 instead of --server")
    parser.add_argument("--release-after", action="store_true")
    parser.add_argument("--decline", action="store_true",
                        help="discover and decline the offer instead "
                        "of requesting it")
    args = parser.parse_args(argv)
    try:
        with DhcpClient(args.mac, server=args.server,
                        server_port=args.server_port,
                        client_port=args.client_port, timeout=args.timeout,
                        broadcast=args.broadcast, hostname=args.hostname,
                        xid_factory=(lambda: args.xid) if args.xid is not None
                        else None) as client:
            if args.decline:
                offer = client.discover()
                client.decline(offer)
                print(f"declined offer {offer.yiaddr} from "
                      f"{offer.option_ip(OPT_SERVER_ID) or offer.siaddr}")
                return 0
            lease = client.obtain_lease()
            print(lease)
            if args.release_after:
                client.release(lease)
                print(f"released {lease.ip}")
            return 0
    except (DhcpError, TimeoutError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

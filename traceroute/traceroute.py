#!/usr/bin/env python3
"""Traceroute — Build Your Own Traceroute (codingchallenges.fyi).

Sends TTL-incrementing probes (UDP by default, ICMP Echo with
--method icmp) and reports each hop from the ICMP replies:
Time Exceeded (type 11) from intermediate routers, Destination
Unreachable / Port Unreachable (type 3, code 3) or Echo Reply
(type 0) from the destination. No reply within the timeout prints
`*` for that probe.

Python 3 standard library only.

Privilege note: receiving ICMP replies needs a raw socket, which
on Linux requires root / CAP_NET_RAW. Without it, socket creation
fails with a clear error and no trace output is fabricated. All
packet building, parsing and formatting below is privilege-free
and unit-tested without any socket.
"""

import argparse
import select
import socket
import struct
import sys
import time
from dataclasses import dataclass, field

BASE_PORT = 33434
LAST_PORT = 33534
PAYLOAD = b"codingchallenges.fyi trace route"  # 32 bytes, the page's string
DEFAULT_MAX_HOPS = 30
DEFAULT_PROBES = 3
DEFAULT_TIMEOUT = 3.0

ICMP_ECHO_REPLY = 0
ICMP_DEST_UNREACH = 3
ICMP_ECHO_REQUEST = 8
ICMP_TIME_EXCEEDED = 11
UNREACH_PORT = 3  # code 3: port unreachable == probe arrived (UDP method)


def checksum(data):
    """RFC 1071 Internet checksum. Empty input checksums to 0xffff."""
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) + data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_echo_request(identifier, sequence, payload=PAYLOAD):
    """Build an ICMP Echo Request packet (type 8, code 0)."""
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, 0, identifier, sequence)
    chk = checksum(header + payload)
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, chk, identifier, sequence)
    return header + payload


def port_for(ttl, probe_index, probes_per_hop):
    """Destination port for one probe, inside 33434-33534, wrapping."""
    span = LAST_PORT - BASE_PORT + 1
    global_index = (ttl - 1) * probes_per_hop + probe_index
    return BASE_PORT + (global_index % span)


@dataclass
class IcmpInfo:
    """Parsed ICMP reply. `inner_dst_port` / `inner_id` / `inner_seq`
    describe the original probe, recovered from the embedded header
    (Time Exceeded / Destination Unreachable carry it; Echo Reply
    carries id/sequence directly)."""
    type: int
    code: int
    inner_dst_port: int = None
    inner_id: int = None
    inner_seq: int = None


def parse_icmp_packet(data):
    """Parse one received IPv4 datagram carrying ICMP.

    Returns an IcmpInfo, or None for truncated/garbage input.
    Never raises on malformed input: a bad packet is ignored by
    the caller, exactly like an unmatched reply.
    """
    try:
        if len(data) < 20:
            return None
        ihl = (data[0] & 0x0F) * 4
        if ihl < 20 or len(data) < ihl + 8:
            return None
        icmp_type, icmp_code = data[ihl], data[ihl + 1]
        body = data[ihl + 8:]
        if icmp_type == ICMP_ECHO_REPLY:
            # id/sequence are bytes 4-7 of the ICMP header itself.
            ident, seq = struct.unpack("!HH", data[ihl + 4:ihl + 8])
            return IcmpInfo(icmp_type, icmp_code, inner_id=ident, inner_seq=seq)
        if icmp_type in (ICMP_TIME_EXCEEDED, ICMP_DEST_UNREACH):
            # Embedded original IPv4 header + first 8 bytes of its payload.
            if len(body) < 20:
                return None
            inner_ihl = (body[0] & 0x0F) * 4
            if inner_ihl < 20 or len(body) < inner_ihl + 8:
                return None
            inner = body[inner_ihl:inner_ihl + 8]
            protocol = body[9]
            if protocol == 17:  # UDP: src port, dst port, ...
                _src, dst_port = struct.unpack("!HH", inner[:4])
                return IcmpInfo(icmp_type, icmp_code, inner_dst_port=dst_port)
            if protocol == 1:  # ICMP: type, code, cksum, id, seq
                ident, seq = struct.unpack("!HH", inner[4:8])
                return IcmpInfo(icmp_type, icmp_code, inner_id=ident, inner_seq=seq)
            return IcmpInfo(icmp_type, icmp_code)
        return IcmpInfo(icmp_type, icmp_code)
    except (IndexError, struct.error):
        return None


def is_destination_reached(info):
    """True when this ICMP reply means the probe arrived at its target."""
    if info is None:
        return False
    if info.type == ICMP_ECHO_REPLY:
        return True
    if info.type == ICMP_DEST_UNREACH and info.code == UNREACH_PORT:
        return True
    return False


def resolve_display(ip, resolve=True):
    """'hostname (ip)' if reverse DNS works, else 'ip (ip)' (page Step 3)."""
    if not resolve:
        return "%s (%s)" % (ip, ip)
    try:
        host = socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        host = ip
    return "%s (%s)" % (host, ip)


@dataclass
class ProbeResult:
    addr: str = None  # None == timeout, printed as '*'
    rtt_ms: float = None


@dataclass
class HopRecord:
    ttl: int
    probes: list = field(default_factory=list)
    reached: bool = False


def format_header(host, ip, max_hops, packet_size=len(PAYLOAD)):
    return "traceroute to %s (%s), %d hops max, %d byte packets" % (
        host, ip, max_hops, packet_size)


def format_hop(record, resolve=True):
    """Hop lines. Rule: a probe joins the current line unless it is
    from a *different named host* than the previous named probe, in
    which case it starts a continuation line (indented, no hop
    number), as in the page's intro example. Timeouts (`*`) never
    start a new line; they just append to the current one."""
    lines = []
    current_host = None
    for probe in record.probes:
        if probe.addr is None:
            if not lines:
                lines.append("%2d  *" % record.ttl)
            else:
                # Single space after a '*', double space after a timing,
                # matching classic traceroute ('* * *' vs 'a ms  b ms').
                lines[-1] += " *" if lines[-1].endswith("*") else "  *"
            continue
        text = "%s %.3f ms" % (resolve_display(probe.addr, resolve), probe.rtt_ms)
        if not lines:
            lines.append("%2d  %s" % (record.ttl, text))
        elif current_host is None or probe.addr == current_host:
            lines[-1] += (" " if lines[-1].endswith("*") else "  ") + text
        else:
            lines.append("     " + text)
        current_host = probe.addr
    if not lines:
        lines.append("%2d  " % record.ttl)
    return "\n".join(lines)


class RealTransport:
    """Live sockets: one send socket, one raw ICMP receive socket."""

    def __init__(self, method):
        self.method = method
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                       socket.IPPROTO_ICMP)
        if method == "icmp":
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                           socket.IPPROTO_ICMP)
        else:
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                           socket.IPPROTO_UDP)

    def close(self):
        self.send_sock.close()
        self.recv_sock.close()

    def probe(self, ttl, probe_index, probes_per_hop, dest_ip, timeout):
        """One probe. Returns (ProbeResult, reached_bool)."""
        self.send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
        start = time.monotonic()
        deadline = start + timeout
        if self.method == "icmp":
            ident = 0xCC00 + (ttl % 0x100)
            seq = probe_index
            packet = build_echo_request(ident, seq)
            match = ("icmp", ident, seq)
            self.send_sock.sendto(packet, (dest_ip, 0))
        else:
            port = port_for(ttl, probe_index, probes_per_hop)
            match = ("udp", port)
            self.send_sock.sendto(PAYLOAD, (dest_ip, port))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ProbeResult(), False
            ready, _, _ = select.select([self.recv_sock], [], [], remaining)
            if not ready:
                return ProbeResult(), False
            try:
                data, (addr, _port) = self.recv_sock.recvfrom(65535)
            except OSError:
                return ProbeResult(), False
            info = parse_icmp_packet(data)
            if info is None:
                continue
            if match[0] == "udp":
                if info.inner_dst_port is not None and info.inner_dst_port != match[1]:
                    continue  # reply to some other probe; keep waiting
            else:
                if (info.inner_id is not None and info.inner_id != match[1]) or \
                   (info.inner_seq is not None and info.inner_seq != match[2]):
                    continue
            rtt = (time.monotonic() - start) * 1000.0
            return ProbeResult(addr, rtt), is_destination_reached(info)


def trace(dest_ip, max_hops, probes, timeout, method, transport):
    """TTL loop. Talks only to `transport.probe(...)`; see TEST_PLAN."""
    hops = []
    for ttl in range(1, max_hops + 1):
        record = HopRecord(ttl)
        for i in range(probes):
            result, reached = transport.probe(ttl, i, probes, dest_ip, timeout)
            record.probes.append(result)
            if reached:
                record.reached = True
        hops.append(record)
        if record.reached:
            break
    return hops


def resolve_host(host):
    """First IPv4 address for host; warns (stderr) if there are several."""
    infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    if not infos:
        raise socket.gaierror("no IPv4 address found for %s" % host)
    ip = infos[0][4][0]
    if len(infos) > 1:
        print("traceroute: Warning: %s has multiple addresses; using %s"
              % (host, ip), file=sys.stderr)
    return ip


def build_parser():
    parser = argparse.ArgumentParser(
        description="Trace the route packets take to a host (UDP probes, "
                    "ICMP replies). Needs raw-socket privileges for live use.")
    parser.add_argument("host", help="hostname or IPv4 address to trace to")
    parser.add_argument("-m", "--max-hops", type=int, default=DEFAULT_MAX_HOPS,
                        help="maximum hops (default %(default)s)")
    parser.add_argument("-q", "--probes", type=int, default=DEFAULT_PROBES,
                        help="probes per hop (default %(default)s)")
    parser.add_argument("-w", "--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="seconds to wait per probe (default %(default)s)")
    parser.add_argument("--method", choices=("udp", "icmp"), default="udp",
                        help="probe type (default %(default)s)")
    parser.add_argument("--no-resolve", action="store_true",
                        help="do not resolve hop IPs to hostnames")
    return parser


def main(argv=None, transport_factory=None):
    """`transport_factory(method)` is injectable for tests; default
    builds a RealTransport (needs privileges). Returns exit code."""
    args = build_parser().parse_args(argv)
    if args.max_hops < 1 or args.probes < 1 or args.timeout <= 0:
        print("traceroute: max-hops and probes must be >= 1, timeout > 0",
              file=sys.stderr)
        return 2
    try:
        dest_ip = resolve_host(args.host)
    except socket.gaierror as exc:
        print("traceroute: cannot resolve %s: %s" % (args.host, exc),
              file=sys.stderr)
        return 2
    print(format_header(args.host, dest_ip, args.max_hops))
    try:
        transport = (transport_factory(args.method) if transport_factory
                     else RealTransport(args.method))
    except PermissionError as exc:
        print("traceroute: cannot open raw ICMP socket (%s). Live tracing "
              "needs root or CAP_NET_RAW; packet parsing and formatting "
              "are still covered by the unit tests." % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("traceroute: socket error: %s" % exc, file=sys.stderr)
        return 1
    try:
        hops = trace(dest_ip, args.max_hops, args.probes, args.timeout,
                     args.method, transport)
    except (PermissionError, OSError) as exc:
        print("traceroute: probe failed (%s). Live tracing needs raw-socket "
              "privileges and a permitted network path; see README.md."
              % exc, file=sys.stderr)
        return 1
    finally:
        if hasattr(transport, "close"):
            transport.close()
    for hop in hops:
        print(format_hop(hop, resolve=not args.no_resolve))
    return 0


if __name__ == "__main__":
    sys.exit(main())

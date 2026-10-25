#!/usr/bin/env python3
"""DNS resolver client (RFC 1035 wire format), Python standard library only.

Implements the Coding Challenges "Build Your Own DNS Resolver" steps:
  1. Build a DNS query message (header + question).
  2. Send it over UDP to a name server and read the response.
  3. Parse the response, including compressed names, and extract answers.
  4. Resolve iteratively from a root server, following NS referrals.
Bonus: follow CNAME records.

Usage:
    python3 dns_resolver.py <hostname> [--server IP] [--port N]
        [--type A|AAAA|NS|CNAME] [--iterative] [--root IP]
        [--recursive-server IP] [--timeout SECONDS]
"""

import argparse
import random
import socket
import struct
import sys

# Record types (RFC 1035 section 3.2.2) handled by name; others stay raw.
TYPE_A = 1
TYPE_NS = 2
TYPE_CNAME = 5
TYPE_AAAA = 28
CLASS_IN = 1

RECORD_TYPES = {"A": TYPE_A, "NS": TYPE_NS, "CNAME": TYPE_CNAME,
                "AAAA": TYPE_AAAA}

# Flags word bits (RFC 1035 section 4.1.1).
FLAG_QR = 0x8000  # 1 = response
FLAG_RD = 0x0100  # recursion desired

MAX_POINTER_JUMPS = 128
MAX_ITERATIVE_HOPS = 30
DEFAULT_DNS_PORT = 53
DEFAULT_RECURSIVE_SERVER = "8.8.8.8"
DEFAULT_ROOT_SERVER = "198.41.0.4"


class DNSError(Exception):
    """A DNS-level failure: timeout, bad id, error RCODE, or dead end."""


def encode_name(name):
    """Encode a hostname as length-prefixed labels terminated by zero."""
    name = name.rstrip(".")
    if name == "":
        return b"\x00"
    out = bytearray()
    for label in name.split("."):
        raw = label.encode("ascii")
        if len(raw) > 63:
            raise ValueError("label too long: %r" % label)
        out.append(len(raw))
        out += raw
    out.append(0)
    return bytes(out)


def decode_name(data, offset):
    """Decode a (possibly compressed) name starting at offset.

    Returns (name, next_offset), where next_offset is the position just
    past the name in the original stream -- i.e. just past the pointer
    when a pointer was followed, not past the pointed-to labels.
    Raises ValueError on pointer loops or out-of-bounds references.
    """
    labels = []
    next_offset = None
    jumps = 0
    pos = offset
    while True:
        if pos >= len(data):
            raise ValueError("name runs past end of message")
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0 == 0xC0:  # compression pointer
            if pos + 1 >= len(data):
                raise ValueError("truncated compression pointer")
            if next_offset is None:
                next_offset = pos + 2
            target = ((length & 0x3F) << 8) | data[pos + 1]
            if target >= len(data):
                raise ValueError("compression pointer out of bounds")
            jumps += 1
            if jumps > MAX_POINTER_JUMPS:
                raise ValueError("compression pointer loop")
            pos = target
            continue
        if length & 0xC0:
            raise ValueError("reserved label length bits set")
        pos += 1
        if pos + length > len(data):
            raise ValueError("label runs past end of message")
        labels.append(data[pos:pos + length].decode("ascii"))
        pos += length
    if next_offset is None:
        next_offset = pos
    return ".".join(labels), next_offset


class Header:
    def __init__(self, id_, flags, qdcount, ancount, nscount, arcount):
        self.id = id_
        self.flags = flags
        self.qdcount = qdcount
        self.ancount = ancount
        self.nscount = nscount
        self.arcount = arcount

    def to_bytes(self):
        return struct.pack(">HHHHHH", self.id, self.flags, self.qdcount,
                           self.ancount, self.nscount, self.arcount)

    @classmethod
    def from_bytes(cls, data, offset):
        fields = struct.unpack_from(">HHHHHH", data, offset)
        return cls(*fields), offset + 12

    @property
    def is_response(self):
        return bool(self.flags & FLAG_QR)

    @property
    def rcode(self):
        return self.flags & 0x000F


class Question:
    def __init__(self, name, qtype, qclass=CLASS_IN):
        self.name = name
        self.qtype = qtype
        self.qclass = qclass

    def to_bytes(self):
        return encode_name(self.name) + struct.pack(">HH", self.qtype,
                                                    self.qclass)

    @classmethod
    def from_bytes(cls, data, offset):
        name, offset = decode_name(data, offset)
        qtype, qclass = struct.unpack_from(">HH", data, offset)
        return cls(name, qtype, qclass), offset + 4


class ResourceRecord:
    def __init__(self, name, rtype, rclass, ttl, rdata):
        self.name = name
        self.rtype = rtype
        self.rclass = rclass
        self.ttl = ttl
        self.rdata = rdata  # decoded: str for A/AAAA/NS/CNAME, else bytes

    def to_bytes(self):
        raw = self._encode_rdata()
        return (encode_name(self.name)
                + struct.pack(">HHIH", self.rtype, self.rclass, self.ttl,
                              len(raw)) + raw)

    def _encode_rdata(self):
        if self.rtype == TYPE_A:
            return socket.inet_aton(self.rdata)
        if self.rtype == TYPE_AAAA:
            return socket.inet_pton(socket.AF_INET6, self.rdata)
        if self.rtype in (TYPE_NS, TYPE_CNAME):
            return encode_name(self.rdata)
        return bytes(self.rdata)

    @classmethod
    def from_bytes(cls, data, offset):
        name, offset = decode_name(data, offset)
        rtype, rclass, ttl, rdlength = struct.unpack_from(">HHIH", data,
                                                          offset)
        offset += 10
        rdata_start = offset
        if offset + rdlength > len(data):
            raise ValueError("record data runs past end of message")
        if rtype == TYPE_A and rdlength == 4:
            rdata = socket.inet_ntoa(data[offset:offset + 4])
        elif rtype == TYPE_AAAA and rdlength == 16:
            rdata = socket.inet_ntop(socket.AF_INET6, data[offset:offset + 16])
        elif rtype in (TYPE_NS, TYPE_CNAME):
            rdata, _ = decode_name(data, offset)
        else:
            rdata = bytes(data[offset:offset + rdlength])
        return cls(name, rtype, rclass, ttl, rdata), rdata_start + rdlength


class Message:
    def __init__(self, header, questions, answers, authorities, additionals):
        self.header = header
        self.questions = questions
        self.answers = answers
        self.authorities = authorities
        self.additionals = additionals

    def to_bytes(self):
        out = bytearray(self.header.to_bytes())
        for section in (self.questions, self.answers, self.authorities,
                        self.additionals):
            for record in section:
                out += record.to_bytes()
        return bytes(out)

    @classmethod
    def from_bytes(cls, data):
        if len(data) < 12:
            raise ValueError("message shorter than DNS header")
        try:
            header, offset = Header.from_bytes(data, 0)
            questions = []
            for _ in range(header.qdcount):
                question, offset = Question.from_bytes(data, offset)
                questions.append(question)
            sections = []
            for count in (header.ancount, header.nscount, header.arcount):
                records = []
                for _ in range(count):
                    record, offset = ResourceRecord.from_bytes(data, offset)
                    records.append(record)
                sections.append(records)
        except (struct.error, IndexError) as exc:
            raise ValueError("truncated DNS message: %s" % exc) from exc
        return cls(header, questions, *sections)


def build_query(name, qtype, recursion_desired=True, id_=None):
    """Build a query Message for one question."""
    if id_ is None:
        id_ = random.randint(0, 0xFFFF)
    flags = FLAG_RD if recursion_desired else 0
    header = Header(id_, flags, 1, 0, 0, 0)
    return Message(header, [Question(name, qtype)], [], [], [])


def send_query(server, name, qtype, port=DEFAULT_DNS_PORT, timeout=5,
               recursion_desired=True):
    """Send one query over UDP and return the validated response Message."""
    query = build_query(name, qtype, recursion_desired)
    # Retry on ConnectionRefusedError: a connected UDP socket surfaces a
    # transient ICMP port-unreachable as ECONNREFUSED, which can arrive
    # when the peer's reader is not yet scheduled (seen as a flaky
    # failure against local fake servers). Retrying the whole exchange
    # on a fresh socket is the standard DNS-over-UDP behaviour.
    last_exc = None
    for _attempt in range(3):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            # Connected UDP (connect + send/recv) rather than sendto/recvfrom:
            # equivalent for a single query/response exchange, and required
            # in sandboxes where unconnected UDP sendto is blocked.
            sock.connect((server, port))
            sock.send(query.to_bytes())
            data = sock.recv(4096)
            break
        except socket.timeout as exc:
            raise DNSError("timed out waiting for %s" % server) from exc
        except ConnectionRefusedError as exc:
            last_exc = exc
            continue
        finally:
            sock.close()
    else:
        raise DNSError("connection refused by %s" % server) from last_exc
    response = Message.from_bytes(data)
    if response.header.id != query.header.id:
        raise DNSError("response id %d does not match query id %d"
                       % (response.header.id, query.header.id))
    if not response.header.is_response:
        raise DNSError("message from %s is not a response" % server)
    if response.header.rcode != 0:
        raise DNSError("server %s returned error RCODE %d"
                       % (server, response.header.rcode))
    return response


def _answers_of_type(message, qtype):
    return [r.rdata for r in message.answers if r.rtype == qtype]


def resolve_recursive(server, name, qtype=TYPE_A, port=DEFAULT_DNS_PORT,
                      timeout=5):
    """One recursive query (RD=1), following CNAME answers (bonus step)."""
    response = send_query(server, name, qtype, port, timeout, True)
    values = _answers_of_type(response, qtype)
    if values:
        return values
    cnames = [r.rdata for r in response.answers if r.rtype == TYPE_CNAME]
    if cnames:
        return resolve_recursive(server, cnames[0], qtype, port, timeout)
    raise DNSError("no %s answer for %s from %s"
                   % (_type_name(qtype), name, server))


def resolve_iterative(name, qtype=TYPE_A, root=DEFAULT_ROOT_SERVER,
                      port=DEFAULT_DNS_PORT, timeout=5,
                      recursive_server=DEFAULT_RECURSIVE_SERVER):
    """Resolve from a root server, following NS referrals (page Step 4)."""
    server = root
    target = name
    for _ in range(MAX_ITERATIVE_HOPS):
        print("Querying %s for %s" % (server, target))
        response = send_query(server, target, qtype, port, timeout, False)
        values = _answers_of_type(response, qtype)
        if values:
            return values
        cnames = [r.rdata for r in response.answers
                  if r.rtype == TYPE_CNAME]
        if cnames:
            target = cnames[0]  # restart from the root for the new name
            server = root
            continue
        ns_records = [r for r in response.authorities if r.rtype == TYPE_NS]
        if not ns_records:
            raise DNSError("no answer and no referral for %s from %s"
                           % (target, server))
        ns_name = ns_records[0].rdata
        glue = [r.rdata for r in response.additionals
                if r.rtype == TYPE_A and r.name == ns_name]
        if glue:
            server = glue[0]
        else:
            # No glue: resolve the name server's address recursively.
            server = resolve_recursive(recursive_server, ns_name, TYPE_A,
                                       port, timeout)[0]
    raise DNSError("too many hops resolving %s" % name)


def _type_name(qtype):
    for name_, value in RECORD_TYPES.items():
        if value == qtype:
            return name_
    return str(qtype)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve a hostname to IP address(es) via DNS.")
    parser.add_argument("hostname", help="hostname to resolve")
    parser.add_argument("--server", default=DEFAULT_RECURSIVE_SERVER,
                        help="recursive server for default mode "
                             "(default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_DNS_PORT,
                        help="DNS port; applies to every hop in iterative "
                             "mode (default: %(default)s)")
    parser.add_argument("--type", dest="qtype", default="A",
                        choices=sorted(RECORD_TYPES),
                        help="record type to query (default: %(default)s)")
    parser.add_argument("--iterative", action="store_true",
                        help="resolve iteratively from a root server")
    parser.add_argument("--root", default=DEFAULT_ROOT_SERVER,
                        help="root server for iterative mode "
                             "(default: %(default)s)")
    parser.add_argument("--recursive-server",
                        default=DEFAULT_RECURSIVE_SERVER,
                        help="server used to resolve glue-less NS names in "
                             "iterative mode (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=5,
                        help="UDP timeout in seconds (default: %(default)s)")
    args = parser.parse_args(argv)
    qtype = RECORD_TYPES[args.qtype]
    try:
        if args.iterative:
            values = resolve_iterative(args.hostname, qtype, args.root,
                                       args.port, args.timeout,
                                       args.recursive_server)
        else:
            values = resolve_recursive(args.server, args.hostname, qtype,
                                       args.port, args.timeout)
    except (DNSError, ValueError, OSError) as exc:
        print("dns_resolver: %s" % exc, file=sys.stderr)
        return 1
    for value in values:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())

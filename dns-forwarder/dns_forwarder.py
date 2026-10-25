#!/usr/bin/env python3
"""dns_forwarder.py — Build Your Own DNS Forwarder (codingchallenges.fyi).

A nameserver that forwards DNS queries to a configured upstream server
(default 8.8.8.8:53, as the challenge page specifies) and caches
successful answers for their TTL, serving later identical questions
from the local cache. Python 3 standard library only, UDP only.

See docs/SPEC.md for the challenge steps, divergences and scope limits.

Usage:
    python3 dns_forwarder.py [--bind HOST] [--port PORT]
                             [--upstream HOST] [--upstream-port PORT]
                             [--timeout SECS] [--no-cache] [--verbose]

Defaults: bind 127.0.0.1, port 53, upstream 8.8.8.8:53, timeout 5s.
"""

import argparse
import socket
import struct
import sys
import time

# --- DNS constants (RFC 1035) -------------------------------------------
TYPE_A = 1
TYPE_NS = 2
TYPE_CNAME = 5
TYPE_OPT = 41
TYPE_AAAA = 28
CLASS_IN = 1

FLAG_QR = 0x8000
FLAG_RD = 0x0100
FLAG_RA = 0x0080
FLAG_RCODE_MASK = 0x000F

RCODE_NOERROR = 0
RCODE_FORMERR = 1
RCODE_SERVFAIL = 2
RCODE_NXDOMAIN = 3

HEADER_LEN = 12
MAX_CACHE_ENTRIES = 1024

_TYPE_NAMES = {1: "A", 2: "NS", 5: "CNAME", 15: "MX", 28: "AAAA",
               41: "OPT"}


# --- Message model -------------------------------------------------------

class DnsError(ValueError):
    """Raised for malformed DNS packets."""


class Question:
    def __init__(self, name, qtype, qclass):
        self.name = name
        self.qtype = qtype
        self.qclass = qclass

    def key(self):
        return (self.name.lower(), self.qtype, self.qclass)

    def __eq__(self, other):
        return (isinstance(other, Question) and self.name == other.name
                and self.qtype == other.qtype and self.qclass == other.qclass)

    def __repr__(self):
        return "Question(%r, %d, %d)" % (self.name, self.qtype, self.qclass)


class Record:
    def __init__(self, name, rtype, rclass, ttl, rdata):
        self.name = name
        self.rtype = rtype
        self.rclass = rclass
        self.ttl = ttl
        self.rdata = rdata

    def rdata_text(self):
        if self.rtype == TYPE_A and len(self.rdata) == 4:
            return ".".join(str(b) for b in self.rdata)
        if self.rtype == TYPE_AAAA and len(self.rdata) == 16:
            groups = struct.unpack("!8H", self.rdata)
            return ":".join("%x" % g for g in groups)
        return self.rdata.hex()

    def __eq__(self, other):
        return (isinstance(other, Record) and self.name == other.name
                and self.rtype == other.rtype and self.rclass == other.rclass
                and self.ttl == other.ttl and self.rdata == other.rdata)

    def __repr__(self):
        return "Record(%r, %d, %d, %d, %r)" % (
            self.name, self.rtype, self.rclass, self.ttl, self.rdata)


class Message:
    def __init__(self, tx_id, flags, questions, answers, authorities,
                 additionals):
        self.tx_id = tx_id
        self.flags = flags
        self.questions = questions
        self.answers = answers
        self.authorities = authorities
        self.additionals = additionals

    @property
    def rcode(self):
        return self.flags & FLAG_RCODE_MASK


# --- Wire encoding / decoding --------------------------------------------

def encode_name(name):
    """'dns.google.com' -> b'\\x03dns\\x06google\\x03com\\x00'."""
    if name in ("", "."):
        return b"\x00"
    out = bytearray()
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        if len(raw) > 63:
            raise DnsError("label too long: %r" % label)
        out.append(len(raw))
        out += raw
    out.append(0)
    return bytes(out)


def parse_name(data, offset):
    """Decode a (possibly compressed) name at offset.

    Returns (dotted_name, next_offset). next_offset is the position
    after the name in the original stream (i.e. just past a pointer,
    not past the pointed-to labels). Pointer loops raise DnsError.
    """
    labels = []
    jumped = False
    next_offset = offset
    seen = set()
    while True:
        if offset >= len(data):
            raise DnsError("name runs past end of packet")
        length = data[offset]
        if length == 0:
            if not jumped:
                next_offset = offset + 1
            break
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise DnsError("truncated compression pointer")
            target = ((length & 0x3F) << 8) | data[offset + 1]
            if target in seen:
                raise DnsError("compression pointer loop")
            seen.add(target)
            if not jumped:
                next_offset = offset + 2
                jumped = True
            offset = target
            continue
        if length & 0xC0:
            raise DnsError("bad label length byte 0x%02x" % length)
        end = offset + 1 + length
        if end > len(data):
            raise DnsError("label runs past end of packet")
        labels.append(data[offset + 1:end].decode("utf-8", "replace"))
        offset = end
        if not jumped:
            next_offset = offset
    return ".".join(labels), next_offset


def parse_message(data):
    """Parse a full DNS message; raises DnsError on malformed input."""
    if len(data) < HEADER_LEN:
        raise DnsError("packet shorter than 12-byte header")
    tx_id, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
    offset = 12
    questions = []
    for _ in range(qd):
        name, offset = parse_name(data, offset)
        if offset + 4 > len(data):
            raise DnsError("truncated question")
        qtype, qclass = struct.unpack("!HH", data[offset:offset + 4])
        offset += 4
        questions.append(Question(name, qtype, qclass))
    answers = _parse_records(data, offset, an)
    offset = answers[1]
    authorities = _parse_records(data, offset, ns)
    offset = authorities[1]
    additionals = _parse_records(data, offset, ar)
    return Message(tx_id, flags, questions, answers[0],
                   authorities[0], additionals[0])


def _parse_records(data, offset, count):
    records = []
    for _ in range(count):
        name, offset = parse_name(data, offset)
        if offset + 10 > len(data):
            raise DnsError("truncated resource record")
        rtype, rclass, ttl, rdlen = struct.unpack(
            "!HHIH", data[offset:offset + 10])
        offset += 10
        if offset + rdlen > len(data):
            raise DnsError("truncated rdata")
        rdata = data[offset:offset + rdlen]
        offset += rdlen
        records.append(Record(name, rtype, rclass, ttl, rdata))
    return records, offset


def encode_question(question):
    return encode_name(question.name) + struct.pack(
        "!HH", question.qtype, question.qclass)


def encode_record(record):
    return (encode_name(record.name)
            + struct.pack("!HHIH", record.rtype, record.rclass,
                          record.ttl, len(record.rdata))
            + record.rdata)


def build_query(qname, qtype=TYPE_A, qclass=CLASS_IN, tx_id=0):
    """Build a standard RD query with one question."""
    header = struct.pack("!HHHHHH", tx_id, FLAG_RD, 1, 0, 0, 0)
    return header + encode_question(Question(qname, qtype, qclass))


def build_response(query, answers, rcode=RCODE_NOERROR,
                   authorities=(), additionals=()):
    """Build a response to `query` (a Message) with given sections."""
    flags = FLAG_QR | FLAG_RA | (query.flags & FLAG_RD) | rcode
    header = struct.pack("!HHHHHH", query.tx_id, flags,
                         len(query.questions), len(answers),
                         len(authorities), len(additionals))
    out = bytearray(header)
    for q in query.questions:
        out += encode_question(q)
    for rec in list(answers) + list(authorities) + list(additionals):
        out += encode_record(rec)
    return bytes(out)


def format_message(msg):
    """Human-readable form, in the shape of the challenge page's Step 2
    example."""
    lines = [
        "Header - id:%d flags:%d questions:%d answers:%d "
        "authorities:%d additionals:%d" % (
            msg.tx_id, msg.flags, len(msg.questions), len(msg.answers),
            len(msg.authorities), len(msg.additionals)),
    ]
    for q in msg.questions:
        lines.append("Questions - name:%s type:%d class:%d" % (
            q.name, q.qtype, q.qclass))
    for label, recs in (("Answers", msg.answers),
                        ("Authorities", msg.authorities),
                        ("Additionals", msg.additionals)):
        if recs:
            for r in recs:
                lines.append("%s - name:%s type:%d class:%d ttl:%d %s"
                             % (label, r.name, r.rtype, r.rclass, r.ttl,
                                r.rdata_text()))
        else:
            lines.append("%s: Empty" % label)
    return "\n".join(lines)


# --- Cache ----------------------------------------------------------------

class DnsCache:
    """TTL-bound cache: key -> (stored_at, [Record, ...]).

    time_fn defaults to time.monotonic and is injectable for tests.
    An entry is a hit only while EVERY answer record is still within
    its TTL; otherwise the whole entry is a miss.
    """

    def __init__(self, time_fn=None, max_entries=MAX_CACHE_ENTRIES):
        self._time = time_fn or time.monotonic
        self._max = max_entries
        self._entries = {}

    def get(self, key):
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, records = entry
        elapsed = self._time() - stored_at
        remaining = []
        for rec in records:
            left = rec.ttl - elapsed
            if left <= 0:
                return None
            remaining.append(Record(rec.name, rec.rtype, rec.rclass,
                                    int(left), rec.rdata))
        return remaining

    def put(self, key, records):
        if key not in self._entries and len(self._entries) >= self._max:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[key] = (self._time(), list(records))

    def __len__(self):
        return len(self._entries)


# --- Forwarder --------------------------------------------------------------

class Forwarder:
    """Serial UDP DNS forwarder (see docs/DESIGN.md for the flow)."""

    def __init__(self, bind="127.0.0.1", port=53,
                 upstream="8.8.8.8", upstream_port=53, timeout=5.0,
                 use_cache=True, verbose=False):
        self.bind = bind
        self.port = port
        self.upstream = upstream
        self.upstream_port = upstream_port
        self.timeout = timeout
        self.use_cache = use_cache
        self.verbose = verbose
        self.cache = DnsCache()
        self._next_id = (int(time.time()) & 0xFFFF) or 1
        self._listen_sock = None
        self._upstream_sock = None
        self._running = False

    def _log(self, text):
        if self.verbose:
            print(text, flush=True)

    def _fresh_id(self):
        tx_id = self._next_id
        self._next_id = (self._next_id + 1) & 0xFFFF
        if self._next_id == 0:
            self._next_id = 1
        return tx_id

    def serve_forever(self):
        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # SO_REUSEPORT is also set on the fresh socket in _send's
        # fallback, so its bind can reuse the port promptly.
        try:
            self._listen_sock.setsockopt(socket.SOL_SOCKET,
                                         socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        self._listen_sock.bind((self.bind, self.port))
        self._upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connected UDP socket: send()/recv() to the one upstream.
        # (Also the form that works in sandboxes that block sendto().)
        self._upstream_sock.connect((self.upstream, self.upstream_port))
        self._upstream_sock.settimeout(self.timeout)
        self._running = True
        self._log("Listening on %s:%d, forwarding to %s:%d"
                  % (self.bind, self.port, self.upstream,
                     self.upstream_port))
        try:
            while self._running:
                try:
                    data, client_addr = self._listen_sock.recvfrom(512)
                except OSError:
                    break
                self.handle_query(data, client_addr)
        finally:
            self.stop()

    def stop(self):
        self._running = False
        for sock in (self._listen_sock, self._upstream_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._listen_sock = None
        self._upstream_sock = None

    def handle_query(self, data, client_addr):
        """Handle one client datagram; returns the bytes sent, if any.

        Separated from serve_forever so tests can drive it directly,
        but the integration tests use real sockets end to end.
        """
        self._log("MSG received")
        if len(data) < HEADER_LEN:
            return None  # too short even to answer; ignore silently
        try:
            query = parse_message(data)
        except DnsError:
            # Header parsed but body did not: answer FORMERR.
            tx_id = struct.unpack("!H", data[:2])[0]
            stub = Message(tx_id, 0, [], [], [], [])
            reply = build_response(stub, [], rcode=RCODE_FORMERR)
            self._send(client_addr, reply)
            return reply
        self._log(format_message(query))
        if not query.questions:
            reply = build_response(query, [], rcode=RCODE_FORMERR)
            self._send(client_addr, reply)
            return reply

        question = query.questions[0]
        single = len(query.questions) == 1
        if self.use_cache and single:
            hit = self.cache.get(question.key())
            if hit is not None:
                self._log("Cache hit for %s" % question.name)
                reply = build_response(query, hit)
                self._send(client_addr, reply)
                return reply
            self._log("Cache miss for %s" % question.name)

        # Forward: same question bytes, fresh upstream transaction id.
        upstream_id = self._fresh_id()
        forwarded = (struct.pack("!H", upstream_id) + data[2:])
        self._log("Forwarded Question")
        try:
            self._upstream_sock.send(forwarded)
            resp_data = self._upstream_sock.recv(4096)
        except (socket.timeout, OSError):
            reply = build_response(query, [], rcode=RCODE_SERVFAIL)
            self._send(client_addr, reply)
            return reply
        try:
            response = parse_message(resp_data)
        except DnsError:
            reply = build_response(query, [], rcode=RCODE_SERVFAIL)
            self._send(client_addr, reply)
            return reply
        if (self.use_cache and single
                and response.rcode == RCODE_NOERROR and response.answers):
            self.cache.put(question.key(), response.answers)
        # Rewrite the id to the client's id, forward everything else
        # (answers, authorities, additionals incl. EDNS OPT) verbatim.
        reply = struct.pack("!H", query.tx_id) + resp_data[2:]
        self._send(client_addr, reply)
        return reply

    def _send(self, addr, data):
        # Normal path: sendto() from the listening socket, so the reply
        # originates from the port the client queried.
        sock = self._listen_sock
        if sock is not None:
            try:
                sock.sendto(data, addr)
                return
            except OSError:
                pass  # e.g. sandbox blocks unconnected sendto(); see below
        # Fallback for environments that block unconnected sendto():
        # connect the listening socket to the client, send() (which
        # keeps the listen port as source, so a connected client
        # accepts the reply), then swap in a fresh unconnected socket
        # bound to the same port for the next query. The old socket is
        # closed BEFORE the fresh one binds, deliberately: binding
        # first (with SO_REUSEPORT) was tried and is worse — a query
        # arriving while both sockets are bound can be load-balanced
        # into the old socket's queue and silently lost when it
        # closes. With close-then-bind, a query arriving in the tiny
        # unbound window instead gets an ICMP port-unreachable, which
        # a connected client surfaces as ConnectionRefusedError and
        # can retry from (the test harness does). The server is
        # serial, so no query is being received while this happens.
        if sock is None:
            return
        try:
            port = sock.getsockname()[1]
            sock.connect(addr)
            sock.send(data)
        except OSError:
            return
        try:
            sock.close()
        except OSError:
            pass
        fresh = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        fresh.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            fresh.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            fresh.bind((self.bind, port))
        except OSError:
            return
        self._listen_sock = fresh


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DNS forwarder: forward queries to an upstream "
                    "nameserver, caching successful answers for their TTL.")
    parser.add_argument("--bind", default="127.0.0.1",
                        help="address to listen on (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=53,
                        help="port to listen on (default 53)")
    parser.add_argument("--upstream", default="8.8.8.8",
                        help="upstream nameserver (default 8.8.8.8)")
    parser.add_argument("--upstream-port", type=int, default=53,
                        help="upstream port (default 53)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="upstream wait in seconds (default 5.0)")
    parser.add_argument("--no-cache", action="store_true",
                        help="disable the cache")
    parser.add_argument("--verbose", action="store_true",
                        help="log received/forwarded/cache messages")
    args = parser.parse_args(argv)

    forwarder = Forwarder(bind=args.bind, port=args.port,
                          upstream=args.upstream,
                          upstream_port=args.upstream_port,
                          timeout=args.timeout,
                          use_cache=not args.no_cache,
                          verbose=args.verbose)
    try:
        forwarder.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        forwarder.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

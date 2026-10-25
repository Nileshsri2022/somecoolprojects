#!/usr/bin/env python3
"""Minimal download-only BitTorrent client (stdlib only).

Implements Coding Challenges #100 / challenge-bittorrent, Steps 1-8:
bencode, .torrent metainfo, HTTP tracker protocol, peer wire
protocol (handshake, bitfield, request/piece), SHA-1 piece
verification, and file assembly. See docs/ for SPEC/DESIGN.

Usage:
    python3 torrent.py info <file.torrent>
    python3 torrent.py <file.torrent>          # same as info
    python3 torrent.py download <file.torrent> [output]
"""

import hashlib
import os
import socket
import struct
import sys
import urllib.parse
import urllib.request

BLOCK_SIZE = 16384
PSTR = b"BitTorrent protocol"
DEFAULT_PORT = 6881
DEFAULT_TIMEOUT = 10.0

# Message ids (peer wire protocol).
CHOKE, UNCHOKE, INTERESTED, NOT_INTERESTED = 0, 1, 2, 3
HAVE, BITFIELD, REQUEST, PIECE, CANCEL = 4, 5, 6, 7, 8


class BencodeError(ValueError):
    pass


class TorrentError(ValueError):
    pass


class TrackerError(RuntimeError):
    pass


class PeerError(RuntimeError):
    pass


class DownloadError(RuntimeError):
    pass


# ---------------------------------------------------------------- bencode

def bencode(value):
    """Encode bytes/str/int/list/dict. Dict keys are sorted bytes."""
    if isinstance(value, int) and not isinstance(value, bool):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, (list, tuple)):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        items = []
        for key in value:
            if isinstance(key, str):
                key = key.encode()
            if not isinstance(key, bytes):
                raise BencodeError("dict key must be bytes or str")
            items.append((key, value[key]))
        items.sort(key=lambda kv: kv[0])
        out = bytearray(b"d")
        for key, val in items:
            out += bencode(key) + bencode(val)
        out += b"e"
        return bytes(out)
    raise BencodeError(f"cannot bencode {type(value).__name__}")


def _decode_at(data, pos):
    """Decode one value starting at pos; return (value, next_pos)."""
    if pos >= len(data):
        raise BencodeError("truncated input")
    token = data[pos:pos + 1]
    if token == b"i":
        try:
            end = data.index(b"e", pos)
        except ValueError:
            raise BencodeError("unterminated integer")
        num = data[pos + 1:end]
        if not num or (len(num) > 1 and num[:1] == b"0") \
                or num == b"-0" or (num[:1] == b"-" and num[1:2] == b"0"):
            raise BencodeError(f"invalid integer {num!r}")
        try:
            return int(num), end + 1
        except ValueError:
            raise BencodeError(f"invalid integer {num!r}")
    if token == b"l":
        items, pos = [], pos + 1
        while data[pos:pos + 1] != b"e":
            item, pos = _decode_at(data, pos)
            items.append(item)
        return items, pos + 1
    if token == b"d":
        result, pos = {}, pos + 1
        while data[pos:pos + 1] != b"e":
            key, pos = _decode_at(data, pos)
            if not isinstance(key, bytes):
                raise BencodeError("dict key must be a string")
            value, pos = _decode_at(data, pos)
            result[key] = value
        return result, pos + 1
    if token.isdigit():
        try:
            colon = data.index(b":", pos)
        except ValueError:
            raise BencodeError("unterminated string length")
        length = int(data[pos:colon])
        start = colon + 1
        end = start + length
        if end > len(data):
            raise BencodeError("truncated string")
        return data[start:end], end
    raise BencodeError(f"unexpected token {token!r} at {pos}")


def bdecode(data):
    """Decode bencoded bytes; reject trailing data."""
    if not isinstance(data, (bytes, bytearray)):
        raise BencodeError("input must be bytes")
    value, pos = _decode_at(bytes(data), 0)
    if pos != len(data):
        raise BencodeError("trailing data after value")
    return value


# ---------------------------------------------------------------- metainfo

class Torrent:
    def __init__(self, announce, name, piece_length, piece_hashes,
                 total_length, files, info_hash):
        self.announce = announce
        self.name = name
        self.piece_length = piece_length
        self.piece_hashes = piece_hashes
        self.total_length = total_length
        self.files = files  # None (single file) or [(length, [path...])]
        self.info_hash = info_hash

    @property
    def num_pieces(self):
        return len(self.piece_hashes)

    def piece_size(self, index):
        """Length of piece index; the last piece may be short."""
        start = index * self.piece_length
        return min(self.piece_length, self.total_length - start)


def parse_torrent_bytes(data):
    """Parse a .torrent file. info_hash is SHA-1 of the raw info bytes."""
    if not isinstance(data, (bytes, bytearray)):
        raise TorrentError("torrent data must be bytes")
    data = bytes(data)
    top, pos = _decode_at(data, 0)
    if pos != len(data):
        raise TorrentError("trailing data in torrent file")
    if not isinstance(top, dict):
        raise TorrentError("torrent top level must be a dictionary")
    if b"announce" not in top or b"info" not in top:
        raise TorrentError("torrent missing announce or info")
    # Re-walk the top dict to slice the raw info bytes verbatim.
    info_raw = None
    p = 1  # skip leading 'd'
    while data[p:p + 1] != b"e":
        key, p = _decode_at(data, p)
        start = p
        _, p = _decode_at(data, p)
        if key == b"info":
            info_raw = data[start:p]
    if info_raw is None:
        raise TorrentError("torrent missing info")
    info = top[b"info"]
    if not isinstance(info, dict):
        raise TorrentError("info must be a dictionary")
    try:
        announce = top[b"announce"].decode()
        name = info[b"name"].decode(errors="replace")
        piece_length = info[b"piece length"]
        pieces = info[b"pieces"]
    except (KeyError, UnicodeDecodeError) as exc:
        raise TorrentError(f"torrent missing required field: {exc}")
    if not isinstance(piece_length, int) or piece_length <= 0:
        raise TorrentError("invalid piece length")
    if not isinstance(pieces, bytes) or len(pieces) % 20 != 0:
        raise TorrentError("pieces must be a multiple of 20 bytes")
    piece_hashes = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]
    files = None
    if b"length" in info:
        total_length = info[b"length"]
    elif b"files" in info:
        files, total_length = [], 0
        for entry in info[b"files"]:
            length = entry[b"length"]
            path = [part.decode(errors="replace")
                    for part in entry[b"path"]]
            files.append((length, path))
            total_length += length
    else:
        raise TorrentError("info has neither length nor files")
    if not isinstance(total_length, int) or total_length < 0:
        raise TorrentError("invalid total length")
    if piece_hashes and total_length > 0:
        expected = (total_length + piece_length - 1) // piece_length
        if len(piece_hashes) != expected:
            raise TorrentError(
                f"piece count {len(piece_hashes)} != expected {expected}")
    return Torrent(announce, name, piece_length, piece_hashes,
                   total_length, files,
                   hashlib.sha1(info_raw).digest())


def parse_torrent_file(path):
    with open(path, "rb") as fh:
        return parse_torrent_bytes(fh.read())


def load_torrent(path_or_url):
    """Local path, or a URL (fetched) — Step 2 allows both."""
    if path_or_url.startswith(("http://", "https://")):
        with urllib.request.urlopen(path_or_url,
                                    timeout=DEFAULT_TIMEOUT) as resp:
            return parse_torrent_bytes(resp.read())
    return parse_torrent_file(path_or_url)


def make_peer_id(prefix=b"-SC0100-"):
    """20-byte peer id: prefix + random bytes."""
    return prefix + os.urandom(20 - len(prefix))


# ---------------------------------------------------------------- tracker

def build_tracker_url(torrent, peer_id, port=DEFAULT_PORT,
                      uploaded=0, downloaded=0):
    params = {
        "info_hash": torrent.info_hash,
        "peer_id": peer_id,
        "port": port,
        "uploaded": uploaded,
        "downloaded": downloaded,
        "left": torrent.total_length - downloaded,
        "compact": 1,
    }
    query = urllib.parse.urlencode(
        {k: v for k, v in params.items()}, quote_via=urllib.parse.quote)
    # urlencode percent-encodes bytes values correctly via quote_via.
    sep = "&" if "?" in torrent.announce else "?"
    return torrent.announce + sep + query


def parse_tracker_response(data):
    """Return (peers, interval). peers is a list of (ip, port)."""
    resp = bdecode(data)
    if not isinstance(resp, dict):
        raise TrackerError("tracker response must be a dictionary")
    if b"failure reason" in resp:
        raise TrackerError(resp[b"failure reason"].decode(errors="replace"))
    raw = resp.get(b"peers", b"")
    peers = []
    if isinstance(raw, bytes):
        if len(raw) % 6 != 0:
            raise TrackerError("compact peer list not a multiple of 6")
        for i in range(0, len(raw), 6):
            ip = socket.inet_ntoa(raw[i:i + 4])
            port = struct.unpack("!H", raw[i + 4:i + 6])[0]
            peers.append((ip, port))
    elif isinstance(raw, list):
        for entry in raw:
            peers.append((entry[b"ip"].decode(), entry[b"port"]))
    else:
        raise TrackerError("unrecognised peers format")
    interval = resp.get(b"interval", 0)
    return peers, interval


def get_peers(torrent, peer_id, port=DEFAULT_PORT,
              downloaded=0, timeout=DEFAULT_TIMEOUT):
    url = build_tracker_url(torrent, peer_id, port,
                            downloaded=downloaded)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except Exception as exc:
        raise TrackerError(f"tracker request failed: {exc}")
    peers, _interval = parse_tracker_response(body)
    return peers


# ---------------------------------------------------------------- peer protocol

def build_handshake(info_hash, peer_id):
    return bytes([len(PSTR)]) + PSTR + b"\x00" * 8 + info_hash + peer_id


def parse_handshake(data):
    """Validate and split a handshake; returns (info_hash, peer_id)."""
    if len(data) < 1 or data[0] != len(PSTR):
        raise PeerError("bad handshake protocol length")
    if len(data) < 1 + len(PSTR) + 8 + 40:
        raise PeerError("truncated handshake")
    if data[1:1 + len(PSTR)] != PSTR:
        raise PeerError("bad handshake protocol string")
    off = 1 + len(PSTR) + 8
    return data[off:off + 20], data[off + 20:off + 40]


def encode_message(msg_id, payload=b""):
    """Keep-alive: encode_message(None). Otherwise length-prefixed."""
    if msg_id is None:
        return struct.pack("!I", 0)
    body = bytes([msg_id]) + payload
    return struct.pack("!I", len(body)) + body


class Message:
    def __init__(self, msg_id, payload=b""):
        self.msg_id = msg_id  # None == keep-alive
        self.payload = payload

    def __repr__(self):
        return f"Message({self.msg_id}, {len(self.payload)} bytes)"


def bitfield_has(bitfield, index):
    byte, bit = divmod(index, 8)
    if byte >= len(bitfield):
        return False
    return bool(bitfield[byte] & (0x80 >> bit))


def bitfield_set(bitfield, index):
    byte, bit = divmod(index, 8)
    while len(bitfield) <= byte:
        bitfield.append(0)
    bitfield[byte] |= 0x80 >> bit
    return bitfield


def bitfield_from_pieces(pieces, num_pieces):
    size = (num_pieces + 7) // 8
    field = bytearray(size)
    for index in pieces:
        bitfield_set(field, index)
    return bytes(field)


def build_request(index, begin, length):
    return encode_message(REQUEST, struct.pack("!III", index, begin, length))


def parse_piece(payload):
    """Piece payload -> (index, begin, block)."""
    if len(payload) < 8:
        raise PeerError("short piece message")
    index, begin = struct.unpack("!II", payload[:8])
    return index, begin, payload[8:]


class PeerSession:
    """One peer connection: handshake, interested/unchoke, requests."""

    def __init__(self, ip, port, torrent, peer_id,
                 timeout=DEFAULT_TIMEOUT):
        self.ip, self.port = ip, port
        self.torrent = torrent
        self.peer_id = peer_id
        self.timeout = timeout
        self.sock = None
        self.bitfield = bytearray()
        self.remote_peer_id = None

    def __enter__(self):
        self.sock = socket.create_connection(
            (self.ip, self.port), timeout=self.timeout)
        self.sock.sendall(build_handshake(self.torrent.info_hash,
                                          self.peer_id))
        raw = self._recv_exact(1 + len(PSTR) + 8 + 40)
        info_hash, self.remote_peer_id = parse_handshake(raw)
        if info_hash != self.torrent.info_hash:
            raise PeerError("peer handshake info_hash mismatch")
        self.sock.sendall(encode_message(INTERESTED))
        # Wait for unchoke, collecting bitfield / have updates.
        while True:
            msg = self.recv_message()
            if msg.msg_id is None:
                continue
            if msg.msg_id == BITFIELD:
                self.bitfield = bytearray(msg.payload)
            elif msg.msg_id == HAVE:
                index, = struct.unpack("!I", msg.payload)
                bitfield_set(self.bitfield, index)
            elif msg.msg_id == UNCHOKE:
                return self
            elif msg.msg_id == CHOKE:
                raise PeerError("peer choked us")
        return self

    def __exit__(self, *exc):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        return False

    def _recv_exact(self, count):
        buf = bytearray()
        while len(buf) < count:
            chunk = self.sock.recv(count - len(buf))
            if not chunk:
                raise PeerError("connection closed by peer")
            buf += chunk
        return bytes(buf)

    def recv_message(self):
        raw_len = self._recv_exact(4)
        (length,) = struct.unpack("!I", raw_len)
        if length == 0:
            return Message(None)
        body = self._recv_exact(length)
        msg = Message(body[0], body[1:])
        if msg.msg_id == BITFIELD:
            self.bitfield = bytearray(msg.payload)
        elif msg.msg_id == HAVE:
            index, = struct.unpack("!I", msg.payload)
            bitfield_set(self.bitfield, index)
        return msg

    def request_piece(self, index, length):
        """Request one piece in 16 KiB blocks; return assembled bytes."""
        blocks = {}
        offset = 0
        while offset < length:
            want = min(BLOCK_SIZE, length - offset)
            self.sock.sendall(build_request(index, offset, want))
            while True:
                msg = self.recv_message()
                if msg.msg_id == PIECE:
                    p_index, begin, block = parse_piece(msg.payload)
                    if p_index == index and begin == offset:
                        blocks[offset] = block
                        break
                    # Wrong block: keep waiting for the one asked for.
                # keep-alive / have / choke etc. are tolerated here;
                # a choke mid-piece surfaces as a timeout/close.
            offset += want
        return b"".join(blocks[o] for o in sorted(blocks))


def verify_piece(data, expected_hash):
    return hashlib.sha1(data).digest() == expected_hash


# ---------------------------------------------------------------- download

def download(torrent, peers, output_path, peer_id=None,
             port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT,
             on_piece=None):
    """Download every piece, verifying SHA-1, writing in place.

    Peers are tried in order per piece; a failed/corrupt piece is
    retried against the next peer and never written unverified.
    Returns the output path.
    """
    if peer_id is None:
        peer_id = make_peer_id()
    if not peers:
        raise DownloadError("no peers available")
    if torrent.total_length == 0:
        open(output_path, "wb").close()
        return output_path
    with open(output_path, "wb") as fh:
        fh.truncate(torrent.total_length)
        for index in range(torrent.num_pieces):
            size = torrent.piece_size(index)
            expected = torrent.piece_hashes[index]
            data = None
            last_error = None
            for ip, peer_port in peers:
                try:
                    with PeerSession(ip, peer_port, torrent, peer_id,
                                     timeout=timeout) as session:
                        if not bitfield_has(session.bitfield, index):
                            continue
                        candidate = session.request_piece(index, size)
                except (PeerError, OSError, socket.timeout) as exc:
                    last_error = exc
                    continue
                if verify_piece(candidate, expected):
                    data = candidate
                    break
                last_error = PeerError(f"piece {index} hash mismatch")
            if data is None:
                raise DownloadError(
                    f"piece {index} could not be downloaded: {last_error}")
            fh.seek(index * torrent.piece_length)
            fh.write(data)
            if on_piece is not None:
                on_piece(index)
    return output_path


# ---------------------------------------------------------------- CLI

def cmd_info(torrent):
    print(f"Announce URL: {torrent.announce}")
    print(f"Name: {torrent.name}")
    print(f"Length: {torrent.total_length} bytes")
    print(f"Piece length: {torrent.piece_length} bytes")
    print(f"Pieces: {torrent.num_pieces}")
    print(f"Info hash: {torrent.info_hash.hex()}")
    if torrent.files:
        print("Files:")
        for length, path in torrent.files:
            print(f"  {length} {'/'.join(path)}")
    return 0


def cmd_download(torrent_path, output_path):
    torrent = load_torrent(torrent_path)
    cmd_info(torrent)
    peer_id = make_peer_id()
    print("Contacting tracker...")
    peers = get_peers(torrent, peer_id)
    print(f"Got {len(peers)} peer(s)")
    for ip, port in peers:
        print(f"Peer: {ip}:{port}")
    if output_path is None:
        output_path = torrent.name
    print(f"Downloading to {output_path}...")

    def _on_piece(index):
        print(f"Verified piece {index}")

    download(torrent, peers, output_path, peer_id=peer_id,
             on_piece=_on_piece)
    print(f"Done: {output_path} ({torrent.total_length} bytes)")
    return 0


def main(argv):
    if len(argv) < 2:
        print("usage: torrent.py info <file.torrent> | "
              "torrent.py download <file.torrent> [output]",
              file=sys.stderr)
        return 2
    if argv[1] == "download":
        if len(argv) < 3:
            print("usage: torrent.py download <file.torrent> [output]",
                  file=sys.stderr)
            return 2
        output = argv[2 + 1] if len(argv) > 3 else None
        return cmd_download(argv[2], output)
    if argv[1] == "info":
        if len(argv) < 3:
            print("usage: torrent.py info <file.torrent>", file=sys.stderr)
            return 2
        return cmd_info(load_torrent(argv[2]))
    # Bare torrent path == info (offline, no network contact).
    return cmd_info(load_torrent(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

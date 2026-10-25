"""Tests for torrent.py — all network tests use local fake servers
on 127.0.0.1 ephemeral ports and synthetic torrents built in-run.
Never contacts a real tracker or peer."""
import hashlib
import http.server
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import torrent as T

PEER_ID = b"-SC0100-123456789012"
assert len(PEER_ID) == 20


def make_torrent_bytes(data, piece_length=16, announce="http://127.0.0.1:1/announce",
                       name="test.bin"):
    hashes = b"".join(
        hashlib.sha1(data[i:i + piece_length]).digest()
        for i in range(0, len(data), piece_length)) or hashlib.sha1(b"").digest()
    # For empty data the page's logic still needs zero pieces; keep simple:
    if len(data) == 0:
        hashes = b""
    info = {b"name": name.encode(), b"piece length": piece_length,
            b"pieces": hashes, b"length": len(data)}
    return T.bencode({b"announce": announce.encode(), b"info": info}), info


def parse_local(data, **kw):
    raw, _ = make_torrent_bytes(data, **kw)
    return T.parse_torrent_bytes(raw)


# ------------------------------------------------------------ fake servers

class FakeTracker(http.server.BaseHTTPRequestHandler):
    peers = []  # list of (ip, port)
    mode = "compact"  # or "dict" or "failure"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.mode == "failure":
            body = T.bencode({b"failure reason": b"no such torrent"})
        elif self.mode == "dict":
            body = T.bencode({b"interval": 60, b"peers": [
                {b"ip": ip.encode(), b"port": port}
                for ip, port in self.peers]})
        else:
            raw = b"".join(socket.inet_aton(ip) + struct.pack("!H", port)
                           for ip, port in self.peers)
            body = T.bencode({b"interval": 60, b"peers": raw})
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakePeer(threading.Thread):
    """Serves `data` for one torrent; corrupt_piece corrupts one piece."""
    daemon = True

    def __init__(self, torrent_obj, data, corrupt_piece=None):
        super().__init__()
        self.torrent = torrent_obj
        self.data = data
        self.corrupt_piece = corrupt_piece
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.stop = threading.Event()

    def run(self):
        self.sock.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn,),
                             daemon=True).start()

    def handle(self, conn):
        try:
            conn.settimeout(10)
            raw = b""
            while len(raw) < 68:
                chunk = conn.recv(68 - len(raw))
                if not chunk:
                    return
                raw += chunk
            info_hash, _pid = T.parse_handshake(raw)
            if info_hash != self.torrent.info_hash:
                return
            conn.sendall(T.build_handshake(self.torrent.info_hash, PEER_ID))
            conn.sendall(T.encode_message(
                T.BITFIELD,
                T.bitfield_from_pieces(range(self.torrent.num_pieces),
                                       self.torrent.num_pieces)))
            conn.sendall(T.encode_message(T.UNCHOKE))
            buf = b""
            while True:
                while len(buf) < 4:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                (length,) = struct.unpack("!I", buf[:4])
                while len(buf) < 4 + length:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                body, buf = buf[4:4 + length], buf[4 + length:]
                if length == 0 or body[0] != T.REQUEST:
                    continue
                index, begin, size = struct.unpack("!III", body[1:13])
                start = index * self.torrent.piece_length + begin
                block = self.data[start:start + size]
                if self.corrupt_piece == index and begin == 0 and block:
                    block = bytes([block[0] ^ 0xFF]) + block[1:]
                conn.sendall(T.encode_message(
                    T.PIECE, struct.pack("!II", index, begin) + block))
        except (OSError, T.PeerError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self.stop.set()
        self.sock.close()


def start_tracker(peers, mode="compact"):
    FakeTracker.peers = peers
    FakeTracker.mode = mode
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeTracker)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ------------------------------------------------------------------- tests

class TestBencode(unittest.TestCase):
    def test_round_trips(self):
        for value in [b"coding", 0, -42, 100, [], [b"a", 3],
                      {b"k": [1, b"v"]}, {b"a": {b"b": b"c"}}]:
            self.assertEqual(T.bdecode(T.bencode(value)), value)
        # str encodes as UTF-8 and decodes back as bytes (SPEC.md):
        self.assertEqual(T.bdecode(T.bencode("hi")), b"hi")

    def test_page_examples(self):
        self.assertEqual(T.bencode(b"coding"), b"6:coding")
        self.assertEqual(T.bencode(100), b"i100e")
        self.assertEqual(T.bencode([b"Coding", b"Challenges"]),
                         b"l6:Coding10:Challengese")
        self.assertEqual(
            T.bencode({b"Coding Challenges":
                       {b"website:": b"codingchallenges.fyi",
                        b"Rating": b"Awesome"}}),
            b"d17:Coding Challengesd6:Rating7:Awesome8:website:"
            b"20:codingchallenges.fyiee")

    def test_encoder_sorts_keys(self):
        self.assertEqual(T.bencode({b"b": 1, b"a": 2}), b"d1:ai2e1:bi1ee")

    def test_decoder_rejects(self):
        for bad in [b"", b"i03e", b"i-0e", b"i12", b"3:ab", b"l1:a",
                    b"d1:a", b"i1ee", b"i1eX", b"di1e1:ae"]:
            with self.subTest(bad=bad):
                self.assertRaises(T.BencodeError, T.bdecode, bad)


class TestMetainfo(unittest.TestCase):
    def test_single_file(self):
        data = b"hello world, this is a torrent test file!!"
        tor = parse_local(data, piece_length=16)
        self.assertEqual(tor.name, "test.bin")
        self.assertEqual(tor.total_length, len(data))
        self.assertEqual(tor.piece_length, 16)
        self.assertEqual(tor.num_pieces, 3)
        self.assertEqual(tor.piece_size(0), 16)
        self.assertEqual(tor.piece_size(2), len(data) - 32)
        self.assertTrue(T.verify_piece(data[:16], tor.piece_hashes[0]))

    def test_info_hash_uses_raw_info_bytes(self):
        # Info dict keys deliberately OUT of order in the raw file.
        data = b"0123456789abcdef"
        # Keys deliberately NOT in sorted order (name before length,
        # pieces before piece length) — sorted order would be
        # length < name < piece length < pieces.
        info_raw = (b"d4:name8:test.bin6:lengthi16e"
                    b"6:pieces40:" +
                    hashlib.sha1(data[:8]).digest() +
                    hashlib.sha1(data[8:]).digest() +
                    b"12:piece lengthi8ee")
        raw = b"d8:announce20:http://127.0.0.1:1/x4:info" + info_raw + b"e"
        tor = T.parse_torrent_bytes(raw)
        self.assertEqual(tor.info_hash, hashlib.sha1(info_raw).digest())
        # Re-encoding the (sorted) dict would differ from raw order,
        # proving the raw slice matters:
        self.assertNotEqual(T.bencode(T.bdecode(info_raw)), info_raw)

    def test_malformed(self):
        for raw in [T.bencode([1, 2]),
                    T.bencode({b"announce": b"http://x/"}),
                    T.bencode({b"announce": b"http://x/",
                               b"info": {b"name": b"n",
                                        b"piece length": 4,
                                        b"pieces": b"short",
                                        b"length": 4}})]:
            with self.subTest(raw=raw):
                self.assertRaises(T.TorrentError, T.parse_torrent_bytes, raw)

    def test_multi_file_parses(self):
        info = {b"name": b"dir", b"piece length": 4,
                b"pieces": hashlib.sha1(b"abcd").digest(),
                b"files": [{b"length": 2, b"path": [b"a.txt"]},
                           {b"length": 2, b"path": [b"b.txt"]}]}
        tor = T.parse_torrent_bytes(T.bencode(
            {b"announce": b"http://x/", b"info": info}))
        self.assertEqual(tor.total_length, 4)
        self.assertEqual(len(tor.files), 2)


class TestTracker(unittest.TestCase):
    def test_url_params(self):
        tor = parse_local(b"0123456789abcdef")
        url = T.build_tracker_url(tor, PEER_ID, port=6881)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["port"], ["6881"])
        self.assertEqual(q["uploaded"], ["0"])
        self.assertEqual(q["downloaded"], ["0"])
        self.assertEqual(q["left"], ["16"])
        self.assertEqual(q["compact"], ["1"])
        # info_hash / peer_id survive URL round-trip as raw bytes
        # (split manually: parse_qsl decodes to str and mangles
        # non-UTF-8 bytes, so unquote the raw query components):
        raw_query = urllib.parse.urlparse(url).query
        vals = dict(part.split("=", 1) for part in raw_query.split("&"))
        self.assertEqual(urllib.parse.unquote_to_bytes(vals["info_hash"]),
                         tor.info_hash)
        self.assertEqual(urllib.parse.unquote_to_bytes(vals["peer_id"]),
                         PEER_ID)

    def test_compact_and_dict_peers(self):
        for mode in ("compact", "dict"):
            srv = start_tracker([("127.0.0.1", 5001), ("10.0.0.2", 6889)],
                                mode=mode)
            try:
                tor = parse_local(b"0123456789abcdef",
                                  announce=f"http://127.0.0.1:{srv.server_port}/announce")
                peers = T.get_peers(tor, PEER_ID)
                self.assertEqual(peers, [("127.0.0.1", 5001),
                                         ("10.0.0.2", 6889)])
            finally:
                srv.shutdown()
                srv.server_close()

    def test_failure_reason(self):
        srv = start_tracker([], mode="failure")
        try:
            tor = parse_local(b"0123456789abcdef",
                              announce=f"http://127.0.0.1:{srv.server_port}/announce")
            self.assertRaises(T.TrackerError, T.get_peers, tor, PEER_ID)
        finally:
            srv.shutdown()
            srv.server_close()


class TestPeerProtocol(unittest.TestCase):
    def test_handshake(self):
        info_hash = b"\x01" * 20
        raw = T.build_handshake(info_hash, PEER_ID)
        self.assertEqual(len(raw), 68)
        self.assertEqual(raw[0], 19)
        self.assertEqual(raw[1:20], b"BitTorrent protocol")
        self.assertEqual(raw[20:28], b"\x00" * 8)
        self.assertEqual(T.parse_handshake(raw), (info_hash, PEER_ID))
        self.assertRaises(T.PeerError, T.parse_handshake, raw[:40])
        bad = bytearray(raw)
        bad[1:4] = b"XYZ"
        self.assertRaises(T.PeerError, T.parse_handshake, bytes(bad))

    def test_message_framing(self):
        self.assertEqual(T.encode_message(None), b"\x00\x00\x00\x00")
        self.assertEqual(T.encode_message(T.UNCHOKE),
                         struct.pack("!I", 1) + bytes([T.UNCHOKE]))
        have = T.encode_message(T.HAVE, struct.pack("!I", 3))
        self.assertEqual(have, struct.pack("!I", 5) + bytes([T.HAVE]) +
                         struct.pack("!I", 3))
        req = T.build_request(2, 0, 16384)
        self.assertEqual(req, T.encode_message(
            T.REQUEST, struct.pack("!III", 2, 0, 16384)))
        idx, begin, block = T.parse_piece(struct.pack("!II", 2, 0) + b"data")
        self.assertEqual((idx, begin, block), (2, 0, b"data"))

    def test_bitfield(self):
        field = T.bitfield_from_pieces([0, 3, 8], 10)
        self.assertTrue(T.bitfield_has(field, 0))
        self.assertTrue(T.bitfield_has(field, 3))
        self.assertTrue(T.bitfield_has(field, 8))
        self.assertFalse(T.bitfield_has(field, 1))
        self.assertFalse(T.bitfield_has(field, 9))
        self.assertFalse(T.bitfield_has(field, 99))


class TestDownload(unittest.TestCase):
    def test_end_to_end_via_fake_tracker_and_peer(self):
        data = bytes(range(256)) * 2  # 512 bytes, piece_length 64 -> 8 pieces
        tor = parse_local(data, piece_length=64)
        peer = FakePeer(tor, data)
        peer.start()
        srv = start_tracker([("127.0.0.1", peer.port)])
        try:
            tor.announce = f"http://127.0.0.1:{srv.server_port}/announce"
            peers = T.get_peers(tor, PEER_ID)
            self.assertEqual(peers, [("127.0.0.1", peer.port)])
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "out.bin")
                seen = []
                T.download(tor, peers, out, peer_id=PEER_ID,
                           on_piece=seen.append)
                with open(out, "rb") as fh:
                    self.assertEqual(fh.read(), data)
                self.assertEqual(seen, list(range(tor.num_pieces)))
        finally:
            peer.close()
            srv.shutdown()
            srv.server_close()

    def test_short_last_piece(self):
        data = b"A" * 70
        tor = parse_local(data, piece_length=16)  # 5 pieces, last 6 bytes
        peer = FakePeer(tor, data)
        peer.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "out.bin")
                T.download(tor, [("127.0.0.1", peer.port)], out,
                           peer_id=PEER_ID)
                with open(out, "rb") as fh:
                    self.assertEqual(fh.read(), data)
        finally:
            peer.close()

    def test_corrupt_piece_never_written(self):
        data = b"B" * 64
        tor = parse_local(data, piece_length=16)
        peer = FakePeer(tor, data, corrupt_piece=1)
        peer.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "out.bin")
                self.assertRaises(T.DownloadError, T.download, tor,
                                  [("127.0.0.1", peer.port)], out,
                                  peer_id=PEER_ID)
                # Nothing valid was left behind for the corrupt piece
                # path: download raises before returning, and the
                # file is incomplete (piece 0 written, piece 1 not).
                with open(out, "rb") as fh:
                    content = fh.read()
                self.assertEqual(content[:16], data[:16])
                self.assertNotEqual(content[16:32], data[16:32])
        finally:
            peer.close()

    def test_verify_piece(self):
        self.assertTrue(T.verify_piece(b"abc",
                                       hashlib.sha1(b"abc").digest()))
        self.assertFalse(T.verify_piece(b"abd",
                                        hashlib.sha1(b"abc").digest()))


class TestCLI(unittest.TestCase):
    def test_info(self):
        data = b"0123456789abcdef"
        raw, _ = make_torrent_bytes(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.torrent")
            with open(path, "wb") as fh:
                fh.write(raw)
            tor = T.parse_torrent_file(path)
            # CLI path: run module main with argv capture
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = T.main(["torrent.py", "info", path])
            out = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("127.0.0.1:1/announce", out)
            self.assertIn(tor.info_hash.hex(), out)
            self.assertIn("test.bin", out)


if __name__ == "__main__":
    unittest.main()

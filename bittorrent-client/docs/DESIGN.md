# DESIGN — BitTorrent Client

## Assumptions (stated before coding, ponytail rule)

1. Python 3 standard library only (`hashlib`, `socket`, `struct`,
   `urllib`, `os`, `sys`). No third-party BitTorrent library — the
   protocol is the point of the exercise.
2. Single-file torrents are the fully supported case; multi-file
   torrents parse (name, total length, piece hashes) and download
   as one concatenated byte stream in `files` order. Real clients
   split that stream back into the listed files; that split is
   deliberately not built (minimum code: the piece/hash logic is
   identical, only the final file layout differs).
3. Download is sequential and single-peer-at-a-time: pieces in
   index order, peers tried in tracker order, one connection per
   piece attempt. The page's Step 6 suggests a concurrent queue;
   sequential retries give the same correctness guarantees
   (bitfield check, hash verification, requeue-on-failure) with
   far less code and no thread-safety surface. Throughput, not
   correctness, is what concurrency would buy.
4. HTTP trackers only. UDP trackers (BEP 15) and DHT are out of
   scope per SPEC.md.
5. `peer_id` is `-SC0100-` + 12 bytes from `os.urandom`, unless a
   caller supplies one (tests do, for determinism).
6. Block size is 16384 bytes; a peer that rejects larger blocks is
   never asked for more.
7. Timeouts: 10 s default on tracker HTTP and on peer sockets, so
   a dead peer fails fast and the next peer is tried instead of
   hanging the download.
8. The CLI never contacts the network unless the user runs
   `download`: bare `torrent.py file.torrent` and `info` only parse
   and print. This keeps the safe default offline.

## Module layout (single file, `torrent.py`)

- Bencode: `bencode(obj) -> bytes`, `bdecode(data) -> object`,
  both raising `BencodeError`. The parser is index-based
  (`_decode_at(data, pos) -> (value, next_pos)`) so metainfo
  parsing can slice out the raw `info` bytes.
- Metainfo: `Torrent` dataclass — `announce`, `name`, `piece_length`,
  `piece_hashes` (list of 20-byte values), `total_length`,
  `files` (None for single-file, else list of (length, path)),
  `info_hash`, `num_pieces`, `piece_size(index)` (last piece may
  be short). `parse_torrent_bytes(data)` / `parse_torrent_file(path)`
  / `load_torrent(path_or_url)` (a URL is fetched with urllib,
  matching Step 2; tests never use this path with a real URL).
- Tracker: `build_tracker_url(torrent, peer_id, port, ...)`,
  `parse_tracker_response(data) -> (peers, interval)`,
  `get_peers(torrent, peer_id, port, ...)` — one GET, returns
  `[(ip, port), ...]`. Compact and non-compact peer lists both
  parsed; `failure reason` raises `TrackerError`.
- Peer protocol: `build_handshake(info_hash, peer_id)`,
  `parse_handshake(data)` (validates pstr and length),
  `encode_message(msg_id, payload)`, `decode_message` is folded
  into `PeerSession.recv_message()` which reads exactly
  (length-prefix framing over a buffered socket). `Message`
  dataclass: `msg_id` (None = keep-alive), `payload`.
  Bitfield helpers: `bitfield_has(bitfield, index)`,
  `bitfield_set(bitfield, index)`, `bitfield_from_pieces(...)`.
  `build_request(index, begin, length)`,
  `parse_piece(payload) -> (index, begin, block)`.
- Download: `PeerSession` (context manager: connect, handshake
  with info_hash check, send `interested`, wait for `unchoke`
  while collecting bitfield/`have` updates; `request_piece(index,
  length) -> bytes` requesting 16 KiB blocks and reassembling
  them). `verify_piece(data, expected_hash)`,
  `download(torrent, peers, output_path, peer_id, ...)`:
  for each piece, try peers in order until one serves a
  hash-verified piece, write it at `index * piece_length`,
  raise `DownloadError` if no peer can serve a piece.
- CLI: `torrent.py info <torrent>` (or bare `<torrent>`) prints
  announce URL, name, total length, piece length/count,
  info_hash (hex). `torrent.py download <torrent> [output]`
  announces once, prints peers, downloads, prints each verified
  piece id (per Step 7's completion signal) and a final summary.

## Verifiable success criteria

- `python3 -m unittest discover -s tests -v` passes (see TEST_PLAN.md).
- `python3 torrent.py info <synthetic.torrent>` prints the
  announce URL and info_hash matching an independent SHA-1 of the
  info dict.
- `python3 torrent.py download <synthetic.torrent> out.bin`
  against local fake tracker + fake peer (in tests) reproduces
  the original file byte-for-byte.
- No test, and no default CLI path, touches a real tracker, peer,
  or torrent: all network tests bind `127.0.0.1` ephemeral ports.

## Divergences from the page (honest list)

- Sequential download instead of the page's concurrent per-peer
  worker queue (assumption 3 above).
- Multi-file torrents download as a concatenated stream, not as
  their listed directory tree (assumption 2).
- No re-announce / `interval` loop, no `event=started/completed`
  tracker parameters: the page's Step 3 parameter list does not
  include `event`, and a single announce suffices for a
  download-only run.
- Real-swarm behaviour (choking/unchoking dynamics, peers that
  disconnect mid-piece, piece availability churn) cannot be
  verified locally; the fake peer in tests is always unchoked
  and always serves. What needs a real swarm is recorded in
  TEST_PLAN.md.

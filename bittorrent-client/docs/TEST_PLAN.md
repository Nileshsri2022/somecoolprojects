# TEST_PLAN — BitTorrent Client

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests are in `tests/test_torrent.py`, stdlib `unittest` only.
No test downloads a real torrent or contacts a real tracker/peer:
synthetic `.torrent` files are bencoded in-run, and the tracker
and peer are fake servers bound to `127.0.0.1` on ephemeral ports
(port 0, OS-assigned), started in `setUp` and shut down in
`tearDown` by explicit server objects (no background processes
left behind, no `pkill`).

## Cases

Bencode (Step 1):
- Encode/decode round-trip for strings (bytes and str), integers
  (including 0 and negatives), nested lists, nested dicts.
- Encoder sorts dict keys lexicographically.
- Page examples verbatim: `6:coding`, `i100e`,
  `l6:Coding10:Challengese`, and the nested-dict example from
  Step 1 (keys `Rating` before `website:`).
- Decoder rejects: trailing bytes, truncated string/list/dict,
  `i03e` (leading zero), `i-0e`, non-string dict key, empty input.

Metainfo (Step 2):
- Synthetic single-file torrent parses: announce URL, name,
  piece length, piece hashes, total length, piece count.
- `info_hash` equals `hashlib.sha1` of the raw info-dict bytes
  sliced from the file — including when the source info dict's
  keys are deliberately out of order (re-encoding would give a
  different hash; the raw slice must not).
- Last piece is shorter than `piece_length` when the file size
  is not a multiple of it; `piece_size()` reflects that.
- Malformed torrents rejected: top level not a dict, missing
  `announce`/`info`, `pieces` length not a multiple of 20,
  missing `length`/`files`.
- Multi-file torrent parses with summed total length.

Tracker (Step 3):
- `build_tracker_url` includes every Step 3 parameter
  (info_hash, peer_id, port, uploaded=0, downloaded=0, left,
  compact=1), URL-encoded, and preserves an existing query string.
- Fake HTTP tracker: `get_peers` returns the compact peer list
  (two peers, exact IPs/ports) from a bencoded response.
- Non-compact peer list (list of dicts) parses to the same pairs.
- Tracker `failure reason` raises `TrackerError`; HTTP error
  status raises `TrackerError` (not a silent empty list).

Peer protocol (Steps 4–5):
- Handshake builds to exactly 68 bytes with the right layout
  (19, "BitTorrent protocol", 8 zero bytes, info_hash, peer_id);
  `parse_handshake` round-trips it and rejects a wrong pstr,
  a wrong length, and a truncated handshake.
- `encode_message` framing: keep-alive is 4 zero bytes; choke /
  unchoke / interested / not interested have length 1; `have`
  carries a 4-byte index; request carries index/begin/length;
  piece payload parses back to (index, begin, block).
- Bitfield: `bitfield_has`/`bitfield_set` follow the page's
  rule (high bit of byte 0 = piece 0, high bit of byte 1 =
  piece 8); spare bits beyond the piece count are ignored.

Download, end to end (Steps 6–8):
- Fake peer server: on connect, verifies the client's handshake
  info_hash, replies with its own handshake, sends a bitfield
  covering all pieces, sends unchoke, then answers every
  `request` with the correct block of the synthetic file.
  (It also answers `interested`; it ignores anything else.)
- Fake tracker returns that fake peer. `download()` through the
  tracker + peer path reproduces the synthetic file
  byte-for-byte, including a multi-piece file whose last piece
  is short, and the written file's per-piece SHA-1s match.
- Piece verification: `verify_piece` accepts matching data,
  rejects tampered data; a fake peer serving a corrupted block
  for one piece causes `download()` to raise `DownloadError`
  (the bad piece is discarded, not written) when it is the only
  peer — proving bad data never reaches the output file.
- CLI: `info` subcommand (and bare torrent path) prints
  announce URL, name, and hex info_hash; `download` subcommand
  against the fake tracker/peer writes the file and prints a
  per-piece "verified piece N" line.

## What cannot be tested locally (needs a real swarm)

- Interop with real clients/trackers (choke/unchoke timing,
  peers disconnecting mid-piece, optimistic unchoking, peers
  whose bitfield arrives after `have` messages, NAT/firewall
  traversal, tracker `interval` / re-announce behaviour).
- Download speed and multi-peer parallelism (by design,
  sequential — see DESIGN.md).
- Large-file behaviour (multi-GB files, many-thousand-piece
  torrents): the logic is size-independent, but only small
  synthetic files are exercised here.

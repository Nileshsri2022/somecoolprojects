# SPEC — Build Your Own BitTorrent Client

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-bittorrent

Slug used: `challenge-bittorrent`.
Caveat: the first guess `challenge-bittorrent-client` returns HTTP 404.
The correct slug was found via the site's tag page, which links to
`challenge-bittorrent`. The page is Coding Challenge #100 (per its
Substack mirror); Steps 0–8 below follow that page, plus the
BitTorrent Protocol Specification (bittorrent.org) it points to for
message payloads it does not spell out.

## Step 0 — scope

A download-only client: read a `.torrent` file, ask an HTTP tracker
for peers, speak the peer wire protocol, verify every piece by SHA-1,
assemble the file, exit. No seeding, DHT, UDP trackers, magnet links,
or multi-torrent operation (all listed only under "Going Further").

## Step 1 — Bencoding

- String: `<len>:<bytes>`, e.g. `6:coding`.
- Integer: `i<base-10>e`, e.g. `i100e`. No leading zeros, no `-0`.
- List: `l<elements>e`, e.g. `l6:Coding10:Challengese`.
- Dictionary: `d<key value pairs>e`, keys are byte strings in
  lexicographical order, e.g.
  `d17:Coding Challengesd6:Rating7:Awesome8:website:20:codingchallenges.fyiee`.
- Decoder rejects trailing bytes, truncated input, and malformed
  integers/strings. All dictionary keys and string values are `bytes`
  (torrent data is not guaranteed UTF-8); only `announce`/`name` are
  decoded to text for display, lossily where needed.

## Step 2 — Metainfo (.torrent)

A bencoded dictionary. Keys used:

- `announce`: tracker URL (string).
- `info`: dictionary with `name`, `piece length`, `pieces`
  (concatenated 20-byte SHA-1 hashes, one per piece), and either
  `length` (single file) or `files` (multi-file, each with `length`
  and `path` components).
- `info_hash`: SHA-1 of the *raw* bencoded `info` dictionary bytes
  exactly as they appear in the file (not a re-encoding — re-encoding
  is only equal when the source dict was already canonically sorted).

## Step 3 — HTTP tracker

GET to the announce URL with query parameters:

- `info_hash`: 20 raw bytes, URL-encoded.
- `peer_id`: 20 bytes, `-SC0100-` + 12 random bytes, URL-encoded.
- `port`: listening port (default 6881).
- `uploaded` / `downloaded`: 0 at start.
- `left`: total bytes remaining (file size from `info`).
- `compact`: 1.

A 200 response body is a bencoded dictionary. `peers` is either a
byte string of 6 bytes per peer (4-byte IPv4 in network order +
2-byte port in network order) or a list of `{"ip", "port"}` dicts.
A `failure reason` key is an error. `interval` is honoured only as
information (no re-announce loop: this client announces once).

## Step 4 — Peer wire protocol

- Handshake (first message, 68 bytes for the standard protocol
  string): `<len=19><"BitTorrent protocol"><8 reserved zero
  bytes><20-byte info_hash><20-byte peer_id>`. The peer's handshake
  must carry the same info_hash, else the connection is dropped.
- Keep-alive: 4-byte length prefix of 0, no message id, no payload.
- Length-prefixed messages: `<4-byte big-endian length><1-byte
  id><payload>`, length counts id + payload. Ids:
  0 choke, 1 unchoke, 2 interested, 3 not interested, 4 have
  (4-byte piece index), 5 bitfield, 6 request (piece index,
  begin offset, length — all 4-byte big-endian), 7 piece (piece
  index, begin offset, block bytes), 8 cancel (same payload as
  request).
- Bitfield: byte 0's high bit is piece 0, byte 1's high bit is
  piece 8, and so on; spare bits in the last byte are zero.
  A `have` message sets the corresponding bit.

## Step 5 — Handshake + bitfield

Connect (TCP) to each peer, handshake, record its bitfield before
requesting anything. A peer is only asked for pieces its bitfield
(or later `have` messages) says it has.

## Step 6 — Piece tracking

Pieces are tracked by index in order (sequential, not rarest-first
— the page suggests a queue; sequential order over a simple
verified/not-verified list is the minimum that satisfies it and is
what is implemented). A piece that fails (peer lacks it, connection
lost, hash mismatch) is retried against the next peer; it is only
marked done when its SHA-1 matches.

## Step 7 — Downloading pieces

After handshake: send `interested`, wait for `unchoke` (handling
bitfield / have / keep-alive meanwhile), then request the piece in
blocks of at most 16384 bytes (16 KiB, the page's safe bet),
reassemble blocks in offset order, SHA-1 the reassembled piece,
compare with `pieces[index]`, discard on mismatch.

## Step 8 — Assembly

Each verified piece is written to the output file at offset
`index * piece_length`. The last piece may be shorter than
`piece_length`. The output filename defaults to `info.name` for a
single-file torrent (for a multi-file torrent, the concatenated
content, in `files` order, is written to the given output path —
see DESIGN.md). The client exits once every piece verifies.

## Out of scope (page's "Going Further", not built)

Seeding/uploading to other peers, magnet links, building a tracker,
UDP trackers, DHT/PEX, rarest-first or end-game piece selection,
parallel multi-peer download (peers are tried in order, one at a
time — see DESIGN.md), and re-announcing to the tracker.

# bittorrent-client — Build Your Own BitTorrent Client

Coding Challenges `challenge-bittorrent` (page slug found via the
site's tag page — `challenge-bittorrent-client` 404s), worked in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Download-only client, Python 3 standard library only: bencode
encode/decode, `.torrent` metainfo parsing (info_hash = SHA-1 of
the *raw* info-dict bytes), HTTP tracker requests (compact and
non-compact peer lists), peer wire protocol (handshake, bitfield,
interested/unchoke, 16 KiB block requests, piece messages), SHA-1
piece verification, and file assembly.

## Usage

```sh
python3 torrent.py info file.torrent        # parse + print, no network
python3 torrent.py file.torrent             # same as info
python3 torrent.py download file.torrent [output]
```

`download` announces once to the tracker's announce URL, prints the
peers, downloads pieces in order (peers tried in tracker order,
one at a time), prints `Verified piece N` per piece, and writes the
assembled file (default output name = `info.name`).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

19 tests, all local: synthetic torrents built in-run, fake HTTP
tracker and fake peer on `127.0.0.1` ephemeral ports. No test
downloads a real torrent or contacts a real tracker/peer.

## Files

- `torrent.py` — bencode, metainfo, tracker, peer protocol, download, CLI.
- `docs/SPEC.md` — challenge steps 0–8 as implemented.
- `docs/DESIGN.md` — assumptions and divergences.
- `docs/TEST_PLAN.md` — test cases and what needs a real swarm.
- `tests/test_torrent.py` — the test suite.

## Known limits (see docs/DESIGN.md)

Sequential, single-peer-at-a-time download (not the page's
concurrent queue); multi-file torrents download as one
concatenated stream, not a directory tree; HTTP trackers only
(no UDP/DHT/magnet); no seeding, no re-announce loop. Real-swarm
behaviour (choking dynamics, mid-piece disconnects) is untested
locally by design — see `docs/TEST_PLAN.md`.

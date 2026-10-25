# dns-forwarder — Build Your Own DNS Forwarder

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (SPEC, DESIGN, TEST_PLAN).
Source page: https://codingchallenges.fyi/challenges/challenge-dns-forwarder/

A DNS forwarder in pure Python 3 standard library: it listens for UDP
DNS queries, parses them (RFC 1035, including name compression),
forwards them to a configured upstream nameserver, returns the
upstream answer to the original client (with the client's transaction
id restored), and caches successful answers for their TTL so later
identical questions are answered locally. It never resolves
recursively itself — that is what distinguishes it from the sibling
`dns-resolver` project.

## Usage

```sh
# Listen on port 53 (default), forward to Google DNS (default 8.8.8.8:53)
python3 dns_forwarder.py

# Test-style invocation: ephemeral-ish port, local upstream, verbose
python3 dns_forwarder.py --port 1053 --upstream 127.0.0.1 \
    --upstream-port 15353 --verbose

# Serve a LAN (default bind is loopback only)
python3 dns_forwarder.py --bind 0.0.0.0 --port 53

# Disable the cache (forward every query, Step 4 alone)
python3 dns_forwarder.py --port 1053 --no-cache
```

Then query it, e.g. `dig @127.0.0.1 -p 1053 www.google.com`.
Verbose mode prints `MSG received`, a human-readable header/questions
dump (Step 2 shape), `Cache hit`/`Cache miss`, and `Forwarded Question`.

Options: `--bind` (default `127.0.0.1`), `--port` (default 53),
`--upstream` (default `8.8.8.8`), `--upstream-port` (default 53),
`--timeout` (default 5 s, after which the client gets SERVFAIL),
`--no-cache`, `--verbose`. Ctrl-C exits cleanly.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use local fake upstream DNS servers on ephemeral ports only —
no public DNS server is contacted by the test suite. One sandbox
quirk the tests (and a fallback in the server) work around: this
sandbox blocks unconnected UDP `sendto()` with EPERM, while `send()`
on a connected UDP socket works; see `docs/DESIGN.md`.

## Divergences from the challenge page

1. Default bind is `127.0.0.1`, not all interfaces (`--bind 0.0.0.0`
   serves a LAN).
2. Single-threaded, serial request handling; a slow upstream blocks
   later queries until `--timeout`.
3. Upstream transaction ids are remapped (question bytes unchanged);
   the client always sees its own id back.
4. Cache stores answer records only; authority/additional sections
   (including EDNS OPT) are passed through on the forwarded path but
   not re-served from cache.
5. Only NOERROR responses with at least one answer are cached;
   NXDOMAIN/SERVFAIL/empty answers are forwarded but not cached.
6. Multi-question queries are forwarded but not cached.
7. Malformed packets: < 12 bytes ignored, otherwise FORMERR;
   upstream timeout yields SERVFAIL. Cache capped at 1024 entries.

## NOT verified live here

Binding port 53 and serving a real LAN are privilege- and
network-position-dependent and were NOT verified in this sandbox;
neither was any live query to `8.8.8.8`. The tested path is
ephemeral ports against local fake upstreams. Full list in
`docs/SPEC.md`.

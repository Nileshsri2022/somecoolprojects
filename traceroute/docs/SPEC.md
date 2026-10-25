# SPEC — Traceroute (somecoolprojects entry 24)

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-traceroute
Slug used: `challenge-traceroute` — first guess, no 404, no correction needed.

## What the page asks for (Steps 0–5)

- Step 0: set up tooling (Python 3, stdlib only).
- Step 1: CLI takes one argument, the hostname, and prints the header line:
  `traceroute to <host> (<ip>), <max> hops max, 32 byte packets`
  The page's payload is the text string `codingchallenges.fyi trace route`
  (32 bytes). The page says "you can pick your own number of max hops";
  its examples use 64.
- Step 2: two sockets — one to send a UDP message, one to receive the
  ICMP reply. Destination ports in the range 33434–33534 (the page's
  range, matching classic traceroute). Set TTL on the sending socket,
  start at TTL 1, print the responding host's IP.
- Step 3: print the responder's hostname if reverse DNS resolves, else
  the IP again: `1  192.168.68.1 (192.168.68.1)`.
- Step 4: keep sending with incrementing TTL until a packet reaches the
  destination. No response → wildcard: `3  *  * *` (one `*` per probe).
- Step 5: record round-trip latency per hop, e.g.
  `1  192.168.68.1 (192.168.68.1) 5.131 ms`.

## Implemented behaviour

- `python3 traceroute.py [-m MAX_HOPS] [-q PROBES] [-w TIMEOUT] [--method udp|icmp] [--no-resolve] HOST`
  - `-m/--max-hops`: default 30 (see DESIGN.md for why this differs
    from the page's 64).
  - `-q/--probes`: probes per hop, default 3 (classic traceroute; the
    page's Step 4/5 examples show 1 probe — `-q 1` reproduces them).
  - `-w/--timeout`: seconds to wait per probe, default 3.0.
  - `--method udp` (default, the page's method) or `icmp` (ICMP Echo
    Request probes; parsing of Echo Reply is covered either way).
  - `--no-resolve`: skip reverse-DNS lookups, print IPs only.
- Header line exactly as the page's Step 1 form, with the chosen
  max-hops and the payload size (32 for the default payload).
- Hop lines: hop number, then per probe either
  `<hostname> (<ip>) <rtt> ms` or `*`. Probes from a different responder
  than the first probe of that hop go on continuation lines (indented,
  no hop number), as in the page's intro example (hop 5/6 there).
  Probes from the same responder append their timings on the same line.
- Stopping: the trace stops after the hop on which a probe is judged
  to have reached the destination (UDP: ICMP Destination Unreachable /
  Port Unreachable, type 3 code 3; ICMP method: Echo Reply, type 0),
  or after max-hops, whichever comes first. A hop of all `*` never
  stops the trace — later hops may still answer.
- If the hostname resolves to several addresses, the first is used and
  a warning like the system tool's is printed to stderr:
  `traceroute: Warning: <host> has multiple addresses; using <ip>`.
- Errors: unresolvable host, bad option values, and socket failures
  print to stderr and exit non-zero. No live trace is claimed unless
  it actually ran (see README.md privilege note).

## Out of scope (ponytail: nothing speculative)

No IPv6, no TCP/SYN probes, no AS-number lookup, no packet capture
from a pcap file, no parallel probing. One probe at a time, in order,
exactly as the page describes.

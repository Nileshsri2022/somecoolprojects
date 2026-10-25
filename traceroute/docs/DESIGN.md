# DESIGN — Traceroute

## Assumptions (stated before coding, per ponytail rules)

1. Python 3 stdlib only (`socket`, `struct`, `time`, `select`,
   `argparse`, `sys`). No third-party packet libraries.
2. The page's method is UDP probes + ICMP replies. That is the default.
   An `--method icmp` variant is included only because the task brief
   explicitly asks for ICMP Echo Reply parsing; it reuses the same
   receive/parse/format path, with an Echo Request builder added.
3. Receiving ICMP requires a raw socket, which requires privileges
   (root / `CAP_NET_RAW`) on Linux. Nothing in this design can remove
   that OS requirement. Therefore all packet logic is factored into
   pure functions so it is fully testable without privileges, and the
   live-trace path is isolated in one transport class.
4. Reverse DNS may be slow or absent; a failed lookup falls back to
   the bare IP (page Step 3) and never aborts a hop.
5. Round-trip time is measured around a single send→receive pair with
   `time.monotonic()`; it includes local processing, as with the real
   tool, and is not corrected for anything.

## Module layout (single file, `traceroute.py`)

- Constants: `BASE_PORT = 33434`, `LAST_PORT = 33534` (page's range),
  `PAYLOAD = b"codingchallenges.fyi trace route"` (32 bytes, page's
  string), `DEFAULT_MAX_HOPS = 30`, `DEFAULT_PROBES = 3`,
  `DEFAULT_TIMEOUT = 3.0`.
- Pure, privilege-free functions (unit-tested directly):
  - `checksum(data)` — RFC 1071 Internet checksum (ICMP Echo only;
    UDP checksums are left to the kernel).
  - `build_echo_request(identifier, sequence, payload)` — 8-byte ICMP
    header (type 8, code 0) + payload.
  - `port_for(ttl, probe_index, probes_per_hop)` — sequential ports
    starting at 33434: global probe number
    `(ttl - 1) * probes_per_hop + probe_index`, wrapped into
    33434–33534, so every probe gets a distinct port within the
    page's range until it wraps.
  - `parse_icmp_packet(data)` — parses a received datagram: outer IPv4
    header (variable length from its IHL field) → ICMP header
    (type, code) → for Time Exceeded (11) and Destination Unreachable
    (3), the embedded original IPv4 header + first 8 bytes of the
    original datagram, from which the original UDP destination port
    (or ICMP identifier/sequence) is recovered. Returns an
    `IcmpInfo` or `None` for truncated/garbage input. Never raises on
    malformed input — a malformed packet is simply ignored.
  - `is_destination_reached(info)` — True for type 3 code 3 (UDP
    method: the destination host answered "port unreachable", meaning
    the probe arrived) and type 0 (ICMP method: Echo Reply). Type 11
    (Time Exceeded) means an intermediate hop. Anything else: False.
  - `resolve_display(ip, resolve=True)` — reverse DNS with fallback.
  - `format_header(host, ip, max_hops, packet_size)` and
    `format_hop(record)` — all output formatting, no I/O.
- Data: `ProbeResult(addr, rtt_ms)` where `addr is None` means
  timeout (`*`); `HopRecord(ttl, probes, reached)`.
- Trace loop: `trace(dest_ip, max_hops, probes, timeout, method,
  transport)` — TTL 1..max_hops, probes per hop, records results,
  stops when a hop is marked reached. It talks only to a `transport`
  object with one method, `probe(...)`, so tests inject a fake
  transport and never touch a socket.
- Live transport: `RealTransport` — one UDP (or raw ICMP, for
  `--method icmp`) send socket and one raw ICMP receive socket.
  Per probe it sets TTL via `IP_TTL`, sends, then reads with `select`
  until the per-probe deadline, discarding packets that do not match
  this probe (wrong embedded UDP port / wrong Echo id+sequence).
  Unmatched or timed-out probes become `*`. Socket creation failure
  (e.g. `PermissionError`) propagates to `main`, which reports it
  plainly instead of fabricating output.

## Defaults that diverge from the page (documented, not hidden)

- Max hops 30, not the page's 64: 30 is the system traceroute
  default, and 64-hop routes are rare in practice. `--max-hops 64`
  reproduces the page exactly.
- Probes per hop 3, not the page's Step 4/5 single probe: 3 is the
  classic behaviour shown in the page's own intro example (three
  timings per hop) and gives per-hop variance. `-q 1` reproduces the
  Step 4/5 output shape.
- Packet size 32 in the header: the page's Step 1 example says 32
  byte packets (its payload string is 32 bytes); its intro example
  says 52. This tool reports the actual payload length, so the header
  is always truthful for the payload actually sent.

## Comparison with system traceroute

- Same: TTL-incrementing probes, `*` timeouts, header shape,
  `host (ip) rtt ms` hop shape, continuation lines for hops where
  probes take different paths, destination ports 33434+.
- Different: no `-I/-U/-T` method zoo beyond udp/icmp, no IPv6, no
  `--mtu`/fragmentation discovery, timings are per-probe wall-clock
  RTTs with no averaging, and this tool never prints the
  `traceroute: Warning` line for anything except multiple addresses.
  System traceroute on this sandbox (if present) is the reference for
  the header/hop shape only; live comparison requires privileges this
  sandbox may not grant (see README.md).

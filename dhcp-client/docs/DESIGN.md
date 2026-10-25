# DESIGN — DHCP Client

Python 3 standard library only. Single file: `dhcp_client.py`.
Tests: `tests/test_dhcp_client.py` (unittest, fake server on loopback).

## Assumptions (stated before coding, ponytail rule)

- IPv4 + Ethernet only. No DHCPv6, no non-Ethernet hardware types.
- Network byte order (big-endian) throughout, via `struct`.
- The client is a *protocol* client: it builds, sends, receives and
  parses DHCP packets. It is not an OS network configurator.
- MAC addresses are given as `aa:bb:cc:dd:ee:ff` (or 12 hex digits,
  or 6 raw bytes); anything else raises `ValueError`.
- IPv4 addresses are dotted quads; parsing uses `ipaddress` (stdlib)
  so malformed addresses fail loudly instead of silently truncating.
- Options are stored as `dict[int, bytes]` (last occurrence wins on
  decode). Pad (0) is skipped, End (255) stops parsing, trailing
  bytes after End are ignored. Unknown option codes are preserved
  as raw bytes, not dropped, so a future option survives a round-trip.
- A received packet must be at least 240 bytes (236 fixed + 4 cookie),
  start with the magic cookie, and have `op == 2` (BOOTREPLY) when it
  is checked as a server reply. `from_bytes` itself accepts both
  directions (op 1 or 2) so tests can round-trip client packets; the
  client's receive loop additionally requires `op == 2` and a
  matching xid.
- Transaction IDs: a fresh random 32-bit xid per exchange (DISCOVER
  and REQUEST use different xids). Rationale: RFC 2131 requires the
  client to pick an xid and the server to echo it; reusing one xid
  across both exchanges would conflate an OFFER with an ACK if a
  retransmission arrived late. Each exchange waits for its own xid,
  so this is strictly safer and still spec-compliant. The xid can be
  injected (constructor / builder argument) for deterministic tests.
- `secs` is 0 in every packet we send: we do not track elapsed time
  across retries, and no retry/backoff loop is implemented (one send,
  one bounded wait per exchange). Retransmission timers are out of
  scope; a timeout raises `TimeoutError` and the caller retries.
- Flags: DISCOVER and REQUEST set the broadcast flag (0x8000), as a
  real client with no address must, so a server replies by broadcast.
  On loopback tests the fake server replies unicast to the sender,
  which the socket receives regardless of the flag.
- Parameter Request List in DISCOVER: [1, 3, 6, 51] (mask, router,
  DNS, lease time) — exactly the fields `Lease` parses.
- No hostname is sent by default; `--hostname` adds option 12.

## Data model

- `DhcpMessage`: op, htype=1, hlen=6, hops=0, xid, secs=0, flags,
  ciaddr, yiaddr, siaddr, giaddr (all dotted-quad strings, "0.0.0.0"
  by default), chaddr (6 raw bytes), sname/file (zeros), options
  dict. Methods: `to_bytes()`, `from_bytes(data)` (classmethod),
  `message_type` property (option 53, or None), `option_ip(code)`,
  `option_ips(code)` (list), `option_u32(code)`, `option_string(code)`.
- `Lease`: ip, subnet_mask, routers (list), dns_servers (list),
  lease_time (seconds, or None if the server sent none), server_id,
  xid. `from_ack(message)` validates the ACK (message type 5,
  non-zero yiaddr) and extracts the fields; missing mask/router/DNS
  become None/[] rather than errors, because those options are
  optional in the protocol.
- `DhcpClient`: holds server address/port, client port, timeout,
  MAC, and an optional xid factory. Methods:
  - `discover(xid=None) -> DhcpMessage` — send DISCOVER, wait for
    a matching OFFER.
  - `request(offer, xid=None) -> DhcpMessage` — send REQUEST for
    `offer.yiaddr` with server id from the offer, wait for ACK/NAK.
  - `obtain_lease() -> Lease` — DISCOVER + REQUEST, returns a
    `Lease` on ACK, raises `DhcpNakError` on NAK, `TimeoutError`
    on no reply.
  - `release(lease)` — send DHCPRELEASE (ciaddr = lease IP,
    server id = lease server), fire-and-forget (no reply expected
    per RFC 2131); returns the packet bytes sent, for testability.
  - `decline(offer)` — send DHCPDECLINE for an offered address
    (e.g. if the address is found in use); fire-and-forget.
  - Context manager (`with DhcpClient(...) as c:`) closes the socket.
- Builders (module functions, used by the client and directly by
  tests): `build_discover`, `build_request`, `build_decline`,
  `build_release`. Each returns a `DhcpMessage`, not bytes, so tests
  can inspect fields before serialising.

## Encoding / decoding

- Fixed header: `struct.pack("!BBBBIHHIIII16s64s128s", ...)` —
  236 bytes. Options: cookie + for each option
  `bytes([code, len]) + value`, in dict insertion order, then
  `b"\xff"`. Encoding always emits options in insertion order, so a
  decode→encode round-trip is stable for packets we build.
- Decoding: fixed part unpacked with the same format; chaddr is
  truncated to `hlen` bytes (6); sname/file are kept as raw bytes
  but not interpreted. Options parsing bounds-checks every
  length byte (a claimed length past the end of the packet raises
  `ValueError` instead of slicing silently).
- IP helpers: `_ip_to_bytes` / `_bytes_to_ip` via `ipaddress`.
- MAC helpers: `parse_mac` accepts colon-separated, hyphen-separated,
  or bare hex; `format_mac` renders colon-separated lowercase.

## Sockets (page step 2, adapted for safety)

- One UDP socket, `SO_BROADCAST` enabled, `SO_REUSEADDR` set, bound
  to `("0.0.0.0", client_port)`. Default `client_port=0` (ephemeral)
  so tests and unprivileged runs never need port 68. Live use passes
  `--client-port 68` and `--broadcast` (target `255.255.255.255`,
  server port 67); that path needs appropriate privileges and is
  documented in README.md as requiring them — it is never exercised
  by the tests.
- Unicast mode uses connected UDP (`connect` + `send`/`recv`)
  instead of `sendto`/`recvfrom`: the two are equivalent for a
  single peer, and unconnected `sendto` is blocked (EPERM) in this
  sandbox — the same workaround as the dns-resolver project.
  Broadcast mode keeps `sendto`/`recvfrom`. The fake server in
  `tests/` has a matching sandbox quirk, verified by experiment:
  it must use `recv()` (not `recvfrom()`) on its socket once
  connected, or its next `send` fails with EPERM; and it must not
  bind a second socket to the server port for replies, because the
  last-bound socket then steals later incoming packets.
- Receive loop: `select`/`settimeout` bounded wait; packets that are
  too short, have a bad cookie, are not BOOTREPLY, have a wrong xid,
  or (for the offer step) are not an OFFER are ignored and the wait
  continues until the timeout. This mirrors a real client ignoring
  unrelated broadcast traffic.
- No thread, no background server in the library itself. The fake
  server lives only in `tests/`.

## CLI

```
python3 dhcp_client.py --mac aa:bb:cc:dd:ee:ff [--server 127.0.0.1]
    [--server-port 67] [--client-port 0] [--timeout 5]
    [--hostname NAME] [--xid 1234] [--broadcast]
    [--release-after] [--decline]
```

Default action is `obtain_lease` and printing the lease
(`ip`, `subnet_mask`, `routers`, `dns_servers`, `lease_time`,
`server_id`, one per line). `--release-after` sends RELEASE after a
successful obtain (demonstrates the page's final step without
touching the NIC). `--decline` instead runs DISCOVER and declines
the offer. Errors print to stderr with a non-zero exit code.
`--broadcast` switches the target from the given `--server` address
to `255.255.255.255`; without it the client unicasts to `--server`,
which is what loopback testing needs.

## Divergences from the page (complete list)

1. fyi slug: both plausible fyi slugs 404'd (see SPEC.md); the
   Substack #94 text (same author, same steps) is the source used.
2. One UDP socket instead of two: a single UDP socket can both send
   and receive, so a second socket adds nothing; the send+listen
   behaviour the page describes is preserved.
3. Fresh xid per exchange instead of one xid for the whole DORA
   handshake: safer against late retransmissions, still compliant.
4. No retransmission/backoff: one send + bounded wait per exchange;
   timeout is an error the caller can retry.
5. Final step "set the local IP" is print-only: the client returns
   and prints the `Lease` and can send RELEASE, but never runs OS
   commands to configure a NIC (unsafe in this environment and
   forbidden by the task). The packet-level RELEASE is implemented.
6. DHCPINFORM is not implemented (the page does not require it).
7. `sname`/`file` fields are carried as zeros and never interpreted
   (boot-file handling is outside the page's steps).

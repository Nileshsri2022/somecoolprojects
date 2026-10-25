# TEST_PLAN — DHCP Client

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No real network, no broadcast, no host-configuration change: every
network test uses a fake DHCP server (a UDP socket in a thread) bound
to `127.0.0.1` on an ephemeral port. The fake server is stopped and
joined in `tearDown`; the test process leaves no background server
behind (verified by the suite finishing and the shell returning).

## Unit tests (packet encode/decode, no sockets)

1. DISCOVER round-trip: build → bytes → decode; op/htype/hlen/xid/
   flags/chaddr/message-type survive; length is 236 + cookie +
   options + END; first option bytes are the magic cookie.
2. OFFER / ACK / NAK / DECLINE / RELEASE round-trips with their
   characteristic options (yiaddr, server id, requested IP, lease
   time, mask/router/DNS) preserved.
3. Known layout check: a hand-built packet's first bytes match the
   RFC 2131 field order (op=1, htype=1, hlen=6, hops=0, xid).
4. Malformed packets rejected: truncated (< 240 bytes), bad magic
   cookie, option length running past the end of the packet, and a
   packet with no option 53 has `message_type is None` (not a crash).
5. MAC parsing: colon, hyphen and bare-hex forms accepted and equal;
   too-short, too-long and non-hex input raise `ValueError`.
6. IP option helpers: single-IP and multi-IP options decode to
   dotted quads; lease time decodes as an unsigned 32-bit value.
7. Lease parsing: ACK → `Lease` with ip/mask/routers/DNS/lease/
   server; ACK without optional options gives None/[]; a NAK or a
   zero yiaddr passed to `Lease.from_ack` raises `ValueError`.

## Integration tests (fake server on loopback)

8. Full DORA: fake server answers DISCOVER with an OFFER
   (192.168.1.100, mask 255.255.255.0, router 192.168.1.1, DNS
   8.8.8.8, lease 3600, server 192.168.1.1) and REQUEST with an ACK;
   `obtain_lease()` returns exactly that lease.
9. NAK path: fake server answers REQUEST with NAK; `obtain_lease()`
   raises `DhcpNakError` and returns no lease.
10. Timeout path: no server listening; `discover()` raises
    `TimeoutError` within a bounded time (timeout 0.5 s in tests).
11. Wrong-xid ignored: fake server first sends an OFFER with a
    wrong xid, then the correct one; the client ignores the first
    and completes on the second (proves the xid filter, not luck).
12. RELEASE packet: after a successful obtain, `release(lease)`
    sends a packet the fake server records as message type 7 with
    ciaddr = the leased IP and server id = the lease server.
13. DECLINE packet: `decline(offer)` sends message type 4 with the
    requested-IP option equal to the offered address.
14. CLI level: `obtain` against the fake server via subprocess
    prints the leased IP; a NAK run exits non-zero with an error
    on stderr (not a lease on stdout).

## Not tested (and why)

- Real broadcast to 255.255.255.255 / port 68: needs privileges and
  a real DHCP server; excluded by the task's safety rule.
- Applying the lease to a NIC: deliberately not implemented.
- Retransmission timing: no retry loop exists to time.
- DHCPv6 / INFORM: out of scope (see DESIGN.md).

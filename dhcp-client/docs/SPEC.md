# SPEC — Build Your Own DHCP Client

Source: Coding Challenge #94 — DHCP Client, by John Crickett.
Canonical text read: https://codingchallenges.substack.com/p/coding-challenge-94-dhcp-client
(published 2025-07-19).

## Slug / 404 caveat (recorded honestly)

The task template asks for `https://codingchallenges.fyi/challenges/challenge-<slug>/`.
Two guesses were tried and both returned HTTP 404 from the text-fetch
layer, and were NOT retried unchanged:

- `challenge-dhcp-client` — 404
- `challenge-dhcp` — 404

No other fyi slug was found by web search (the fyi site's own search
results surface the DNS-resolver and other challenges, but not a DHCP
page). The Substack post above is the same challenge by the same author
(#94, same step text quoted in search results), so the build below is
from that text plus RFC 2131, which the page itself cites as the
message-format authority. If a fyi DHCP page appears later, re-check
its slug against this spec before claiming an exact match.
Reconciliation 2026-10-25: the Substack source was read directly
and its steps match this build (serialise/deserialise DISCOVER/
OFFER/REQUEST/ACK/NAK/DECLINE, two-socket concept, request, ACK/
NACK, set local IP, release). Documented divergences stand:
one socket instead of two, no retransmission loop, final IP
setting is print-only (never runs OS NIC commands).

## Goal

Build a DHCP client and use it to request an IP address from a DHCP
server, following the page's steps.

## Step 0 — Look at the local network first

Before coding, the page asks the reader to inspect their own interface
(`ipconfig` on Windows, `ip`/`ifconfig` on Linux, `networksetup` on
macOS) and note the current IPv4 address, subnet mask, gateway, DHCP
server and DNS servers. This build does not do that automatically:
the client takes a MAC address (and, for live use, a broadcast target)
as input, and prints the lease it obtains. See DESIGN.md for why
applying the lease to a real NIC is deliberately out of scope here.

## Step 1 — Serialise / deserialise DHCP messages (RFC 2131)

Message format (RFC 2131 §2), all integers big-endian:

| Field | Size | Notes |
|---|---|---|
| op | 1 | 1 = BOOTREQUEST (client), 2 = BOOTREPLY (server) |
| htype | 1 | 1 = Ethernet |
| hlen | 1 | 6 for Ethernet |
| hops | 1 | 0 from a client |
| xid | 4 | transaction ID, chosen by the client, echoed by the server |
| secs | 2 | seconds since the client started acquiring/renewing |
| flags | 2 | bit 15 = broadcast flag (0x8000) |
| ciaddr | 4 | client IP (0 in DISCOVER/REQUEST for a new lease) |
| yiaddr | 4 | "your" IP — the offered/assigned address |
| siaddr | 4 | server IP |
| giaddr | 4 | relay-agent IP (0 when no relay) |
| chaddr | 16 | client hardware address (MAC, padded with zeros) |
| sname | 64 | server host name (zeros when unused) |
| file | 128 | boot file name (zeros when unused) |
| options | variable | magic cookie `99, 130, 83, 99` first, then TLV options, then END (255) |

Fixed part is 236 bytes; options follow the cookie.

Options implemented (RFC 2132 numbers):

| Code | Name | Value |
|---|---|---|
| 0 | Pad | no length/value; skipped on decode |
| 1 | Subnet Mask | 4-byte IPv4 address |
| 3 | Router | one or more 4-byte IPv4 addresses |
| 6 | Domain Name Server | one or more 4-byte IPv4 addresses |
| 12 | Host Name | ASCII string |
| 50 | Requested IP Address | 4-byte IPv4 address |
| 51 | IP Address Lease Time | 4-byte unsigned seconds |
| 53 | DHCP Message Type | 1 byte (see below) |
| 54 | Server Identifier | 4-byte IPv4 address |
| 55 | Parameter Request List | list of option codes requested |
| 255 | End | terminates the options area |

DHCP Message Type (option 53) values:

| Value | Message |
|---|---|
| 1 | DHCPDISCOVER |
| 2 | DHCPOFFER |
| 3 | DHCPREQUEST |
| 4 | DHCPDECLINE |
| 5 | DHCPACK |
| 6 | DHCPNAK |
| 7 | DHCPRELEASE |
| 8 | DHCPINFORM |

The page requires serialising/deserialising DISCOVER, OFFER, REQUEST,
ACK, NAK and DECLINE. This build additionally supports RELEASE
(the page's final step) and INFORM is out of scope (not built).

## Step 2 — The two sockets

The page's reasoning: a client may have no IP address yet and does not
know the server's address, so it cannot open a TCP connection. It uses
UDP broadcast: send to the broadcast address on the server port, and
listen for a broadcast reply on the client port.

- DHCP server port: 67. DHCP client port: 68 (RFC 2131).
- This implementation uses a single UDP socket bound to the client
  port with `SO_BROADCAST` enabled, which is functionally the
  send+listen pair the page describes (one socket can both send and
  receive UDP; two separate sockets would only duplicate it). The
  socket is bound to a configurable client port so tests can use an
  ephemeral port instead of privileged port 68 — see DESIGN.md.
- Live broadcast use needs broadcast privileges / usually root for
  port 68, and must NOT be run against a real network in tests.

## Step 3 — Request an address, read the offer

Send DHCPDISCOVER (broadcast flag set, `ciaddr` 0, `yiaddr` 0,
parameter-request list asking for subnet mask, router, DNS and lease
time). Wait for a DHCPOFFER with the same transaction ID, then print /
log it. An offer for a different xid, or a non-OFFER message, is
ignored (with the timeout still applying).

## Step 4 — Respond to the offer, handle ACK or NAK

Send DHCPREQUEST naming the offered address (option 50) and the
offering server (option 54, the server identifier), reusing the same
transaction ID policy as the page's handshake (a fresh xid per
exchange in this implementation — see DESIGN.md). Then listen for:

- DHCPACK — the lease is confirmed; parse yiaddr, subnet mask,
  router(s), DNS server(s), lease time and server identifier.
- DHCPNAK — the request is refused; no lease is returned and the
  caller gets a clear error (the client must not use the offered
  address).

## Step 5 — Set the address, and release it

The page's final step: on ACK, set the local IP address on the NIC,
and support RELEASE (clear the address from the NIC and tell the
server the client no longer needs it), then release and request a new
one to verify.

Divergence (deliberate, documented): this build does NOT change the
host's network configuration and does NOT run `ip`/`ifconfig` to set
an address. Doing so from an unprivileged test harness would be
unsafe and is explicitly forbidden by the task (do not change the
host's network configuration). Instead, on ACK the client returns a
`Lease` object and prints it, and RELEASE sends a standards-compliant
DHCPRELEASE packet (with ciaddr = the leased address and server
identifier) without touching the NIC. The packet-level behaviour —
the part the page's earlier steps actually specify — is fully built
and tested against a fake server. See DESIGN.md "Divergences".

## Success criteria (verifiable)

1. A DISCOVER packet encodes to the RFC 2131 layout and round-trips
   through decode byte-for-byte on the fields that matter.
2. OFFER / REQUEST / ACK / NAK / DECLINE / RELEASE all encode and
   decode, including their options.
3. Against a local fake DHCP server on loopback, the client completes
   DISCOVER → OFFER → REQUEST → ACK and returns the offered lease
   (IP, mask, router, DNS, lease seconds, server id).
4. A NAK from the fake server is reported as an error, not a lease.
5. A packet with a bad magic cookie, a truncated packet, or an
   unknown message type is rejected, not silently accepted.
6. No test broadcasts on a real network or changes host configuration.

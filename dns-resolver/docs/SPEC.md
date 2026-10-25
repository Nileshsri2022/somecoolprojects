# SPEC — Build Your Own DNS Resolver

Source: https://codingchallenges.fyi/challenges/challenge-dns-resolver/
(slug: `challenge-dns-resolver`, fetched 2026-10-25; no 404, no slug correction needed.)

## Goal

Build a simple DNS resolver that turns a hostname into IP address(es),
following the challenge's four steps plus the CNAME bonus step.

## Step 1 — Build a query message (RFC 1035 §4.1.1, §4.1.2)

A DNS message has a header, a questions section, and answer, authority,
and additional sections (empty in the initial query).

Header (12 bytes, all integers big-endian):
- 2 bytes id (random; the page's example uses 22)
- 2 bytes flags — recursion-desired (RD) bit set to 1 when asking a
  resolver; see §4.1.1 for the bit layout
- 2 bytes each: QDCOUNT, ANCOUNT, NSCOUNT, ARCOUNT (1, 0, 0, 0)

Question: encoded name + 2-byte type + 2-byte class.
Name encoding: each label prefixed by its length, terminated by a zero
byte, e.g. `dns.google.com` → bytes `3dns6google3com0`.

Page's expected query bytes (id 22, RD=1, type A=1, class IN=1):

```
00160100000100000000000003646e7306676f6f676c6503636f6d0000010001
```

## Step 2 — Send the query over UDP, dump the response

Send the message via UDP to a name server (page uses Google's `8.8.8.8`,
port 53). Check the first two bytes of the response match the id sent.

Page's example response (hex):

```
00168080000100020000000003646e7306676f6f676c6503636f6d0000010001
c00c0001000100000214000408080808c00c0001000100000214000408080404
```

## Step 3 — Parse the response, extract the answers (RFC 1035 §4.1.3)

Parse header, question, answer, authority, and additional sections.
Check the QR bit (§4.1.1) is 1, indicating a response.

Resource record format: name, type, class, TTL, RDLENGTH, RDATA.
Name compression (§4.1.4): a label may be replaced by a two-byte pointer
(top two bits `11`, remaining 14 bits = offset into the message);
re-join decoded labels with `.`.

For the page's example the decoded message must have: same id, 1
question, 2 answers, 0 authorities, 0 additionals; answers named
`dns.google.com`, type 1, class 1, TTL > 0, RDATA `8.8.8.8` and
`8.8.4.4`.

Record types handled (RFC 1035 §3.2.2): A (1), NS (2), CNAME (5),
AAAA (28). Other types are preserved as raw RDATA bytes.

## Step 4 — Iterative resolution from a root server

- Set RD = 0 (flags = 0) so servers return referrals instead of
  recursing.
- Parse the response type: A (1) = answer; NS (2) = referral.
- On a referral, take the authoritative servers from the authority
  section and their IPs from the additional section (glue). If no glue
  record exists, resolve the name server's own name (see DESIGN.md).
- Start at a root server — the page suggests `198.41.0.4` — and repeat
  until an answer is received. Expected trace shape (page example):

```
Querying 198.41.0.4 for dns.google.com
Querying 192.12.94.30 for dns.google.com
Querying 216.239.34.10 for dns.google.com
'8.8.8.8'
```

## Bonus — CNAME

Follow CNAME records: when an answer is a CNAME, resolve its target
name (same query type, new query) and return the final addresses.

## Out of scope (not on the page)

No caching, no TCP fallback, no DNSSEC, no EDNS, no search domains.

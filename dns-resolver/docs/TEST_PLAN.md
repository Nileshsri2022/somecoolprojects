# TEST_PLAN — DNS Resolver

Run: `python3 -m unittest discover -s tests -v` from
`~/workspace/somecoolprojects/dns-resolver/`.

No test contacts a public DNS server. All network tests use a fake UDP
DNS server bound to `127.0.0.1` on an ephemeral port (port 0), run in a
background thread and shut down in `tearDown`. The fake server builds
responses with the same library under test for message framing, except
for the page-example test, which parses the page's literal hex bytes.

Sandbox note (verified 2026-10-25): unconnected UDP `sendto` is blocked
here (`PermissionError`), so both the tool and the fake server use
connected UDP. The fake server replies from its own socket and then
rebinds a fresh socket on the same port, because a socket left
connected to one client would drop the next query (new source port).

## Cases

Encoding (Step 1):
- `encode_name("dns.google.com")` == `3dns6google3com0` (page example).
- Query with id 22, RD=1, type A, class IN for `dns.google.com`
  encodes to exactly the page's hex:
  `00160100000100000000000003646e7306676f6f676c6503636f6d0000010001`.
- Root name `.` encodes to a single zero byte; label > 63 bytes rejected.
- Flags: RD=1 gives `0x0100`; RD=0 gives `0x0000`.

Decoding (Steps 2–3):
- The page's Step 2 example response hex parses to: id 22, QR set,
  1 question (`dns.google.com`, A, IN), 2 answers (A, IN, TTL 532,
  `8.8.8.8` and `8.8.4.4`), 0 authorities/additionals.
- Compressed names: an answer name that is a `0xC00C` pointer to the
  question name decodes to the question name, and parsing continues
  at the correct offset (a following record still parses).
- Pointer loop / pointer out of bounds raises `ValueError`.
- Round-trip: a message with A, AAAA, NS, CNAME, and an unknown-type
  record encodes and decodes to identical values.
- Truncated message raises `ValueError`.

Network, fake server (Steps 2–4, bonus):
- Recursive query to the fake server returns its canned A answers,
  and the fake server sees RD=1.
- ID mismatch in a reply raises `DNSError`; RCODE != 0 raises
  `DNSError`; no reply within the timeout raises `DNSError`.
- Iterative resolution: fake server answers the first query with an
  NS referral (authority NS + glue A pointing at itself) and the
  second query with an A answer; the resolver follows the referral
  and returns the A record. (Port override per DESIGN divergence 1.)
- CNAME bonus: fake server answers with a CNAME, then with an A for
  the target; the resolver returns the final A record.
- CLI: `dns_resolver.py example.com --server 127.0.0.1 --port <fake>`
  prints the A record; unknown type / missing hostname exits non-zero.

## Success criteria

All tests pass; no test depends on external network access.

Note (2026-10-25): `send_query` retries a query up to 3 times on
`ConnectionRefusedError`. A connected UDP socket surfaces a transient
ICMP port-unreachable this way when the local fake server's reader is
not yet scheduled; without the retry the network tests failed about
half of runs. After the fix, 8 consecutive full-suite runs pass.

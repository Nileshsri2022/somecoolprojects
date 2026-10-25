# TEST_PLAN — dns-forwarder

Suite: `tests/test_dns_forwarder.py`, run with:

```sh
python3 -m unittest discover -s tests -v
```

from `dns-forwarder/`. Python 3 standard library `unittest` only.

## Ground rules (same as previous waves)

- Tests use LOCAL fake upstream DNS servers bound to ephemeral ports
  (port 0, OS-assigned) on `127.0.0.1` only. No public DNS server
  (including 8.8.8.8) is contacted by any test.
- Every fake server runs in a daemon thread and is shut down in
  `tearDown` (socket closed, thread joined with a timeout); the
  forwarder under test is likewise stopped and its thread joined.
  No stray servers are left running.
- The forwarder is exercised end-to-end over real UDP sockets, not
  just via function calls, for every forwarding/caching test.

## Coverage map

Unit — wire format (Step 2):

1. `encode_name("dns.google.com")` produces exactly
   `3dns6google3com0` (the page's example bytes).
2. Name decoding: plain labels, root name, and compression pointers
   (including a pointer into the question section, as real upstream
   responses do).
3. Pointer loops are rejected (`ValueError`) instead of looping.
4. Header + question round-trip: build a query, parse it back, fields
   equal (id, flags, counts, name, type, class).
5. Answer record round-trip: A record (type 1) and AAAA record
   (type 28) parse to the right rdata text and TTL.
6. Short packet (< 12 bytes) raises `ValueError`; truncated question
   raises `ValueError`.

Unit — cache (Step 5):

7. Put then get returns the answers with unchanged TTLs at once.
8. Get after the TTL has elapsed (injectable fake clock) returns
   `None` (expired entry is a miss).
9. TTLs are decremented by elapsed time on a hit.
10. An entry whose one record expired while another is still valid is
    a miss as a whole (answer-set expiry rule).
11. Different qname / qtype / qclass keys do not collide.
12. The 1024-entry cap evicts the oldest entry.

Integration — forwarding and caching over UDP (Steps 1, 3, 4, 5):

13. Forward: a client query to the forwarder reaches the fake
    upstream (counted) and the client receives the upstream's A
    answer, with the client's own transaction id.
14. Cache hit: a second identical query is answered without any
    second upstream query (upstream count stays 1).
15. TTL expiry: upstream TTL = 1; after sleeping past it, the next
    identical query is forwarded again (upstream count becomes 2).
16. Cache isolation: a different name, and a different qtype for the
    same name, each trigger their own upstream query.
17. NXDOMAIN is forwarded to the client but NOT cached: repeating it
    queries upstream again.
18. Upstream timeout: fake upstream that never replies + short
    `--timeout` yields a SERVFAIL (rcode 2) reply to the client,
    and the server stays alive for the next query.
19. Malformed packet does not kill the server: garbage sent to the
    forwarder, then a valid query still gets a forwarded answer.
20. AAAA forwarding: an AAAA query is forwarded and its answer
    returned and cached.
21. `--no-cache` mode: repeated identical queries each reach
    upstream (used to demonstrate Step 4 without Step 5).

## What is NOT tested live (honest gaps)

- Port 53 binding (needs privileges) and serving a real LAN.
- A real upstream at 8.8.8.8:53, or any real public DNS traffic.
- `dig` output shape: `dig` may not be installed in this sandbox;
  the tests use raw UDP clients that check the same wire fields
  `dig` would display (id, flags, question, answers, TTL).
- Concurrency: the server is serial by design, so no concurrent-
  client test is claimed.

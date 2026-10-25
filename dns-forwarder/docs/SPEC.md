# SPEC — Build Your Own DNS Forwarder

Source challenge page (resolved first, before any code was written):

- https://codingchallenges.fyi/challenges/challenge-dns-forwarder/
- Found via the site's tag pages / web search for "codingchallenges.fyi
  DNS forwarder". The page was read in full on 2026-10-25. It is a live
  page, not a 404.
- Tags on the page's tag listings: intermediate, networking (also listed
  under system programming in the assignment; the page itself is reached
  from the networking/intermediate tag pages).

Summary of the page, in its own terms: a DNS Forwarder is a nameserver
that resolves DNS queries instead of directly using the authoritative
nameserver chain. It typically sits on the edge of a local area network,
reducing external traffic and speeding up access by serving answers from
a local cache.

## Challenge steps (as written on the page)

### Step Zero — environment setup

Choose platform, editor and language. The work involves creating,
sending and receiving UDP packets. Implemented here in Python 3
standard library only.

### Step 1 — UDP server on a specified port

Create a UDP server listening on a specified port. It should use port 53
if no port is provided, otherwise the provided port (command-line option).
The page notes testing uses a port above 1023, as many OSs do not allow
non-privileged users to use a port below 1023.

Implemented: `--port` (default 53), `--bind` (default `127.0.0.1`, see
divergences). On receiving a datagram the server logs `MSG received`
in verbose mode, matching the page's example output.

### Step 2 — parse the request packet

A DNS message has a header, questions, answers, authority and additional
sections. Header per RFC 1035 Section 4.1.1; question per Section 4.1.2;
answer/authority/additional record format per Section 4.1.3. A question
has a name (encoded label sequence, e.g. `dns.google.com` encodes as
`3dns6google3com0`), a record type and a class.

Implemented: full header/question/record parsing, including name
compression pointers (`0xC0xx`) in responses, and a human-readable print
of the parsed message in verbose mode, in the page's shape:

```
Header - id:40500 flags:288 questions:1 answers:0 authorities:0 additionals:1
Questions - name:www.google.com type:1 class:1
Answers: Empty
Authorities: Empty
```

The page suggests test-driven development for serialise/deserialise
code; the test suite covers exactly that (see `docs/TEST_PLAN.md`).

### Step 3 — forward the request to a DNS server

Forward the request to a DNS server to actually resolve it. The page
uses Google's public DNS server as the example (`8.8.8.8`, port 53).
The forwarder receives a request, unpacks it, re-packs it and sends it
to `8.8.8.8` port 53. For this step it is enough to print that it was
forwarded.

Implemented: the query is re-packed (new upstream transaction id, same
question) and sent to the configured upstream; verbose mode prints
`Forwarded Question`. Default upstream is `8.8.8.8:53`, exactly as the
page specifies; `--upstream` / `--upstream-port` override it (required
for testing against a local fake upstream, and for any network where
8.8.8.8 is not reachable).

### Step 4 — return the answer to the original client

Receive an answer from the DNS server, unpack it, and forward it to the
original client. This requires keeping a record of which client asked
which question, then looking the answer up and sending it to that client.

Implemented: each forwarded query is tracked by its upstream
transaction id, mapping back to the client's address and transaction
id. The upstream response's id is rewritten to the client's id before
it is sent back, so the client sees the id it sent. The page's Step 4
`dig` example (answer `www.google.com. 118 IN A 142.250.179.228`, plus
an EDNS OPT pseudo-section) is the shape of a forwarded answer; OPT
records in upstream responses are passed through verbatim on the
forwarded path (they are not served from cache — see divergences).

### Step 5 — cache successful resolutions within their TTL

Cache the results of successful DNS resolution and respond to future
requests with the same question from the local cache. The cached value
must only be served while still within the TTL provided in the answer
section; otherwise a new lookup is done. The page's closing test is
that the server only forwards requests that are not cached or whose
TTL has expired.

Implemented: successful (NOERROR, at least one answer record) responses
are cached under `(qname, qtype, qclass)`. A cache hit rebuilds a
response with each answer's TTL reduced by the time already elapsed;
if every/any answer's TTL has expired the entry is treated as a miss
and the query is forwarded again. Error responses are not cached (see
divergences).

## Deliberate divergences from the page

1. **Default bind address is `127.0.0.1`, not all interfaces.** The
   page's example queries `127.0.0.1`. Binding only loopback by default
   is safer; `--bind 0.0.0.0` serves a LAN. Serving a real LAN was NOT
   verified live here (see scope limits).
2. **Single-threaded, serial request handling.** The page does not
   require concurrency. The server handles one client query at a time:
   forward, wait for the upstream reply (or `--timeout`, default 5 s),
   reply, then take the next query. Concurrent clients are served in
   turn, not in parallel, and a slow upstream blocks later queries
   until it times out.
3. **Upstream transaction ids are remapped.** The page says "sending
   the same request"; the question section is sent unchanged, but the
   header id is replaced with a fresh upstream id so replies can be
   matched to the right client even if two clients coincidentally use
   the same id. The client always sees its own original id back.
4. **Cache stores answer records only.** On a cache hit the response
   contains the question and the cached answers (with decremented
   TTLs); authority and additional sections from the upstream reply
   (including EDNS OPT) are not re-served from cache. The forwarded
   (non-cached) path passes the upstream response through in full.
5. **Only NOERROR responses with at least one answer are cached.**
   NXDOMAIN / SERVFAIL / empty NOERROR responses are forwarded but
   not cached, so a later retry re-queries upstream. The page says
   "successful DNS resolution"; caching negative answers would need a
   separate (SOA-derived) TTL policy the page does not specify.
6. **Cache key includes class as well as name and type.** Two queries
   differing only in class are different questions under RFC 1035.
7. **Multi-question queries are forwarded but not cached.** DNS
   clients in practice send one question; caching a multi-question
   response under a single key would be incorrect.
8. **Malformed packets:** a datagram shorter than the 12-byte header is
   ignored; a packet whose header parses but whose question does not
   gets a FORMERR response (rcode 1) with the question section
   omitted, rather than crashing the server. The page does not specify
   this behaviour.
9. **Upstream timeout produces SERVFAIL (rcode 2)** to the client,
   with the original question echoed. The page does not specify a
   timeout behaviour; silently dropping the query would leave `dig`
   hanging until its own timeout.
10. **Cache size cap:** at most 1024 entries; when full, the oldest
    entry is evicted. The page specifies no cap.

## NOT built / NOT verified

- Binding port 53 and serving a real LAN: privilege- and
  network-position-dependent, NOT verified live in this sandbox. The
  tested path is ephemeral ports against local fake upstream servers.
  Port 53 remains the default when no `--port` is given, per Step 1.
- No live query to `8.8.8.8` was made or verified from this sandbox;
  the default upstream is implemented exactly as the page specifies
  but exercised only via the `--upstream` override in tests.
- No recursion: this forwarder never walks the authoritative chain
  itself. That is the point of the challenge and what distinguishes
  it from the sibling `dns-resolver` project, which resolves
  iteratively from root servers. If the configured upstream refuses
  recursion, this forwarder cannot resolve on its own.
- No TCP DNS, no DNSSEC validation, no zone files / authoritative
  answers, no access control or rate limiting, no persistent cache
  (cache lives only for the process lifetime).
- No support for `dig`-style EDNS negotiation beyond passing OPT
  records through on the forwarded path.

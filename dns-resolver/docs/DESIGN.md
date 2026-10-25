# DESIGN — DNS Resolver

Python 3 standard library only. Single file: `dns_resolver.py`.

## Assumptions

- Only the wire format of RFC 1035 §4.1 is implemented; no other RFCs.
- Network byte order (big-endian) throughout, via `struct`.
- UDP only; a response that does not fit is out of scope (page uses UDP).
- The tool is a resolver *client*: it queries servers, it does not serve.
- Hostnames are ASCII; labels are at most 63 bytes (enforced on encode).
- A trailing dot on input (`example.com.`) is stripped before encoding.

## Data model

- `Header`: id, flags, qdcount, ancount, nscount, arcount.
  Flag helpers: `flags_for_query(recursion_desired)` builds the flags
  word (only RD is ever set by us); `is_response` checks the QR bit.
- `Question`: name, qtype, qclass.
- `ResourceRecord`: name, rtype, rclass, ttl, rdata. `rdata` is the
  decoded value: dotted-quad string for A, IPv6 string for AAAA,
  domain name string for NS/CNAME, raw `bytes` for anything else.
- `Message`: header + lists of questions/answers/authorities/additionals,
  with `to_bytes()` and `Message.from_bytes()`.

## Encoding

- `encode_name(name)`: labels length-prefixed, zero-terminated.
- `encode_question` / record encoding: straightforward struct packing.
- We never emit compression pointers in queries (not needed; the page's
  example query has none). Compression is only *decoded*.

## Decoding

- `decode_name(data, offset)`: follows labels and `0xC0` pointers,
  returning `(name, next_offset)` where `next_offset` is the position
  after the name *in the original stream* (i.e. just past the pointer
  when a pointer was used). Guarded against pointer loops: at most 128
  jumps, each pointer target must be inside the message, else
  `ValueError`.
- RDATA decoding is type-driven: A → 4 bytes to dotted quad (via
  `socket.inet_ntoa`); AAAA → 16 bytes to IPv6 string; NS/CNAME →
  `decode_name` (may itself be compressed); otherwise raw bytes.
- `Message.from_bytes` verifies the buffer is at least 12 bytes, checks
  counts against remaining data implicitly by failing on truncation
  (`struct.error` / `IndexError` surfaced as `ValueError`).

## Querying

- `send_query(server, name, qtype, port=53, timeout=5,
  recursion_desired=True) -> Message`: builds a query with a random
  16-bit id, sends it over one UDP socket, waits for a reply, and
  validates: reply id == query id, QR bit set, RCODE == 0
  (non-zero RCODE raises `DNSError` naming the code). A socket timeout
  raises `DNSError("timed out")`.
  Implementation note: the socket is *connected* (`connect` + `send` /
  `recv`) rather than `sendto` / `recvfrom`. The two are equivalent
  for a single query/response exchange; connected UDP is used because
  this sandbox blocks unconnected UDP `sendto` with `PermissionError`
  (verified 2026-10-25), while connected UDP works.
- `resolve_recursive(server, name, ...)` (Step 2/3 path): one query
  with RD=1; returns the A (or requested-type) answer values, following
  a CNAME answer by re-querying the target name (bonus step).
- `resolve_iterative(name, root_server="198.41.0.4", ...)`: Step 4.
  Loop (max 30 hops): query current server with RD=0.
  - If answers contain the requested type → return them (CNAME in
    answers restarts the loop at the CNAME target, still from the root,
    like a fresh iterative resolution).
  - Else if authority NS records exist: pick the first NS; use its glue
    A record from the additionals if present; otherwise resolve the NS
    name with a single recursive query to `recursive_server`
    (default `8.8.8.8`) — this is the page's "query a name server to
    resolve the IP address of the name server" step.
  - Else raise `DNSError` (dead end: no answer, no referral).
  Each hop prints `Querying <server> for <name>` to stdout, matching
  the page's trace format.

## CLI

```
python3 dns_resolver.py <hostname> [--server IP] [--port N]
    [--type A|AAAA|NS|CNAME] [--iterative] [--root IP]
    [--recursive-server IP] [--timeout SECONDS]
```

- Default mode: recursive query to `--server` (default `8.8.8.8`).
- `--iterative`: iterative resolution from `--root` (default
  `198.41.0.4`); `--recursive-server` supplies glue-less NS lookups.
- The final answer list prints one value per line (page prints a
  quoted list; one-per-line is simpler and script-friendly — see
  divergences in README).
- Errors go to stderr with a non-zero exit code.

## Divergences from the page (also listed in README)

1. `--port` applies to every hop of iterative resolution, not just the
   first query. Real DNS always uses port 53; the override exists so
   iterative resolution can be tested against a local fake server on
   an ephemeral port. Default is 53, so real-world behaviour is exact.
2. Glue-less NS lookup uses a recursive query to `--recursive-server`
   instead of a fully iterative resolution of the NS name. Simpler, and
   it is what the page describes ("query a name server to resolve the
   IP address of the name server").
3. Output is one answer per line rather than the page's quoted-list
   repr, for scriptability.

# DESIGN — dns-forwarder

Single file: `dns_forwarder.py`, Python 3 standard library only
(`socket`, `struct`, `sys`, `time`, `argparse`, `select` is not needed;
see below). No third-party DNS library.

## Message model (RFC 1035 §4.1.1–§4.1.3)

- `Header`: id, flags, qdcount, ancount, nscount, arcount.
  Flag helpers: `QR`, `RD`, `RA`, `RCODE` masks. Flags are handled as
  a raw 16-bit value and copied where appropriate, never re-derived
  from scratch on the forwarded path.
- `Question`: name (dotted string, case preserved as sent, compared
  lower-cased for cache keys), qtype, qclass.
- `Record`: name, rtype, rclass, ttl, rdata (raw bytes). A/AAAA rdata
  is decoded to dotted/colon text only for verbose display; the wire
  bytes are always what is forwarded or cached, so unknown record
  types pass through untouched.
- `Message`: header + lists of questions, answers, authorities,
  additionals.

Parsing:

- `parse_name(data, offset)` walks labels, following compression
  pointers (`0xC0` + offset byte) with a visited-offset guard against
  pointer loops, and returns `(dotted_name, next_offset)`. The root
  name is `""` rendered as `"."` only in display.
- `parse_message(data)` requires at least 12 bytes, unpacks the header
  with `struct "!HHHHHH"`, then parses each section in order. A short
  or corrupt section raises `ValueError`; callers decide between
  ignoring the packet and answering FORMERR.
- `encode_name(name)` emits length-prefixed labels + zero terminator.
  Encoders never emit compression pointers; that keeps cache-hit
  responses simple and always valid, at the cost of a few bytes.

Serialisation:

- `build_query(qname, qtype, qclass, tx_id)` — header flags `RD=1`,
  one question.
- `build_response(query, answers, ...)` — used for cache hits,
  FORMERR and SERVFAIL replies: id from the client query, `QR=1`,
  `RA=1`, `RD` copied from the query, rcode as specified.
- The forwarded path does NOT rebuild the whole message: it copies
  the client's wire bytes, patches only the 2-byte transaction id,
  and sends that. This preserves EDNS OPT, multiple questions and any
  other section bytes exactly, which a rebuild could mangle.

## Forwarding flow (serial, single-threaded)

```
recvfrom(listen_sock) -> data, client_addr
  log "MSG received" (verbose)
  parse -> on failure: ignore (<12 bytes) or FORMERR reply
  log human-readable header/questions (verbose)
  key = (qname.lower(), qtype, qclass)   [first question only]
  if single-question and cache.get(key) is not None:
      log "Cache hit"; send build_response(...) to client; continue
  log "Cache miss" / "Forwarded Question" (verbose)
  upstream_id = fresh id (monotonic counter, avoids reuse while a
      query is in flight); pending[upstream_id] = (client_addr, client_id, key)
  send patched query to upstream via a second UDP socket
  recvfrom(upstream_sock, timeout) -> response bytes
      on timeout: drop pending entry; send SERVFAIL reply to client
      on reply: parse; if NOERROR and >= 1 answer and single question:
          cache.put(key, answers, now)
      rewrite response id to client_id; sendto(client_addr)
```

Why one upstream socket and a blocking wait instead of a selector
loop: the server is serial by design (divergence 2 in SPEC.md), so
there is at most one outstanding upstream query at any time and no
demultiplexing is needed. The pending dict exists to document the
Step 4 mapping (client <-> question) and to make the id rewrite
explicit; it never holds more than one entry in this design.

Transaction ids: a counter starting from a time-derived seed,
incremented per forwarded query, masked to 16 bits. This avoids
colliding with a client's id and avoids reusing an id while its
query is in flight (there is only ever one in flight).

## Cache

- `DnsCache`: dict `key -> (stored_monotonic_time, [Record, ...])`
  plus insertion order for eviction. `get(key, now)` returns a list of
  `Record` copies with `ttl` replaced by `max(0, ttl - elapsed)`;
  returns `None` if the key is absent or if any answer's remaining
  TTL is 0 (whole-entry expiry: an answer set is served only while
  every record in it is still valid, matching the page's "only served
  if still within the TTL" rule for the answer section as a unit).
- `put` caps at 1024 entries, evicting the oldest inserted entry.
- Time source is `time.monotonic` by default and injectable
  (`DnsCache(time_fn=...)`) so TTL logic is unit-testable without
  real sleeps; the server itself uses the real clock.
- Cache lookup happens before forwarding and only for single-question
  queries; a hit never touches the upstream socket.

## CLI

```
python3 dns_forwarder.py [--bind HOST] [--port PORT]
                         [--upstream HOST] [--upstream-port PORT]
                         [--timeout SECS] [--no-cache] [--verbose]
```

Defaults: bind `127.0.0.1`, port `53` (Step 1), upstream `8.8.8.8`,
upstream-port `53` (Step 3), timeout `5.0`. `--no-cache` disables
both cache reads and writes (useful to demonstrate Step 4 alone).
`Ctrl-C` (KeyboardInterrupt) exits cleanly with both sockets closed.

## Sending replies: sendto() vs the connect-send-rebind fallback

The normal reply path is `listen_sock.sendto(data, client_addr)`,
which is also what keeps the reply's source port equal to the port
the client queried (a connected client drops replies from any other
port). The sandbox this was developed in blocks unconnected UDP
`sendto()` with EPERM while allowing `send()` on a connected UDP
socket, so `_send` falls back, only when `sendto()` raises, to:
connect the listening socket to the client, `send()`, then swap in a
fresh socket bound to the same port for the next query. The old
socket is closed BEFORE the fresh one binds, deliberately: binding
first (with `SO_REUSEPORT`) was tried and caused real silent losses
— a query arriving while both sockets were bound could be
load-balanced into the old socket's queue and dropped when it closed
(reproduced ~2 in 15 runs of a back-to-back query loop, upstream
count 0, both threads alive). With close-then-bind, a query arriving
in the tiny unbound window instead gets an ICMP port-unreachable,
which a connected client surfaces as `ConnectionRefusedError`.
Worse, the sandbox also SILENTLY drops a datagram sent immediately
after a socket swap (reproduced in isolation: server alive and
blocked in recvfrom on the correctly-bound port, datagram simply
never arriving — no ICMP, so no refused error). The harness therefore
retries a query up to 3 attempts on BOTH refused errors and timeouts,
with the same transaction id. That retry is safe for the count
assertions: every observed loss was on a query leg (the failed query
never reached the upstream, so retrying does not double-count it); a
reply-leg loss on a forwarded query WOULD double-count and fail
loudly, as it should. A genuine hang still fails, after 3 attempts.
With the retry in place, a 30-iteration back-to-back loop that failed
9/30 passes 30/30. On a normal machine the fallback never runs. The
upstream socket is connected once at startup (there is exactly one
upstream), so it needs no such dance. Tests use connected client
sockets and the same trick in the fake upstream (which stays
connected to its single peer after the first query).

A second sandbox trap, found while debugging the above: calling
`connect()` on an ALREADY-connected UDP socket (even to the same
peer) breaks the next reply deterministically in this sandbox
(reproduced in isolation: fails at the second exchange, every time),
while connect-once works 50/50. Nothing in the forwarder or the fake
upstream re-connects a connected socket — each socket is connected at
most once — but any future change must preserve that invariant.

## What is deliberately not in the design

- No threads, no asyncio: serial handling is sufficient for the
  challenge and keeps the client<->upstream mapping trivially correct.
- No TCP fallback on truncated (TC bit) responses: the page is UDP
  throughout; a truncated response is forwarded as-is and the client
  may retry over TCP itself.
- No config file, no daemonisation, no logging framework: `print`
  to stdout in verbose mode only, so quiet mode stays silent except
  for startup errors.

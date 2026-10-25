# TEST_PLAN — Redis Server

Runner: `python3 -m unittest discover -s tests -v` from
`redis-server/` (also runnable as `python3 -m unittest discover -s
redis-server/tests -t redis-server` from the repo root — see README).
Tests use only the standard library. The live-server tests start the
real server on an **ephemeral port** (`port=0`, read back from
`server.server_address`); no hard-coded ports, so tests never clash
with a real Redis on 6379. The raw-socket client in the tests encodes
commands as RESP Arrays of Bulk Strings and decodes replies with the
server's own `parse_one` — plus a few hand-built raw byte strings for
the parser tests, so the codec is also checked against literals from
the challenge page.

## Parser unit tests (Step 1)

- Every example from the page, decoded exactly:
  `$-1\r\n` → None; `*1\r\n$4\r\nping\r\n` → `[b'ping']`;
  `*2\r\n$4\r\necho\r\n$11\r\nhello world\r\n` → `[b'echo', b'hello world']`;
  `*2\r\n$3\r\nget\r\n$3\r\nkey\r\n` → `[b'get', b'key']`;
  `+OK\r\n` → SimpleString("OK"); `-Error message\r\n` →
  Error("Error message"); `$0\r\n\r\n` → `b''`; `+hello world\r\n` →
  SimpleString("hello world").
- Encoder round-trips: encode then parse returns the original value
  (simple strings, errors, integers incl. negatives, bulk strings incl.
  empty, arrays incl. nested, None).
- Invalid inputs raise `RespError`: bad prefix byte, truncated length
  line, bulk length mismatch (payload not followed by CRLF), negative
  lengths other than -1, non-numeric integer/length.
- Partial inputs raise `NeedMoreData` (not an error): truncated bulk
  payload, truncated array, missing CRLF.

## Live-server tests (Steps 2–6)

- PING → `+PONG`; `PING hello` → Bulk String `hello`; lower-case
  `ping` works (case-insensitivity).
- ECHO → its argument verbatim, including spaces.
- SET → `+OK`; GET returns the value; GET of a missing key → Null;
  SET overwrites; empty-string value round-trips.
- SET expiry: `EX 1` (gone after ~1.2 s), `PX 200` (gone after ~0.35 s),
  `EXAT` (future Unix time, present then gone), `PXAT` (same in ms),
  expired key counts as missing for GET and EXISTS.
- SET with an unknown option, two expiry options, or a non-numeric
  expiry value → Error reply; the key is not set.
- EXISTS: 0/1/multiple, expired keys not counted.
- DEL: deletes existing keys, returns count, deleting a missing key
  returns 0 and is not an error.
- INCR/DECR: missing key → 1 / -1; existing integer increments /
  decrements; non-integer value → Error and value unchanged; 64-bit
  overflow → Error.
- LPUSH/RPUSH: return the new length; LRANGE verifies order
  (`LPUSH k a b c` → `c b a`; `RPUSH k a b c` → `a b c`);
  negative LRANGE indices; pushing onto a string key → WRONGTYPE;
  GET on a list key → WRONGTYPE.
- Errors: unknown command → Error; wrong argument count (e.g. bare
  `GET`, bare `SET`) → Error; the connection stays usable after an
  error reply.
- Pipelining: two commands sent in a single TCP write both answered.
- Concurrency (Step 4): 10 threads × 50 SET/GET pairs each on separate
  connections, all values correct afterwards; plus 5 threads hammering
  INCR on one key, final value exactly 5 × per-thread count.
- SAVE/load (Step 6): SET string + list keys, SAVE → `+OK`, shut the
  server down, start a new server on the same dump file, GET/LRANGE
  return the saved values; an already-expired key is not resurrected.

## Not tested

- Step 7 benchmarking against real Redis (no real Redis here; see SPEC).
- RDB-format compatibility (deliberately not implemented; see SPEC).
- Performance numbers; only correctness under concurrency.

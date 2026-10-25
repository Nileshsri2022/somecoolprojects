# SPEC — Build Your Own Redis Server (Coding Challenges #8)

Source: https://codingchallenges.fyi/challenges/challenge-redis/
(verified live 2026-10-25; the URL in the task works as given, no slug correction needed.)

## Goal

Build a lite Redis: an in-memory dictionary server speaking the Redis
Serialisation Protocol (RESP), covering the functionality of the first
actual version of Redis.

## Challenge steps (from the page)

- **Step 0** — Set up the environment; a real Redis CLI may be used as a
  test client. (This build uses raw-socket tests instead, so no Redis
  install is required.)
- **Step 1** — Serialise and de-serialise RESP messages. Clients send
  commands as a RESP Array of Bulk Strings; the server replies with one
  of the RESP types. Test messages from the page:
  `$-1\r\n`, `*1\r\n$4\r\nping\r\n`, `*2\r\n$4\r\necho\r\n$11\r\nhello world\r\n`,
  `*2\r\n$3\r\nget\r\n$3\r\nkey\r\n`, `+OK\r\n`, `-Error message\r\n`,
  `$0\r\n\r\n`, `+hello world\r\n`, plus invalid cases.
- **Step 2** — Server listening on port `6379` (default; tests use an
  ephemeral port). Implement `PING` (→ `PONG`) and `ECHO` (→ its argument).
- **Step 3** — `SET` (simplest form first: `SET key value` → `OK`) and
  `GET` (→ the value, or null for a missing key), with results serialised
  per RESP.
- **Step 4** — Handle multiple concurrent clients (one thread per client
  here). Must survive a `redis-benchmark`-style concurrent SET/GET load
  without crashing; performance is not the goal.
- **Step 5** — Extend `SET` with expiry options `EX` (seconds), `PX`
  (milliseconds), `EXAT` (Unix seconds), `PXAT` (Unix milliseconds).
  (The page prints "EAXT" once; that is a typo for `EXAT`.) Expiry must
  be cheap: lazy expiry on access (constant time per key) is used here.
- **Step 6** — `EXISTS`, `DEL`, `INCR`, `DECR`, `LPUSH`, `RPUSH`, `SAVE`
  (plus load on startup).
- **Step 7** — Benchmark GET/SET performance against real Redis.
  (Not reproduced here: no real Redis install in this environment, and
  the page itself says not to focus on performance. Concurrency under
  load is covered by tests instead.)

## RESP (as described on the page)

First byte determines the type:

| First byte | Type |
| --- | --- |
| `+` | Simple String |
| `-` | Error |
| `:` | Integer |
| `$` | Bulk String |
| `*` | Array |

- Bulk Strings: `$<length>\r\n<bytes>\r\n`; `$-1\r\n` is Null.
- Arrays: `*<count>\r\n<elements...>`; `*-1\r\n` is Null.
- Simple Strings, Errors, Integers: `<prefix><payload>\r\n`.
- A command from a client is an Array of Bulk Strings; the first element
  is the command name, the rest are its arguments.

## Command behaviour (Redis semantics, per the linked command docs)

- Command names are case-insensitive. All replies follow RESP.
- `PING [message]` → `+PONG`, or the message as a Bulk String if given.
- `ECHO message` → the message as a Bulk String.
- `SET key value [EX seconds | PX ms | EXAT unix-seconds | PXAT unix-ms]`
  → `+OK`. At most one expiry option; an unknown option is a syntax
  error. Setting a key replaces any previous value (string or list) and
  clears its old expiry unless a new one is given.
- `GET key` → Bulk String value, or Null if missing or expired.
  `GET` on a list key is a `WRONGTYPE` error.
- `EXISTS key [key ...]` → Integer count of existing (unexpired) keys.
- `DEL key [key ...]` → Integer count of keys actually deleted.
- `INCR key` / `DECR key` → Integer. A missing key starts at 0. A value
  that is not an integer (or out of the signed 64-bit range) is an error:
  `ERR value is not an integer or out of range`.
- `LPUSH key element [element ...]` → Integer list length after the
  push. Elements are inserted at the head, so `LPUSH k a b c` yields
  `c, b, a`. `RPUSH` inserts at the tail, so `RPUSH k a b c` yields
  `a, b, c`. Pushing onto a string key is a `WRONGTYPE` error.
- `SAVE` → `+OK` after writing the database state to disk; the server
  also loads that file on startup if present.
- Unknown commands → `ERR unknown command '<name>'`.
  Wrong argument counts → `ERR wrong number of arguments for
  '<name>' command`.

## Deliberate divergences from the page

1. **`SAVE` file format is not RDB.** Real Redis writes a binary RDB
   file; this build writes a JSON snapshot (base64-encoded values) to
   the dump file (default `dump.rdb` in the working directory). The
   file is loadable by this server only, not by real Redis. Implementing
   the real RDB format would be a large speculative addition for a lite
   clone; the page only requires "save the database state to disk".
2. **`LRANGE` is added** although the page does not list it. Without it
   there is no way to observe list contents (LPUSH/RPUSH only return a
   length), so list ordering could not be tested. `LRANGE key start
   stop` follows Redis semantics, including negative indices.
3. **No `NX`/`XX`/`GET`/`KEEPTTL` SET options.** The page's Step 5
   requires only the four expiry options; the others are omitted.
4. **Expiry is lazy only.** No background active-expiry sweep: expired
   keys are removed when accessed (GET/EXISTS/DEL/INCR/DECR/list ops)
   or overwritten. This keeps expiry constant-time per the page's hint
   and is behaviourally identical for all commands; an expired key that
   is never touched simply stays in memory until touched.
5. **Default bind is `127.0.0.1`, not `0.0.0.0`.** Port default is
   `6379` as specified. `--host` overrides the bind address.
6. **Step 7 benchmarking against real Redis is not performed** (see
   Step 7 note above).

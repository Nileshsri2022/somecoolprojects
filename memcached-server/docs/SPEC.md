# SPEC — Memcached Server (Coding Challenges #17)

Source: https://codingchallenges.fyi/challenges/challenge-memcached/
(read 2026-10-25; the build below follows this page's steps, not a memorised
Memcached feature list.)

## Overview

A single-node, in-memory key-value cache speaking the Memcached text
protocol over TCP. One server, no sharding, no communication with other
servers. Data lives only in RAM; a restart loses everything.

## Step 1 — Startup and listening

- Default port 11211; `-p <port>` overrides it.
- Bind to 127.0.0.1 (loopback) only.
- Accept TCP connections and read the incoming data.
- Usage: `python3 memcached_server.py` or `python3 memcached_server.py -p 9999`.

## Step 2 — set and get (text protocol)

Storage command line:

```
<command> <key> <flags> <exptime> <bytes> [noreply]\r\n
<data block>\r\n
```

- `flags`: arbitrary 16-bit unsigned integer, decimal. Stored with the
  value and returned on retrieval.
- `bytes`: number of bytes in the data block, NOT including the trailing
  `\r\n`. May be zero (followed by an empty data block).
- `noreply`: optional; when present the server sends no reply for that
  command.
- The data block is opaque bytes: it may contain any bytes except that
  its length is fixed by `bytes`, so embedded `\r\n` inside the block is
  fine and must not terminate the value early.

Examples from the page:

```
set test 0 0 4\r\n1234\r\n        -> STORED\r\n
get test\r\n                       -> VALUE test 0 4\r\n1234\r\nEND\r\n
set test2 1 0 7 noreply\r\ntesting\r\n  -> (no reply)
get test2\r\n                      -> VALUE test2 1 7\r\ntesting\r\nEND\r\n
```

- `get <key> [<key> ...]`: one `VALUE <key> <flags> <bytes>\r\n<data>\r\n`
  line per found key, in request order, terminated by `END\r\n`. A key
  that is not found (or is expired) contributes nothing; if none are
  found the reply is just `END\r\n`.
- The page's get examples use a single key; multi-key get is the same
  rule applied per key and is supported.

## Step 3 — Concurrency

One thread per client connection, so two or more clients can be
connected and issuing commands at the same time. All store access is
serialised by a single lock.

## Step 4 — Expiry

- `exptime` 0: never expires.
- `exptime` > 0: expires that many seconds into the future (server time).
- `exptime` < 0: immediately expired (stored, but never retrievable).
- Lazy expiration: an expired item is not swept eagerly; it is removed
  when a client next accesses the key, and that access behaves as if the
  key did not exist.
- Page examples: `set test 0 1 4` then a get after ~1 s returns `END`;
  `set test 0 100 4` is retrievable; `set test 0 -1 4` is not.

Note: real Memcached treats exptime values over 30 days as absolute Unix
timestamps. The challenge page defines non-zero exptime purely as
"seconds into the future", so this build follows the page: every
positive value is a relative number of seconds. (See DESIGN.md.)

## Step 5 — add and replace

Same command line and data block as `set`.

- `add`: store only if the server does NOT already hold a live (unexpired)
  value for the key. Otherwise `NOT_STORED`.
- `replace`: store only if the server DOES already hold a live value for
  the key. Otherwise `NOT_STORED`.
- On success both reply `STORED` (unless `noreply`).

## Step 6 — append and prepend

Same command line and data block as `set`; the stored flags/exptime are
replaced by the ones in the append/prepend command (matching real
Memcached behaviour).

- `append`: append the data block to the existing value. Fails with
  `NOT_STORED` if the key has no live value.
- `prepend`: prepend the data block before the existing value. Fails
  with `NOT_STORED` if the key has no live value.
- On success reply `STORED` (unless `noreply`).

Page examples (starting from `test` = `john`):

```
append test 0 0 4 / more   -> STORED, get test -> VALUE test 0 8 / johnmore
prepend test 0 0 4 / send  -> STORED, get test -> VALUE test 0 12 / sendjohnmore
append foo ... / prepend foo ... (missing key) -> NOT_STORED
```

## delete (required by this project's brief; "Going Further" on the page)

```
delete <key> [noreply]\r\n
```

- Deletes a live value. Reply `DELETED` if the key existed, `NOT_FOUND`
  if it did not (or was expired, in which case it is lazily removed).
- `noreply` suppresses the reply, as for storage commands.

## Errors

- Unknown command or malformed command line: `ERROR\r\n`.
- Malformed storage command (wrong field count, non-integer
  flags/exptime/bytes, negative byte count): `ERROR\r\n`, and the
  connection stays open for the next command. (For a malformed storage
  line the server cannot know how many data bytes follow, so it cannot
  reliably resynchronise; tests therefore only send well-formed storage
  commands after an error, or use a fresh connection.)
- A data block that is shorter than `bytes` because the client closed
  the connection ends that connection; it does not crash the server.

## Explicitly out of scope

The page's "Going Further" items other than `delete` are NOT implemented:
`cas`, `incr`/`decr`, cache-size limits / eviction, and the binary
protocol. The server also does not persist data across restarts and does
not implement `flush_all`, `stats`, or `version`. These are documented
divergences from full Memcached, not from the challenge page's core
steps (Steps 1–6), which are all implemented.

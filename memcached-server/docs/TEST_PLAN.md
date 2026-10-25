# TEST_PLAN — Memcached Server

## Harness

- `tests/test_memcached_server.py`, Python `unittest`, no third-party
  packages.
- Each test class starts the real server in a background thread on an
  **ephemeral port** (`port 0`, read back from the bound socket) — no
  hard-coded ports, no port clashes with a developer's own Memcached.
- The client is a raw `socket` wrapped in a tiny helper: `send(bytes)`
  and `read_until(marker)` / `read_exact(n)`, so tests speak the wire
  protocol exactly as telnet would, including `\r\n` handling.
- `setUp` opens a fresh connection per test; `tearDown` closes it.
  The server thread is daemonised and shut down in `tearDownClass`
  via `server.shutdown()`.

## Cases (mapped to the challenge page)

Step 1 — startup:
- Server binds and accepts a TCP connection on the ephemeral port.
- `-p` parsing: `main(["-p", "<port>"])` binds that port (tested by
  starting a second server instance on another ephemeral port via the
  same argument path); default port constant is 11211.

Step 2 — set/get:
- `set` then `get` returns `VALUE <key> <flags> <bytes>`, data, `END`.
- Flags round-trip (e.g. flags 1 returned as 1).
- `get` of a missing key returns just `END`.
- `noreply` set sends no reply, but the value is stored (verified by a
  following `get`).
- Zero-byte value: `set k 0 0 0` with an empty block stores and `get`
  returns `VALUE k 0 0` plus empty data plus `END`.
- Binary-safe value: a data block containing `\r\n` and non-ASCII bytes
  round-trips byte-for-byte (length is honoured, not line scanning).
- Overwriting a key replaces value and flags.
- Multi-key `get` returns values for found keys only, in request
  order, then `END`.

Step 3 — concurrency:
- Two simultaneous connections: one sets a key, the other reads it.
- Several threads issuing interleaved set/get on distinct keys all see
  their own values (no cross-talk, no crash).

Step 4 — expiry:
- `exptime` 1: value present immediately, gone after ~1.2 s (`END`).
- `exptime` 100: still present.
- Negative `exptime`: `STORED` reply, but `get` returns `END`.
- Expired key does not block `add` (an expired entry counts as absent).

Step 5 — add/replace:
- `add` on a missing key stores; `add` on an existing key `NOT_STORED`
  and leaves the old value.
- `replace` on an existing key stores; on a missing key `NOT_STORED`.
- `noreply` honoured for `add`/`replace` (no reply, effect applied).

Step 6 — append/prepend:
- `append` extends, `prepend` prefixes, byte counts and values match
  the page's `john` -> `johnmore` -> `sendjohnmore` transcript.
- `append`/`prepend` on a missing key return `NOT_STORED`.
- Flags/exptime on append/prepend come from the new command.

delete (brief requirement):
- `delete` of an existing key returns `DELETED` and a following `get`
  returns `END`.
- `delete` of a missing key returns `NOT_FOUND`.
- `delete` of an expired key returns `NOT_FOUND`.
- `delete ... noreply` sends no reply but deletes.

Errors / robustness:
- Unknown command returns `ERROR` and the connection stays usable.
- Malformed `get` (no key) returns `ERROR`.
- Client disconnect mid-session does not kill the server; a new
  connection afterwards still works.

## Manual check (not automated)

Reproduce the page's telnet transcripts for Steps 2, 5 and 6 against a
server started with `python3 memcached_server.py -p 9999`, using
`printf` piped through `nc`/a raw socket (telnet may not be installed),
and confirm the replies match the page byte for byte.

## Pass criterion

`python3 -m unittest discover -s tests -v` exits 0 with every test
passing. Any failure is fixed in the server (or, if the test itself is
wrong about the page's spec, the test is corrected and the reason noted
in the final report).

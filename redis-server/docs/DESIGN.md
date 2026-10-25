# DESIGN — Redis Server

## Assumptions (stated before coding)

1. **Python 3 standard library only, one main file** (`redis_server.py`),
   matching the earlier projects in this repo. No third-party Redis
   client is used; tests speak raw RESP over sockets.
2. **One thread per client** (`socketserver.ThreadingTCPServer` with
   daemon threads), as the page offers this as one of the two options
   for Step 4. One global lock guards the whole store: simplest correct
   concurrency, and throughput is explicitly not the goal (Step 4).
3. **Keys and string values are bytes.** RESP is a byte protocol; keeping
   bytes end-to-end avoids encoding surprises. Commands are matched
   case-insensitively on their ASCII-decoded name.
4. **Store shape:** a single dict `key -> Entry`, where `Entry` is
   `(kind, value, expire_at)` with `kind` `"string"` or `"list"`,
   `value` bytes or `list[bytes]`, and `expire_at` a Unix-epoch float
   or `None`. One dict (rather than one per type) keeps EXISTS/DEL/SET
   trivial and mirrors "dictionary server".
5. **Expiry as absolute epoch time.** `EX`/`PX` are converted to an
   absolute deadline at SET time; `EXAT`/`PXAT` already are one. All
   expiry checks are then a single `time.time() > expire_at` comparison
   — constant time, no timers, no background thread (see SPEC
   divergence 4).
6. **RESP parsing is incremental.** A per-connection byte buffer plus a
   pure `parse_one(buf) -> (value, bytes_consumed)` function that raises
   `NeedMoreData` when the buffer holds a partial message. The same
   function is unit-tested directly (Step 1) and used by the server
   loop, so pipelined commands in one TCP segment just work.
7. **Errors never kill a connection** for command-level errors (unknown
   command, wrong arity, WRONGTYPE, non-integer): the server replies
   with an Error and keeps serving that client. Only a malformed RESP
   frame closes the connection, after one protocol-error reply.
8. **SAVE format:** JSON snapshot (see SPEC divergence 1). One object
   per line is overkill; a single JSON document `{"key": {"type": ...,
   "value": <base64 or list of base64>, "expire_at": ...}}` is written
   atomically via write-to-temp-then-rename, so a crash mid-SAVE cannot
   corrupt the previous snapshot. On startup, expired entries in the
   snapshot are skipped. The dump path is a constructor/CLI option
   (default `dump.rdb`); tests point it at a temp directory so the repo
   is never polluted.
9. **INCR/DECR range:** signed 64-bit, matching Redis. Values outside
   it (or non-numeric) produce the standard Redis error message.
10. **No persistence of the server process itself:** no config file, no
    replication, no pub/sub, no transactions. Out of scope for a lite
    clone; the page's Steps 0–6 do not ask for them.

## Module layout (single file)

- `NeedMoreData`, `RespError` — parser signals.
- `parse_one(data)` / `encode(value)` — pure RESP codec. Values:
  `bytes` → Bulk String, `str` starting with `+`/`-` handled via
  dedicated `SimpleString`/`Error` wrappers, `int` → Integer,
  `None` → Null Bulk String, `list` → Array.
- `Store` — dict + lock + expiry helpers + one method per command's
  storage logic (pure, no sockets; the command dispatcher calls these).
- `execute(store, command: list[bytes]) -> reply value` — argument
  validation and dispatch; returns a codec value.
- `RedisTCPServer` / `RedisHandler` — socketserver plumbing; handler
  loops `recv → buffer → parse_one → execute → encode → sendall`.
- `create_server(host, port, dump_file)` — used by both CLI and tests.
- `main()` — argparse: `--host` (default `127.0.0.1`), `--port`
  (default `6379`), `--dump-file` (default `dump.rdb`).

## Verification criteria

- `python3 -m unittest discover` in `tests/` passes (parser unit tests
  + live-server tests on an ephemeral port + concurrency test +
  SAVE/load round-trip test).
- A manual smoke check with a raw socket (or `redis-cli` if available)
  is optional; the test suite is the verification.

# Redis CLI — Test Plan

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

No real Redis daemon, no fixed port, no network beyond loopback.
One test file: `tests/test_redis_cli.py`.

## Fake server

`FakeRedisServer` (in the test file, not shipped code): a threaded
TCP server bound to `127.0.0.1:0` (ephemeral port), speaking RESP2,
with an in-memory dict + lists. Implements PING [message], ECHO,
SET, GET, DEL, EXISTS, INCR, DECR, LPUSH, RPUSH, LRANGE, LLEN, and
returns real Redis-style error replies for unknown commands and wrong
argument counts. Each test class starts it in `setUpClass` and stops
it in `tearDownClass`; the listening socket is closed and the thread
joined — no stray processes, no `pkill`.

## Coverage

1. **RESP encode** — `encode_command` for the page's examples
   (`ping`, `echo hello world`, `get key`, `set key value`) byte-
   exact, incl. empty string and unicode arguments.
2. **RESP decode (page examples)** — `parse_reply_bytes` for every
   example in SPEC.md: null bulk, null array, simple strings,
   errors (returned as `RedisError` values, not raised), integers,
   empty bulk, nested arrays. Errors as values matter: the CLI must
   print them, not crash.
3. **RESP decode (invalid)** — truncated input, unknown prefix byte,
   non-numeric length, negative length other than -1, bulk body
   shorter than declared, missing trailing CRLF: all raise
   `RespError`.
4. **RESP round-trip** — encode then decode returns the original
   argument list.
5. **Formatting** — simple/bulk raw, `(nil)`, `(integer) N`, error,
   numbered arrays, empty array, nested array indentation.
6. **One-shot over the wire** — `RedisClient.command` against the
   fake server: PING -> PONG, PING msg -> msg, SET/GET round-trip,
   GET missing -> None, DEL/EXISTS counts, INCR/DECR incl. on a
   fresh key and on a non-integer (error reply), LPUSH/RPUSH/
   LRANGE/LLEN, unknown command -> error reply (not exception).
7. **REPL** — `run_repl` driven with `io.StringIO` streams against
   the fake server: prompt shows `host:port>`, commands print
   formatted replies, `quit` exits without sending anything (the
   fake server records commands received), `exit` likewise, blank
   lines ignored, quoted values survive `shlex`, bare `get` prints
   a usage hint and sends nothing, `help`/`help set`/`help @string`
   output, unknown help topic prints an error line.
8. **CLI entry (`main`)** — one-shot via `main()` with a fake-server
   port returns 0 and prints the reply; connection to a closed port
   returns 1 with stderr text; `--help` exits 0 via argparse.
9. **Oracle (manual, not automated)** — against the in-repo
   `redis-server` on an ephemeral port, read-only: PING, SET/GET,
   INCR, LPUSH/LRANGE through the real CLI binary. Recorded in the
   delivery report, not in the suite (keeps the suite hermetic).

## Non-goals for tests

- Real `redis-cli` parity beyond the formatting rules in SPEC.md.
- RESP3, TLS, performance, concurrent clients.

# DESIGN — Memcached CLI Tool

## Assumptions (stated before coding)

1. The server speaks the Memcached plain-text protocol over TCP. No binary
   protocol, auth, or UDP support is assumed or needed.
2. Keys are single tokens (no spaces, no newlines) — this is a protocol
   constraint, not just a CLI choice. Values are UTF-8 text in this client;
   byte length is computed after UTF-8 encoding, so non-ASCII values round-trip.
3. One connection per invocation in one-shot mode; one persistent connection
   for the whole REPL session. Reconnecting mid-session is not attempted —
   a dropped connection ends the REPL with an error message.
4. `get` of a missing key is success with no output, matching the protocol
   (`END` with no `VALUE` block). Only protocol error lines are failures.
5. Python 3 standard library only, one file, no threads in the client itself.
   Tests use a threaded fake server, but that lives only in the test file.

## Structure (single file: `memcached_cli.py`)

```
MemcachedError(Exception)          # server error line, or protocol violation
ConnectionError -> wrapped as MemcachedError for uniform handling

MemcachedClient:
    __init__(host, port, timeout=5)
    connect() / close()            # socket.create_connection; context-manager support
    _send(bytes) / _readline() / _read_exact(n)
    _storage(cmd, key, value, flags, exptime) -> reply word
    set/add/replace/append/prepend -> reply word
    get(key) -> (flags, value) | None
    get_multi(keys) -> dict key -> (flags, value)
    gets(key) / gets_multi(keys) -> dict key -> (flags, value, cas)
    delete(key) -> reply word
    incr(key, amount) / decr(key, amount) -> int
    touch(key, exptime) -> reply word
    flush_all() -> reply word
    stats() -> dict (ordered by receipt; printed verbatim by the CLI)
    version() -> str (the full "VERSION x.y.z" line)

CLI:
    build_parser()                 # argparse: globals + one subparser per command
    run_command(client, args) -> int   # dispatch; prints results; 0/1/2
    repl(client) -> int            # shlex-split loop; same verbs as one-shot
    main(argv=None) -> int         # connect, dispatch or REPL, close, exit code
```

Reading is deliberately strict: `_readline` requires `\r\n` termination and
`_read_exact` loops until the requested byte count arrives, so a short read
or a truncated block raises `MemcachedError` instead of silently truncating
a value. Retrieval parsing validates the `VALUE` header shape before reading
the block, so a malformed header cannot desynchronise the stream.

## Why this shape

- A small client class separate from argparse means the tests exercise the
  real wire behaviour (subprocess CLI runs against a fake server) while the
  class itself stays unit-testable.
- One-shot and REPL share `run_command` logic via a tiny adapter: the REPL
  parses a line into the same namespace shape argparse produces, so a verb
  cannot behave differently in the two modes.
- `stats()` returns a dict because callers print it; keeping the raw lines
  would push parsing into the CLI. `version()` returns the raw line because
  there is nothing to parse — the line *is* the answer.

## Edge cases handled

- Empty value: `set k ""` sends a 0-byte block; the fake server and the
  client both handle it (header `0`, immediate `\r\n`).
- `incr`/`decr` on a non-numeric or missing key: server reply `NOT_FOUND`
  (or an error line) surfaces as an error, not a crash.
- Multi-key `get`: one request, multiple `VALUE` blocks, in server order.
- REPL `set` with spaces: everything after the key is the value (joined with
  single spaces after shlex splitting; quoted values keep their spaces).
- Keyboard interrupt (Ctrl-C) in the REPL exits cleanly; EOF does the same.

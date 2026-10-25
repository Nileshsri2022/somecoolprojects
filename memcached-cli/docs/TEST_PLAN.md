# TEST_PLAN — Memcached CLI Tool

## Approach

Tests live in `tests/test_memcached_cli.py` (unittest, stdlib only). They run
a small in-process fake Memcached server — not the repo's memcached-server
project — on an **ephemeral port** (`port 0`, the OS picks the port, the test
reads back the real port). Nothing hard-codes 11211 or any other port, and
no test requires a real memcached daemon.

The fake server implements just enough of the text protocol for the tests:
`set`/`add`/`replace`/`append`/`prepend` (with flags/exptime stored, expiry
ignored), `get`/`gets` (cas counter increments per store), `delete`,
`incr`/`decr` (non-numeric stored value → `CLIENT_ERROR`), `touch`,
`flush_all`, `stats` (a few fixed lines), `version` (`VERSION 1.6.9`),
`quit`, and `ERROR` for unknown commands. It is threaded
(`socketserver.ThreadingTCPServer`, `daemon_threads = True`) so the CLI
subprocess and the test process can talk to it concurrently, and it is shut
down in `tearDownClass`.

## Coverage

Client-level (direct `MemcachedClient` against the fake server):

1. set then get round-trip, including flags preserved.
2. get of a missing key returns `None`; multi-get returns only found keys.
3. gets returns a cas token; a second store changes the cas token.
4. add stores only when absent (`NOT_STORED` when present); replace stores
   only when present (`NOT_STORED` when absent).
5. append / prepend concatenate in the correct order.
6. delete returns `DELETED` then `NOT_FOUND` on the second delete.
7. incr / decr arithmetic, default amount 1, and `NOT_FOUND` for a missing key.
8. touch returns `TOUCHED` / `NOT_FOUND`.
9. flush_all empties the store; stats returns the fake server's lines;
   version returns the `VERSION` line.
10. Empty-string value round-trips; non-ASCII value round-trips byte-exact.
11. Unknown command raises `MemcachedError` (raw protocol path).

CLI-level (subprocess `python3 memcached_cli.py --host 127.0.0.1 --port <ephemeral> ...`):

12. One-shot `set` prints `STORED`; one-shot `get` prints `KEY: VALUE`;
    one-shot `get` of a missing key prints nothing and exits 0.
13. One-shot `incr` prints the new value; `stats` prints `STAT` lines;
    `version` prints the `VERSION` line; `delete` prints `DELETED`.
14. REPL: feeding `set k v\nget k\nquit\n` on stdin prints `STORED` and
    `k: v` and exits 0.
15. Connection failure (port with nothing listening, also ephemeral) exits
    non-zero with an error on stderr, not a traceback.

## How to run

```
cd memcached-cli
python3 -m unittest discover -s tests -v
```

## Success criteria

All tests pass; no test server process is left running after the run
(`tearDownClass` shuts the fake server down, and the CLI subprocesses exit
on their own). No `__pycache__` is left in the delivered tree.

# DESIGN — Memcached Server

Assumptions stated before coding (ponytail: think before coding).

## Language and shape

- Python 3, standard library only. One file: `memcached_server.py`.
- Thread-per-client (`threading.Thread`, daemon threads) — the page's
  Step 3 option 1. No async framework, no dependencies.
- A single `threading.Lock` guards the whole store dict. Throughput is
  not a goal of this challenge; correctness under concurrent clients is,
  and one lock is the simplest correct choice.

## Store

```python
store: dict[bytes, Item]   # key -> Item(flags, exptime_deadline, data)
```

- Keys are `bytes` (the protocol is byte-oriented; decoding to `str`
  would break non-ASCII keys). Values are `bytes` for the same reason.
- `Item` is a small dataclass: `flags: int`, `expires_at: float | None`
  (`None` = never expires), `data: bytes`.
- `exptime` handling (per SPEC.md, following the page, not real
  Memcached): `0 -> None`; `> 0 -> time.monotonic() + exptime`;
  `< 0 -> already expired` (stored with a deadline in the past, so the
  first access lazily removes it and reports a miss — exactly the
  page's "immediately expired" behaviour, with no special case).
- `time.monotonic()` is used for deadlines so a wall-clock jump cannot
  un-expire or prematurely expire items.
- Lazy expiration only: no background sweeper thread. Every lookup
  (`get`, `add`, `replace`, `append`, `prepend`, `delete`) first checks
  the deadline, deletes the entry if expired, and treats it as absent.
  This is the page's Step 4 design, and it keeps the code to one
  expiration helper, `_live(key)`.

## Connection handling

- Each client thread reads with a buffered binary reader
  (`socket.makefile("rb")`) and writes with `sendall`.
- Reading a command line: `readline()` up to `\n`, stripped of the
  trailing `\r\n`. Reading a data block: `read(n)` for exactly `bytes`
  bytes, then `read(2)` for the trailing `\r\n` — never `readline()`
  on the data, so embedded newlines in values survive.
- Pipelining works naturally: the buffered reader keeps unread bytes
  for the next command on the same connection.
- One command per loop iteration; an empty line (bare `\r\n`, which
  telnet users sometimes send) is ignored rather than answered with
  `ERROR`, so interactive telnet sessions are forgiving. Any other
  malformed line gets `ERROR` and the connection stays open.
- Client disconnect (EOF) ends the thread quietly. A socket error on
  one client never affects the server or other clients.
- `SO_REUSEADDR` is set so restarting the server on the same port
  during development does not hit "address already in use".

## Command dispatch

One `if/elif` chain on the command word:

| Command | Behaviour |
|---|---|
| `set` | Always store. Reply `STORED`. |
| `add` | Store only if no live value. Else `NOT_STORED`. |
| `replace` | Store only if a live value exists. Else `NOT_STORED`. |
| `append` / `prepend` | Combine with existing live value; new flags/exptime come from the command. Else `NOT_STORED`. |
| `get` | `VALUE ...` per live key, then `END`. |
| `delete` | `DELETED` or `NOT_FOUND`. |
| anything else | `ERROR`. |

All storage commands share one parser (`_parse_storage`) and one
reply rule (`noreply` suppresses the reply). `add`/`replace`/
`append`/`prepend` differ only in their precondition, implemented as a
small per-command branch — no speculative generality.

## What is deliberately NOT built

- No `cas` / `incr` / `decr` / size limit / eviction: "Going Further"
  options, not core steps. `delete` is included because this project's
  brief requires it at minimum.
- No persistence, no clustering, no UDP, no binary protocol.
- No config file, no logging framework: a one-line `Serving on
  127.0.0.1:<port>` message to stdout is enough, matching the page's
  Step 1 launch examples.

## Verification

See TEST_PLAN.md. Success criterion: `python3 -m unittest discover -s
tests -v` passes with all tests green against a live server on an
ephemeral port, plus a manual telnet-style session reproducing the
page's Step 2/5/6 transcripts.

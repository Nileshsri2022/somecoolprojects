# Pastebin — Design

## Assumptions

- Python 3 standard library only; no database server, no third-party
  packages. The whole app is one file, `pastebin.py`, built on
  `http.server.ThreadingHTTPServer`.
- Single-process, local use. Concurrency is handled with one
  `threading.Lock` around the in-memory store; this is enough for a
  local pastebin and keeps the code small.
- No authentication. The page does not ask for it, and anyone with a
  paste's URL can view or delete it — same as a public pastebin's
  unlisted-link model. This is documented, not hidden.

## Storage: in-memory dict, optional JSON file

The page says "database" in the broadest sense (an organised collection
of structured data), so an in-memory dict of
`id -> {content, language, created_at, expires_at}` qualifies for the
challenge, with a clear tradeoff:

- In-memory (default): simplest, fastest, no setup; data is lost on
  restart. This is the default because the challenge's steps do not
  require durability.
- `--store <path>`: the same dict is loaded from / saved to a JSON file
  on every create/delete/expiry-removal. Durable across restarts, still
  stdlib-only, still single-process. Not a real database: no queries,
  no concurrent writers, whole-file rewrite per mutation.

A real deployment would swap this dict for SQLite (`sqlite3` is also
stdlib) — noted as a future step, not built, per "minimum code".

## Id generation

Random 7-char base62 ids (`secrets.choice`), not the page's other
suggestion of an atomic counter or a content hash:

- A counter leaks the paste count and is guessable in order.
- A content hash gives the *same* URL for identical content, so two
  users' pastes collide and deleting one deletes the other's.
- Random ids are unguessable enough for unlisted links and unique by
  construction (retry on collision, which is negligible at 62^7).

## Expiry: lazy, checked on access

Every read (view, raw, delete-confirm, delete) first checks
`expires_at`; if it has passed, the paste is deleted and treated as
404. Tradeoff, as the page hints:

- Lazy expiry costs nothing when idle and needs no background thread,
  but expired pastes sit in memory until someone (or something) asks
  for them. A sweeper thread would reclaim them promptly at the cost
  of a background thread and wakeups. For a local tool, lazy wins;
  the `--store` path also means an expired paste is only purged from
  disk when it is next requested.
- `expires_at` is stored as a Unix timestamp (UTC); expiry options are
  fixed durations from creation, not absolute times.

## Syntax highlighting: minimal Python tokenizer

No Pygments in the stdlib, so highlighting is a small hand-written
tokenizer for Python only: comments (`# ...`), string literals
(single/double/triple quotes, with backslash escapes), and a keyword
set (`def`, `class`, `return`, `if`, ...). Each token is HTML-escaped
*before* being wrapped in a `<span>`, so highlighting can never inject
markup. Other languages are rendered as plain escaped text inside
`<pre>` — the language is still stored and shown, but no fake
highlighting is claimed for them.

## HTML safety

All user content is escaped with `html.escape` on every rendered page.
The raw view serves `text/plain`, so browsers do not interpret it.

## Deletion flow

View page → "Delete" link → confirmation page → POST deletes →
303 redirect to home. This is the page's "check they meant to delete
it" step, implemented as a separate page rather than JavaScript
`confirm()`, so it works with no JS at all. Deleting an unknown or
already-deleted id returns 404 (never a success page for nothing).

## Files

- `pastebin.py` — server, routes, store, highlighting. `make_server()`
  factory (host/port/store) exists so tests can bind port 0.
- `tests/test_pastebin.py` — unittest, server on an ephemeral port.

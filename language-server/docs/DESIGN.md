# DESIGN — Language Server (LSP)

Single file, Python 3 standard library only: `lsp_server.py`.
No third-party packages, no threads: one read loop over stdio.

## Modules / layout

- `lsp_server.py` — everything: framing, JSON-RPC dispatch,
  document store, diagnostics, completion, lifecycle, CLI.
- `tests/test_lsp_server.py` — unittest suite (library-level plus one
  subprocess integration test over real pipes).

Keeping one file is deliberate: the LSP wire protocol plus two
features is small, and a single file is what a reader of the
challenge page can follow end to end. No helpers were needed.

## Framing (base protocol)

- Reader works on a binary stream (`sys.stdin.buffer`). It reads
  header lines until a blank line, parsing `Name: value` pairs
  case-insensitively. It requires `Content-Length`; a header block
  without one is logged and ends the loop (there is no way to know
  where the body ends).
- It then reads exactly `Content-Length` bytes and decodes UTF-8
  JSON. A body that fails to parse is logged (`[cclsp] Ignoring
  invalid JSON`) and the loop continues with the next message —
  one bad message must not kill the server.
- Writer emits `Content-Length: <len>\r\n\r\n` + UTF-8 JSON to a
  binary stream and flushes after every message. `json.dumps`
  output is compact (`separators=(",", ":")`) so the length is
  unambiguous.
- Logging goes to stderr (or `--log-file`) with a `[cclsp]`
  prefix. Nothing but framed protocol bytes ever goes to stdout.

## Message model

A decoded message is a plain `dict`. Dispatch is by shape, exactly
as JSON-RPC defines it:
- Has `method` + `id` -> request: a response is always sent
  (`result`, or `error` for unknown/after-shutdown methods).
- Has `method`, no `id` -> notification: never answered.
- Has `id` but no `method` -> a response from a client; logged
  and ignored (this server sends no requests, so none are expected).
- Missing `method` and `id` -> logged and ignored.

`id` values are echoed verbatim (number or string), so clients
using either form get a matching response.

## Document store

`server.documents: dict[uri, dict]` holding `languageId`,
`version`, `text`. Keyed by the document URI string exactly as
sent (no URI normalisation, no `file://` decoding — diagnostics
and completion echo the same URI back, so normalisation would
only risk mismatching the client).

- `didOpen`: `params.textDocument.{uri, languageId, version,
  text}` stored wholesale.
- `didChange`: Full sync — `params.contentChanges[0].text`
  replaces `text`; if `params.textDocument.version` is present it
  replaces the version. A `didChange` for an unknown URI creates
  the entry from the change params (defensive; a well-behaved
  client always opens first). Extra `contentChanges` entries are
  ignored under Full sync, and that is documented in SPEC.
- `didClose`: entry deleted; empty diagnostics published.

## Diagnostics

`analyze_document(text) -> list[diagnostic dict]` scans line by
line, and per line uses `str.find` in a loop so every occurrence
of each phrase is reported, not just the first. Ranges are
`{start: {line, character}, end: {line, character}}` with
`character` = UTF-16 code units? No — character = Python string
index (Unicode code points). This matches the page's examples
(ASCII text) and is documented as a limitation: for documents
with characters outside the BMP, LSP clients expect UTF-16
offsets and this server's offsets would differ. No test or claim
covers non-ASCII positions.

Phrase table (single source of truth in code):

| Phrase | Message | Severity |
|---|---|---|
| `Watching a Video` | It's much better to learn by doing! Try Coding Challenges instead. | 2 Warning |
| `Coding Challenges` | This is the way! | 3 Information |

Note the overlap subtlety: "Coding Challenges" is a substring
of neither phrase's message, and the two phrases do not overlap
each other, so no ordering/overlap rule is needed. Diagnostics
are emitted in line order, phrase-table order within a line.

## Completion

`completion_items(text, line, character)`:
1. If the document is unknown -> `[]` (caller handles this).
2. Take the line (out-of-range line -> empty line), take the
   text before `character`, and walk backwards over
   `[A-Za-z0-9_]` to get the word fragment at the cursor.
3. Return the single `CodingChallenges` item iff the fragment
   is empty or `CodingChallenges.startswith(fragment)`;
   otherwise `[]`.

`textDocument/completion` wraps this as
`{isIncomplete: false, items: [...]}`. Returning a `CompletionList`
rather than a bare array is the form the spec allows and is what
the tests assert.

## Lifecycle / shutdown

- `shutdown_requested: bool` on the server. `shutdown` sets it
  and returns `null`. Any later request (except none — `exit`
  is a notification, not a request) gets error `-32600`.
- `exit` sets `running = False` and records
  `exit_code = 0 if shutdown_requested else 1`. The main loop
  then returns that code; `main()` passes it to `sys.exit`.
- EOF on stdin also stops the loop with exit code 0 (a client
  that just closes the pipe is not an error).

## Error codes

- `-32601` Method not found — unknown request method.
- `-32600` Invalid request — request after `shutdown`.
- No other error codes are produced. `initialize` never fails:
  missing `params`/`clientInfo` is tolerated (logged as unknown
  client) rather than erroring, since a server that refuses to
  start is useless for testing.

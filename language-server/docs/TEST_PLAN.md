# TEST_PLAN — Language Server (LSP)

Run: `python3 -m unittest discover -s tests -v` from
`language-server/`. Python 3 standard library only; no editor,
no network, no real LSP client needed.

## What is tested (and how)

Framing (`encode_message` / `read_message` over `BytesIO`):
- Round-trip: encode then read returns the same dict; the raw
  bytes start with `Content-Length: N\r\n\r\n` and N equals the
  body byte length.
- Header names are case-insensitive and a `Content-Type` header
  is accepted and ignored.
- EOF before any header returns `None` (clean end of stream).

Diagnostics (`analyze_document`, pure function):
- Both phrases on one line produce two diagnostics with exact
  start/end character offsets and the page's messages.
- Multiple occurrences of one phrase on one line all reported.
- No phrases -> empty list.
- Diagnostics on later lines carry the correct 0-based line number.
- Severities: Warning (2) for "Watching a Video", Information (3)
  for "Coding Challenges"; source is `cclsp` on every diagnostic.

Completion (`completion_items`, pure function):
- Empty fragment, `C`, `Cod`, full `CodingChallenges` -> item returned.
- Non-matching fragment (`xyz`, `Watching`) -> empty list.
- Cursor mid-word uses only the text before the cursor.
- Out-of-range line -> empty fragment -> item returned (documented
  behaviour, matches "no fragment" case).

Server behaviour (in-process, `LanguageServer` over `BytesIO`
streams, messages fed in and replies parsed back out):
- `initialize` -> response id echoed, capabilities contain
  `textDocumentSync == 1` and a `completionProvider` key, and
  `serverInfo.name == "cclsp"`. Works with a string id too.
- `initialized` notification -> no reply bytes at all.
- `didOpen` -> document stored; exactly one
  `textDocument/publishDiagnostics` notification follows, with
  the document URI and the expected diagnostics.
- `didChange` (Full) -> stored text replaced, diagnostics
  re-published for the new text.
- `didClose` -> document forgotten, empty diagnostics published.
- `didSave` -> no reply.
- `completion` on an opened doc -> `CompletionList` with the
  `CodingChallenges` item; on an unopened doc -> empty items.
- Unknown request -> error `-32601`; unknown notification ->
  ignored, no reply.
- Malformed JSON body (valid framing, bad JSON) -> logged,
  skipped, subsequent valid message still processed.
- `shutdown` -> `result: null`; a request after shutdown ->
  error `-32600`; `exit` after shutdown -> run returns 0.
- `exit` without shutdown -> run returns 1.
- EOF with no `exit` -> run returns 0.

End-to-end (subprocess over real pipes):
- Spawn `python3 lsp_server.py`, send `initialize`,
  `initialized`, `didOpen`, `textDocument/completion`,
  `shutdown`, `exit` as framed messages on stdin, read all of
  stdout, and assert: initialize response, one publishDiagnostics
  notification containing "This is the way!", completion list
  containing `CodingChallenges`, shutdown response, process exit
  code 0. The subprocess is driven with `communicate()` and a
  timeout so no stray server can survive the test run.

## What is NOT tested

- Any real editor (Neovim, VS Code, or other): not installed or
  driven here. Editor integration is therefore not claimed.
- Non-ASCII character offsets (see DESIGN.md UTF-16 limitation).
- Incremental sync, hover, definition, or any unimplemented
  method — absence is asserted only for the unknown-method
  error path, not per method.
- Concurrent clients: the server is single-client stdio by
  design; there is nothing concurrent to test.

# SPEC — Language Server (LSP)

Source challenge (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-lsp
— "Build Your Own Language Server (LSP)". The page was readable in full
(137 lines); it did NOT 404. This spec follows it step by step.

## Challenge steps (as written on the page)

- Step 0 — Pick a language, use stdio as the transport, and get a way to
  test the server. The page author used Neovim + kickstart.nvim; this
  build is verified against scripted fake-client tests over pipes
  (see TEST_PLAN.md), NOT against a real editor.
- Step 1 — Start up, read/write stdio, serialise/deserialise JSON-RPC
  request, response and notification messages, and answer the
  `initialize` request. Advertised capabilities must include text
  document synchronisation. Logging goes to stderr (never stdout, which
  carries the protocol). Log lines use the page's `[cclsp]` prefix.
- Step 2 — Handle `textDocument/didOpen` and
  `textDocument/didChange`: parse them, store the document, log its
  contents. `initialize` advertises full text document sync.
- Step 3 — Evaluate the opened/changed document and publish
  diagnostics (`textDocument/publishDiagnostics`) for two phrases:
  - `Watching a Video` -> "It's much better to learn by doing! Try
    Coding Challenges instead."
  - `Coding Challenges` -> "This is the way!"
  Each occurrence gets its own diagnostic with the exact line/character
  range of the phrase.
- Step 4 — Support `textDocument/completion` with a completion item
  `CodingChallenges`.
- Going Further — work through the rest of the specification, or build
  a real language analyser (e.g. a JSON language server). NOT built
  here; see "Not built" below.

## Implemented LSP surface

Wire protocol (LSP base protocol over stdio):
- `Content-Length: N\r\n\r\n` + exactly N bytes of JSON. Headers are
  case-insensitive; `Content-Type` (if sent) is accepted and ignored.
  Only UTF-8 JSON bodies are supported.

Requests / notifications handled:
- `initialize` (request) -> `result` with `capabilities` and
  `serverInfo` (`{name: "cclsp", version: "0.1.0"}`). Capabilities:
  `textDocumentSync: 1` (Full), `completionProvider: {}`.
  The client name/version from `params.clientInfo` is logged, as in
  the page's sample log.
- `initialized` (notification) -> logged, no reply.
- `textDocument/didOpen` (notification) -> stores the document
  (uri, languageId, version, text), logs `Opened: <uri>` and the text,
  then publishes diagnostics for it.
- `textDocument/didChange` (notification) -> Full sync only: the
  first `contentChanges` entry's `text` replaces the whole document
  (this is what `textDocumentSync: 1` promises). Version updated if
  present. Diagnostics are re-published.
- `textDocument/didClose` (notification) -> forgets the document and
  publishes an empty diagnostics list to clear editor markers.
- `textDocument/didSave` (notification) -> accepted, no action, no reply.
- `textDocument/completion` (request) -> a completion list. See below.
- `shutdown` (request) -> `result: null`, server enters shutdown state.
- `exit` (notification) -> terminates: exit code 0 if `shutdown` was
  received first, 1 otherwise (per the LSP lifecycle).
- Unknown request -> JSON-RPC error `-32601` (Method not found).
  Unknown notification -> logged and ignored, no reply.
- A request received after `shutdown` (other than `exit`) -> JSON-RPC
  error `-32600` (Invalid Request), per the lifecycle spec.

Diagnostics (`textDocument/publishDiagnostics`, notification):
- Source field is `cclsp`. Severity: `2` (Warning) for
  "Watching a Video", `3` (Information) for "Coding Challenges".
- Matching is case-sensitive and exact, on every line, every
  occurrence (not just the first per line). Range is 0-based
  (line, character) spanning exactly the phrase.
- Diagnostics are published after every `didOpen` and `didChange`,
  and an empty list after `didClose`. The document `version` is
  echoed in the publish params when known.

Completion (`textDocument/completion`, request):
- Returns `{isIncomplete: false, items: [...]}` with a single item:
  `label: "CodingChallenges"`, `detail: "Coding Challenges — learn by
  doing"`, `documentation: "Try Coding Challenges instead of watching
  videos."`, `insertText: "CodingChallenges"`.
- Filtering: the item is returned only when the word fragment at the
  cursor is empty or a case-sensitive prefix of `CodingChallenges`
  (e.g. cursor after `Cod`); otherwise the list is empty. A completion
  request for a document that was never opened also returns an empty
  list. The page shows the item in the editor but does not specify a
  filtering rule, so this prefix rule is a deliberate, documented
  choice — not a page requirement.

## Deliberate divergences from the page

1. Testing against a real editor (Neovim/kickstart.nvim, the page
   author's route) is NOT done. Verification is by scripted
   fake-client tests over pipes and in-process byte streams. No
   editor integration is claimed.
2. The page's example diagnostics are for text files; this server
   analyses any opened document the same way regardless of
   `languageId` (the page does not restrict by language either).
3. Severities (Warning vs Information) are this build's choice; the
   page specifies only the messages.
4. The completion prefix filter (above) is this build's choice; the
   page specifies only the item.
5. The page suggests the log line "Sent the reply"; this build logs
   one line per received method plus open/publish events, which
   covers the same information without a per-reply line.
6. Logging defaults to stderr. An optional `--log-file PATH` redirects
   it to a file (useful when stderr is also captured by a harness).

## NOT built (honestly scoped out)

- Hover, go-to-definition, references, document symbols, code actions,
  formatting, rename, and every other language feature in the LSP
  specification. The page's steps only require diagnostics and
  completion; the Going Further section is explicitly out of scope.
- Incremental (`textDocumentSync: 2`) or incremental-range sync:
  Full sync only, as advertised.
- Pull diagnostics (`textDocument/diagnostic`), workspaces
  (`workspace/*`), configuration, progress, or client/register
  capability negotiation beyond `initialize`.
- A real language analyser (JSON or any programming language). The
  diagnostics are the page's two fixed phrases only.
- Multi-root / workspace-folder handling: documents are keyed by URI
  alone; `initialize` params other than `clientInfo` are ignored.
- Malformed framing recovery beyond logging: a message whose JSON
  body does not parse is logged and skipped; a stream that ends
  mid-header or mid-body ends the server (EOF). No
  `Content-Length`-less or chunked framing.

## Usage

```sh
python3 lsp_server.py            # stdio server; logs to stderr
python3 lsp_server.py --log-file /tmp/cclsp.log
python3 lsp_server.py --help
```

The server reads LSP messages on stdin and writes responses and
notifications on stdout. Do NOT type at it interactively expecting
readable output — stdout is binary-framed JSON.

# language-server — Build Your Own Language Server (LSP)

Coding Challenges: https://codingchallenges.fyi/challenges/challenge-lsp
Docs first, then code — see `docs/` (`SPEC.md`, `DESIGN.md`,
`TEST_PLAN.md`).

A small Language Server implementing the Language Server Protocol
over stdio, in Python 3 standard library only (`lsp_server.py`).
It speaks the LSP base protocol (`Content-Length` framing +
JSON-RPC), handles the server lifecycle, stores opened documents,
publishes diagnostics, and answers completion requests.

## Implemented methods

- `initialize` / `initialized` — capabilities: full text document
  sync (`textDocumentSync: 1`) and a completion provider; server
  name `cclsp`.
- `textDocument/didOpen`, `textDocument/didChange` (Full),
  `textDocument/didClose`, `textDocument/didSave`
- `textDocument/publishDiagnostics` (server notification) for two
  phrases: `Watching a Video` -> "It's much better to learn by
  doing! Try Coding Challenges instead." (Warning), and
  `Coding Challenges` -> "This is the way!" (Information).
- `textDocument/completion` — one item, `CodingChallenges`,
  returned when the word at the cursor is empty or a prefix of it.
- `shutdown` / `exit` — exit 0 after shutdown, 1 otherwise.

NOT implemented (honest scope, see `docs/SPEC.md`): hover,
go-to-definition, references, code actions, formatting, rename,
incremental sync, pull diagnostics, workspace handling, and any
real language analyser. The diagnostics are the challenge page's
two fixed phrases only.

## Usage

```sh
python3 lsp_server.py            # stdio server; logs to stderr
python3 lsp_server.py --log-file /tmp/cclsp.log
```

Stdout carries framed protocol bytes only — do not expect readable
output from an interactive terminal. Logs use the `[cclsp]` prefix
and go to stderr by default, so they never corrupt the protocol.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use scripted fake clients over pipes and in-memory streams —
NOT a real editor. No editor integration is claimed; see
`docs/TEST_PLAN.md` for what is and is not covered.

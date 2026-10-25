# Code Comment Remover — DESIGN

## Overview

One file, `ccremover.py`, Python 3 standard library only. The core is a
small hand-written character scanner, not regular expressions: regexes
cannot track "inside a string / inside a block comment" state across a
whole file, and that state is exactly what separates a comment marker
from the same characters inside a string literal (see SPEC.md).

## Pipeline

```
input text
  -> split into lines (keeping no line terminators; \r\n is normalised)
  -> scanner pass (per language) producing output lines
  -> join with "\n", single trailing newline if any output lines
```

The scanner works line by line but carries state across lines:
`in_block_comment` (and its start line, for error messages) and, for
Python, `in_triple_string` (quote kind, raw flag). Single-line strings
cannot span lines in any supported language (except Go raw backtick
strings and Python triple-quoted strings, which the scanner handles
explicitly), so per-line scanning with carried state is sufficient.

## Scanner states

### Python scanner (`strip_python`)

State: `triple` — None or `(quote, raw)` for an open `'''`/`"""` string.

For each line, walk characters left to right:

- If inside a triple-quoted string: copy characters until the matching
  triple quote (honouring backslash escapes unless raw), then resume
  normal scanning.
- If at a string start: recognise an optional prefix of letters from
  `rRbBfFuU` immediately before a quote (the prefix letters are copied
  as code, not skipped — the scanner just needs to know the string is
  raw). A triple quote opens triple state; a single quote scans to its
  closing quote on the same line, honouring backslash escapes unless raw.
- If at `#` outside a string: the rest of the line is a comment. If the
  comment is a preserved tool comment (see below), emit the whole line
  unchanged; otherwise drop the comment text. If nothing but whitespace
  precedes it, the line produces no output line at all.
- Otherwise copy the character.

Note: Python has no block comments, so there is no block state. A `#`
inside a triple-quoted string is copied, never treated as a comment.

### C-style scanner (`strip_cstyle`, shared by js / c / go)

State: `in_block` (bool), `block_start_line` (int).

For each line, walk characters left to right:

- If inside a block comment: look for `*/`. If found, resume normal
  scanning after it (code after `*/` on the same line is kept). If not
  found, the whole line is comment content.
- If at a string start (language-dependent quote set): scan the string
  on the same line (single/double quotes, rune/char literals), honouring
  backslash escapes unless it is a Go raw backtick string. A Go backtick
  string may span lines: the scanner carries `in_raw_string` state for
  it (a Go-only extension of the same state machine).
- If at `//` outside a string: line comment to end of line (see
  preservation rules below).
- If at `/*` outside a string: enter block state.
- Otherwise copy the character.

Quote sets: js → `'`, `"`, `` ` `` (backtick template literals,
multi-line); c → `'`, `"`; go → `"`, `` ` `` (raw, multi-line),
`'` (rune).

Multi-line string state is carried only for js backticks, Go backticks,
and Python triple quotes. Single/double-quoted strings and char / rune
literals are single-line: an unterminated one at end of line is copied
to end of line and scanning resumes fresh on the next line.

## Preservation: Go doc comments and tool comments

Preservation cannot be decided purely inside the character scanner,
because a Go doc comment is defined by what follows it (the next line).
So the C-style path works in two passes:

1. **Tokenise into segments.** `_scan_cstyle_lines` scans the whole
   text once and returns, per input line, a list of segments
   `(kind, text, group_id)` where kind is `code` or `comment` and
   block comments spanning lines share one group id. A second pass
   groups consecutive comment-only `//` lines into one group, then
   decides, per group/segment, keep-or-drop:
   - tool comment → keep (verbatim original comment text);
   - Go doc comment (go mode, `--go-doc` on) → keep if the line
     immediately after the comment group's last line is a declaration
     line (first token in `package/func/type/var/const`);
   - otherwise → drop.
2. **Reassemble.** Kept comments are re-inserted at their original
   position (a comment-only line stays a line; a trailing comment stays
   trailing on its code line, with the code's trailing whitespace
   stripped only when the comment is dropped). Dropped comment-only
   lines produce no output line. Dropped block comments spanning lines
   produce no lines for their comment-only lines, and code before/after
   the block on the boundary lines is joined.

For Python, preservation is simpler (line comments only, no doc-comment
rule), so the Python scanner applies the tool-comment check inline and
needs no second pass. The Go doc-comment second pass is only used for
`go` mode; for `js`/`c` the tool-comment check is applied inline during
scanning, since no look-ahead is needed there.

Implementation note: there is one C-style scanner, shared by js/c/go;
`strip_cstyle` applies the Go doc-comment decision before final
assembly, and the tool-comment check during that same pass. The exact
internal shape is documented in code comments in `ccremover.py`, which
is authoritative if this file and the code ever disagree about a helper
name.

## Comment-text classification (tool comments)

Given a comment's raw text (without the marker), strip leading
whitespace and test prefixes:

- Python: `noqa`, `type:`, `pylint:`, `flake8:`, `fmt:`, `isort:`,
  `mypy:`, `coverage:`, `pyright:`, `ruff:`. Prefix matching is
  plain `startswith` on the stripped text, so `# noqa: E731`,
  `#noqa`, and `# type: ignore` all match; `# notably` does NOT match
  `noqa` (it starts with `not`), and `# types` does not match `type:`
  (no colon). This is deliberate: the colon in most prefixes prevents
  false positives.
- C-style: `go:` (only when the marker is immediately `//go:`, no
  space) or `+build` (after stripping, so `// +build linux` matches).

## Error handling

- Unterminated block comment: the scanner raises `UnterminatedComment`
  with the start line; the CLI prints `ccremover: error: unterminated
  block comment starting on line N` to stderr and exits 2, writing
  nothing to stdout.
- I/O errors (missing file, undecodable UTF-8): caught in the CLI,
  same exit-2 pattern.
- Broken pipe / KeyboardInterrupt: not specially handled beyond Python
  defaults; no partial-file writes exist because output goes to stdout
  only.

## What is deliberately not in the design

- No full lexer/tokeniser per language (no AST, no regex-vs-division
  disambiguation in JS, no `${}` re-scanning in template literals).
  The scanner is a string/comment state machine, which is the level the
  challenge's "simple regexes → lexer" spectrum invites at the simple
  end, upgraded just enough to be string-aware.
- No formatting or whitespace normalisation beyond trailing-whitespace
  stripping on comment-stripped lines (this is not a formatter or
  minifier).
- No caching, no config files, no parallelism: input sizes for this
  tool are source files, and a single linear pass is fast enough.

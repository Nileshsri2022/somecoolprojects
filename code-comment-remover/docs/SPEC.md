# Code Comment Remover — SPEC

## Challenge source (resolved, not guessed)

- Challenge page: https://codingchallenges.fyi/challenges/challenge-code-comment-remover/
  (returned by search as `https://codingchallenges.fyi:443/challenges/challenge-code-comment-remover/`;
  the `:443` is the default HTTPS port, so the canonical form above is the same URL.)
- Title on the page: "Build Your Own Code Comment Remover".
- Resolution method: web search for the challenge title, then a direct read of the
  returned codingchallenges.fyi page in full (Steps Zero–5 plus "Going Further").
  The site's tag index (https://codingchallenges.fyi/challenges/tags) was also
  opened; it lists `cli`, `parsing`, and `dev tools` among the tags, matching the
  tags given for this project. No URL was guessed.
- Mirror / earlier text: Coding Challenge #87 on Substack
  (https://codingchallenges.substack.com/p/coding-challenge-87-code-comment)
  carries the same Steps 0–3 text; the fyi page is treated as authoritative.

## What the page asks for

- Step Zero: set up an environment and a language comfortable for building a CLI tool.
- Step 1: remove Python comments: `#` to end of line. Example:
  `# this is a comment` and `l = [x for x in range(10)] # this is also a comment`.
  The page suggests testing against real open-source Python code.
- Step 2: remove C/C++-style comments (`//` line, `/* ... */` block) from
  JavaScript source. The page's factorial example shows comment-only lines
  disappearing entirely (no blank line left behind) and trailing comments
  removed with the code kept.
- Step 3: remove the same C/C++-style comments from C and C++ code
  (same factorial example, C syntax).
- Step 4: support Go, leaving in Go doc comments — comments that can be
  extracted from Go source to create documentation.
- Step 5: leave in Python and Go comments related to configuration of tools
  and linters. Page examples: Python `# noqa: E731` and Go
  `//go:generate` and `//go:build ignore`.
- Going Further (NOT built, see "Not built"): more languages, minification,
  obfuscation (whitespace removal + renaming variables/functions).

## What this build does

A single-file Python 3 (standard library only) CLI filter, `ccremover.py`,
that reads source from stdin or from one or more files and writes the
comment-stripped source to stdout. It never modifies an input file in place
(the page never asks for in-place editing, so no such option exists).

### Supported languages and comment forms

| Language (`--lang`) | Line comment | Block comment | Strings honoured |
|---|---|---|---|
| `python` | `#` to end of line | — (none) | `'...'`, `"..."`, `'''...'''`, `"""..."""`, with `r/b/f/u` prefixes (any case, combinable) and backslash escapes (ignored in raw strings) |
| `js` | `//` to end of line | `/* ... */` | `'...'`, `"..."`, `` `...` `` (template literals, escapes honoured) |
| `c` | `//` to end of line | `/* ... */` | `'...'` (character literals, escapes honoured), `"..."` |
| `go` | `//` to end of line | `/* ... */` | `"..."`, `` `...` `` (raw, multi-line, no escapes), `'.'` (rune literals, escapes honoured) |

Language selection: `--lang python|js|c|go`. With `--lang auto` (the default
when files are given), the language is picked from the file extension:
`.py` → python; `.js`, `.mjs`, `.cjs`, `.jsx` → js; `.c`, `.h`, `.cpp`,
`.cc`, `.cxx`, `.hpp`, `.hh` → c; `.go` → go. Reading from stdin requires
an explicit `--lang` (stdin has no extension to infer from). An unknown
extension with `--lang auto` is an error, not a silent guess.

### Output rules (all languages)

1. A line that consisted only of a comment (plus leading whitespace) is
   dropped entirely — it does not become a blank line. This matches the
   page's Step 2/3 examples, where comment-only lines vanish.
2. A line that had code before a comment keeps the code, with trailing
   whitespace stripped (e.g. `x = 1 # note` → `x = 1`).
3. A line that was originally blank stays blank.
4. For a block comment, code on the same line before `/*` and/or after `*/`
   is kept and joined on one line (e.g. `a /* x */ b` → `a  b`, then
   trailing whitespace stripped; interior double space is kept, not
   collapsed — this is not a minifier).
5. A multi-line block comment whose lines contain no code is dropped line
   by line, as in rule 1; code on the first/last line of the block is kept.
6. Line endings are normalised to `\n` (a CRLF input produces LF output).
7. The final output ends with a single trailing newline if the input had
   any output lines; empty output is empty (no newline invented).

### Step 4 — Go doc comments (Go only, on by default)

A comment group is preserved as a Go doc comment when it is immediately
followed — on the very next line, with no blank line in between — by a
line whose first token is one of `package`, `func`, `type`, `var`, or
`const`. This covers the common cases: a doc comment above a package
clause, a function, a type, or a grouped/single `var`/`const` declaration.
`import` is deliberately NOT in the list: the page links to Go doc-comment
rules, and import doc comments are rare; treating them as doc comments
would also preserve ordinary comments above imports. The rule is
line-based, not declaration-based: a comment above a `func` inside another
function (a local declaration) is also preserved, which is a safe
over-preservation, documented here rather than hidden.

Doc-comment detection works for both `//` groups (consecutive `//` lines
form one group) and `/* ... */` blocks. A preserved doc comment is emitted
verbatim (original text, original indentation), followed by the declaration
line it documents.

`--no-go-doc` disables this: all Go comments are then removed (except
tool directives, see Step 5).

### Step 5 — tool / linter configuration comments (on by default)

These comments are preserved verbatim, even when they would otherwise be
removed, in the languages the page names (Python and Go). For other
languages the same prefixes are preserved too, because the rule is
harmless there and simpler to reason about; this is a deliberate,
documented extension, not a page requirement.

Preserved when the comment text (after the marker, stripped of leading
whitespace) starts with one of:

- Python-style (`#`): `noqa`, `type:`, `pylint:`, `flake8:`, `fmt:`,
  `isort:`, `mypy:`, `coverage:`, `pyright:`, `ruff:`
  (covers the page's `# noqa: E731` and the usual `# type: ignore`,
  `# pylint: disable=...`, `# fmt: off/on/skip` forms).
- Go/C-style (`//`): `go:` (covers `//go:generate`, `//go:build`,
  `//go:embed`, and any other `//go:` directive), `+build`
  (the pre-`//go:build` build-constraint form `// +build ...`).
  Note: a `//go:` directive is recognised only when `go:` immediately
  follows `//` with no space (`// go:generate` is an ordinary comment
  and is removed — this matches Go's own directive rule).

`--no-keep-tool-comments` disables this preservation.

### Errors

- Unterminated block comment (`/*` with no closing `*/` before EOF):
  exit code 2, message on stderr naming the line where the block started.
  No partial output is written in this case.
- Unterminated string literal at end of input: treated as string content
  to EOF (the characters are kept), not an error — this mirrors how a
  tolerant filter behaves on truncated input, and is documented here
  because a real parser would reject it.
- Unknown language, unknown extension (with `--lang auto`), missing input
  file, or unreadable input: exit code 2 with a message on stderr.
- `--help` / `--version` exit 0.

## Deliberate divergences from the page

1. **No in-place editing.** The page describes a "tool to remove comments"
   without specifying in-place rewriting, so this build is a pure filter
   (stdin/files → stdout). Users can redirect output themselves.
2. **String-aware removal, beyond the page's examples.** The page's
   examples never show a comment marker inside a string, and its "simple
   regular expressions" route would mangle such code. This build uses a
   small hand-written scanner that tracks string state, so
   `"http://example.com"`, `'# not a comment'`, and `"/* not a comment */"`
   survive. This is strictly more correct than the page's minimum, and
   the cases where the scanner still differs from a real parser are
   listed under "Known limits" rather than hidden.
3. **Go doc-comment rule is line-based, not AST-based.** See Step 4 above.
   A full Go parser (not available in the Python standard library) would
   be needed to know exactly which comments `go doc` extracts. The
   next-line-declaration heuristic is the documented approximation.
4. **Tool-comment prefix list is wider than the page's two examples.**
   See Step 5 above. The page gives `noqa` and `//go:generate` /
   `//go:build` as examples ("comments such as"), not an exhaustive list,
   so a prefix list is a faithful reading; the exact list is pinned here
   so behaviour is testable.
5. **TypeScript is not a separate language.** `.ts`/`.tsx` are not mapped
   (the page says JavaScript). A TypeScript file can still be processed
   with `--lang js`, which handles its `//`/`/* */` comments and strings;
   type annotations are passed through untouched, since this tool only
   removes comments.
6. **Line-ending normalisation and comment-only-line dropping** are
   specified here (rules 1, 6) where the page only implies them via its
   examples.

## Known limits (NOT handled — honest scope limits)

- **Nested block comments are NOT supported.** `/* outer /* inner */`
  closes at the first `*/`, exactly as in C/Go/JavaScript. A remaining
  `*/` afterwards is passed through as code. (Some languages, e.g. Rust
  or Swift, nest block comments; they are not in scope.)
- **JavaScript regex literals are NOT recognised.** A regex such as
  `/\/*/` or `/http:\/\//` is scanned as code, so a `//` or `/*` inside
  a regex literal may be misread as a comment start. Distinguishing
  regexes from division requires expression-context parsing, which this
  scanner does not do.
- **JavaScript template-literal `${ ... }` expressions are NOT
  re-scanned.** The whole backtick literal, including `${ ... }`, is
  treated as string content, so a `//` comment inside an interpolation
  expression is preserved rather than removed.
- **C/C++ raw string literals (`R"(...)"`) are NOT recognised.** A `//`
  or `/*` inside a C++ raw string may be misread as a comment.
- **Python `#` inside a line continuation or implicit string
  concatenation** is handled by the same string scanner, so it is safe;
  but Python's `#` in a `#`-only "comment" inside an f-string expression
  (e.g. `f"{x # c}"`, legal in Python 3.12+) is NOT re-scanned: the
  f-string body is treated as string content and the comment is kept.
- **Go build constraints in block comments** (`/* +build ... */`) are
  not treated as directives; only `//`-form directives are preserved
  under Step 5.
- **Preprocessor lines in C/C++** (`#include`, `#define`, ...) are passed
  through untouched; `#` is not a comment marker in C mode.
- **Shebang lines** (`#!/usr/bin/env python3`) are ordinary Python
  comments to this tool and are removed like any `#` comment. (Keeping
  them would be a one-line special case, but the page does not ask for
  it, and silently special-casing the first line would be a divergence
  not requested by the page.)
- **Comment markers inside character escapes and other pathological
  literals** beyond the documented string handling (e.g. JS `'a\' // '`
  with a line-continuation backslash) follow the scanner's escape rule
  and may differ from a real parser in edge cases; the test suite pins
  the implemented behaviour.

## Not built

- "Going Further": support for more languages, minification, obfuscation
  (whitespace removal / identifier renaming).
- Any in-place file rewriting, backup files, or directory recursion.
- Any network access, configuration files, or per-project settings.
- The page's suggestion to test against the Coding Challenges Shared
  Solutions repo: no external code was fetched; tests use fixtures
  written for this project (see TEST_PLAN.md).

## CLI (summary; `ccremover.py --help` is authoritative)

```
ccremover.py [--lang python|js|c|go|auto] [--go-doc|--no-go-doc]
             [--keep-tool-comments|--no-keep-tool-comments]
             [FILE ...]
```

No FILE arguments → read stdin (requires explicit `--lang`).
One or more FILEs → each is processed in order to stdout.
Exit 0 on success, 2 on usage/input/scan errors.

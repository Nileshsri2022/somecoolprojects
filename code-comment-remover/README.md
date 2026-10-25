# Code Comment Remover

Strip comments from source files. A Python 3 standard-library-only CLI
filter: one file, `ccremover.py`, no dependencies, no installation.

Challenge: [Build Your Own Code Comment Remover](https://codingchallenges.fyi/challenges/challenge-code-comment-remover/)
(Coding Challenges, Steps 0–5). Full contract, divergences, and known
limits: see `docs/SPEC.md`; design: `docs/DESIGN.md`; test plan:
`docs/TEST_PLAN.md`.

## Supported languages

| Language | Comments removed | Preserved |
|---|---|---|
| Python (`--lang python`) | `#` to end of line | `# noqa`, `# type:`, `# pylint:`, `# flake8:`, `# fmt:`, `# isort:`, `# mypy:`, `# coverage:`, `# pyright:`, `# ruff:` |
| JavaScript (`--lang js`) | `//`, `/* ... */` | `//go:` / `// +build` forms (harmless here; same rule as Go) |
| C/C++ (`--lang c`) | `//`, `/* ... */` | same as JavaScript |
| Go (`--lang go`) | `//`, `/* ... */` | Go doc comments (comment group directly above `package`/`func`/`type`/`var`/`const`), plus `//go:generate`, `//go:build`, `//go:embed`, `// +build` |

Comment markers inside string literals are **not** treated as comments
(`"http://example.com"`, `'# not a comment'`, `` `template // text` ``
all survive). Comment-only lines disappear entirely (no blank line
left behind); originally blank lines are preserved.

## Usage

```sh
# stdin (language required — stdin has no extension to infer from)
python3 ccremover.py --lang python < input.py

# files (language inferred from extension; multiple files concatenate)
python3 ccremover.py app.js lib.js
python3 ccremover.py --lang go main.go

# options
python3 ccremover.py --no-go-doc --lang go main.go
python3 ccremover.py --no-keep-tool-comments --lang python app.py
python3 ccremover.py --help
```

Exit codes: 0 on success, 2 on usage/input errors and on an
unterminated block comment (reported with its start line, no partial
output). There is **no in-place option**: this is a pure filter, so
redirect output yourself (`... > stripped.py`). The challenge page
never asks for in-place rewriting.

## Examples

Python (Step 1):

```
# this is a comment
l = [x for x in range(10)] # this is also a comment
```

becomes:

```
l = [x for x in range(10)]
```

JavaScript / C (Steps 2–3) — the challenge's factorial example, with
all comment-only lines removed and code kept, is covered verbatim by
the fixtures in `tests/fixtures/factorial.js` and `factorial.c`.

Go (Steps 4–5): doc comments above declarations and `//go:generate` /
`//go:build` directives are kept; ordinary comments are removed
(see `tests/fixtures/factorial.go`).

## Known limits (honest scope limits, see SPEC.md)

- Block comments do **not** nest: `/* a /* b */` closes at the first `*/`.
- JavaScript regex literals are not recognised: a `//` or `/*` inside
  one may be misread as a comment.
- `//` inside a JavaScript template-literal `${ ... }` expression is
  preserved, not removed (the whole template literal is treated as a
  string).
- C++ raw strings (`R"(...)"`) are not recognised.
- Shebang lines are removed like any other Python `#` comment.
- "Going Further" (more languages, minification, obfuscation) is not built.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

48 tests, all passing: the challenge's factorial examples verbatim,
string-tricky cases, Go doc/directive rules, tool-comment rules, CLI
behaviour (stdin, extension inference, error exits), and fixtures in
`tests/fixtures/` (each input file beside its `.expected` output).

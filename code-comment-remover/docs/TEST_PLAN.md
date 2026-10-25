# Code Comment Remover — TEST_PLAN

## Runner

```
python3 -m unittest discover -s tests -v
```

from the project directory. Standard library `unittest` only; no
third-party test dependencies. Tests import `ccremover` by path (the
test module inserts the project directory into `sys.path`), so the
suite runs without installing anything.

## Coverage map

Tests live in `tests/test_ccremover.py` and exercise the public
functions `strip_source(text, lang, ...)` and the CLI entry point
(`main(argv)` with captured stdout/stderr), plus the fixture files in
`tests/fixtures/`.

| Area | What is tested |
|---|---|
| Python Step 1 | Full-line `#` comment removed; trailing `#` comment removed, code kept, trailing space stripped; `#` inside single, double, triple-quoted strings kept; escaped quote inside string; raw string with `#`; `#` inside an f-string kept; blank lines preserved; comment-only lines dropped (no blank line left) |
| JS Step 2 | The page's factorial example, verbatim input → verbatim expected output; `//` and `/* */` (single- and multi-line); block comment joining code on both sides; `//` and `/* */` inside string literals kept; nested block comment closes at first `*/` (documented limit, pinned by a test) |
| C Step 3 | The page's factorial example, verbatim input → verbatim expected output; char literal `'/'` and `'"'` handling; `//` inside a string kept |
| Go Step 4 | Doc comment above `package` / `func` / `type` kept; ordinary comment above a blank line or above non-declaration code removed; doc comment above `var`/`const` kept; `/* */` doc block above a function kept; `--no-go-doc` removes doc comments |
| Go/Python Step 5 | `# noqa: E731` kept; `# type: ignore` kept; `//go:generate`, `//go:build ignore` kept; `// +build linux` kept; `// go:generate` (with a space) removed; `--no-keep-tool-comments` removes them |
| Edge cases | Unterminated block comment → error naming the start line; unterminated string kept to EOF (documented tolerance); empty input → empty output; input with only comments → empty output; CRLF input → LF output; `a /* x */ b` joining; comment markers at EOF without newline |
| CLI | stdin mode requires `--lang`; file mode with `--lang auto` infers from extension; unknown extension errors (exit 2); missing file errors (exit 2); multiple files concatenated in order; `--help` exits 0; no in-place option exists (argparse rejects `--in-place`) |
| Fixtures | `tests/fixtures/` holds the page's factorial examples as files (Python, JS, C, Go) plus a strings-tricky file per language; the suite runs the stripper over each fixture and compares against the expected output stored beside it (`.expected` files) |

## Cases deliberately NOT asserted as correct parser behaviour

- JS regex literals containing comment markers, JS `${}` interpolation
  comments, C++ raw strings, and Python 3.12+ f-string-expression
  comments: where the implementation differs from a real parser, the
  test pins the *implemented* behaviour and the test name/docstring
  says so (e.g. `test_js_regex_literal_is_a_known_limit`), so a
  future fix changes the test deliberately, not silently.
- Go doc-comment detection for declarations the heuristic misses
  (e.g. a doc comment above a method with a receiver, where the line
  starts with `func` — actually covered, since the first token is
  still `func`; a doc comment above a `//`-commented-out declaration
  is not covered and not tested as kept).

## Manual checks (done by the builder, not in the suite)

- Run the tool on its own source file (`python3 ccremover.py --lang
  python ccremover.py`) and confirm the output still parses
  (`python3 -m py_compile` on the stripped output is expected to fail
  only where docstrings/comments were load-bearing — in practice the
  tool's own module docstring is a string, not a comment, so it
  survives; the check is eyeballed, not asserted).
- Run the tool over the fixture files via the CLI (not just the
  library function) and diff against `.expected` files.

## Pass criteria

Full suite green: 0 failures, 0 errors. Skips: none expected; any skip
must name its reason in the test and be reported as a skip, not hidden.

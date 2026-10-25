# DESIGN — JSON Validator And Prettier

## Files

- `json_pretty.py` — everything: argument parsing, validation, pretty-print,
  sort, compress, YAML emission, CLI. One file, Python 3 standard library
  only (`argparse`, `json`, `sys`).
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md` — this documentation.
- `tests/test_json_pretty.py` — `unittest` suite, run with
  `python3 -m unittest discover -s tests -v` from the project directory.

No helpers were needed: the YAML emitter and the compressor are each one
small, self-contained function, and splitting them out would only add
import plumbing.

## Pipeline

```
read text (file / stdin, UTF-8)
  → validate: json.loads with parse_constant rejected (NaN/Infinity)
  → on JSONDecodeError: report message + line/column + source line + caret
  → on success: optionally sort keys recursively
  → emit: pretty (json.dumps, indent=N, ensure_ascii=False)
          | compress (token-level strip of the ORIGINAL text)
          | yaml (own emitter, step = N)
```

Validation always happens first, even for `--compress` and `--yaml`: an
invalid document never produces transformed output, per Step 2 of the page.

## Why `json` for parsing, and what is still original here

`json.loads` gives a correct, well-tested parser plus error positions
(`JSONDecodeError.msg`, `.lineno`, `.colno`) for free. The page's own
prerequisite pointer and the existing hand-written `json-parser` project in
this series make a second hand-written parser redundant work, not a feature.
What this tool implements itself:

- Error reporting: the `message at line L, column C` line plus the source
  line and caret. `json` reports the column of the offending token; the
  caret points exactly there. If the reported line is past the end of the
  input (e.g. unclosed input), the last line is shown and the caret sits at
  its end.
- Sorting: `sort_value()` walks the parsed value recursively, rebuilding
  each dict with keys in Python's default (Unicode code-point) order and
  leaving array order untouched. Sorting is by the decoded string, so
  `"Z"` sorts before `"a"` and `"\u00e9"` sorts by its character, not by
  its escape spelling.
- Compression: `compress_json()` is a character scanner over the original
  text, not a re-serialization. Outside a string it drops every whitespace
  character; inside a string it copies characters verbatim, honouring `\`
  escapes (a `\` copies itself and the next character unconditionally, so
  an escaped quote `\"` never ends the string, and `\\` never leaks an
  escape). Because the input was already validated, the scanner cannot hit
  an unterminated string. This is what guarantees Step 4's requirement —
  whitespace inside strings, including spaces, tabs and literal newlines in
  the source text, survives byte-for-byte — where a `json.dumps(...,
  separators=(',', ':'))` re-serialization would normalize escape spellings
  and number spellings instead.
- YAML emission: `to_yaml()` / `yaml_scalar()` / `yaml_key()`, below.

## Pretty-print

`json.dumps(value, indent=indent, sort_keys=False, ensure_ascii=False)`.
Sorting is done beforehand by `sort_value()` when `--sort` is given, rather
than by `sort_keys=True`, so the same sorted value feeds the YAML emitter
too and the two modes cannot disagree. Separators default to `(',', ': ')`
under `indent`, matching the page's example (`"name": "John",`).

## YAML emitter

`to_yaml(value, indent_step)` returns a list of lines (no trailing newline;
the CLI adds one).

- Dict: one `key: value` line per entry. A scalar value goes on the same
  line; a non-empty dict/list value puts the key alone on its line and the
  nested block one step deeper; an empty dict/list goes on the same line
  as `{}` / `[]`.
- List: one `- ...` line per item, at the current indent. A scalar item goes
  on the dash line. A dict item puts its first entry on the dash line
  (`- name: John`) and the rest indented one step past the dash, aligned
  with that first key. A list item puts its first inner item on the dash
  line only when the inner item is a scalar (`- - a` is avoided: nested
  lists instead start a fresh block one step deeper, i.e. `-` alone followed
  by indented `- ...` lines — simpler to read and unambiguous).
- Scalars: `True` → `true`, `False` → `false`, `None` → `null`,
  `int` → decimal, `float` → `repr` (so `9.5` stays `9.5`, `100.0` stays
  `100.0`); note `bool` is checked before `int`, since `bool` subclasses
  `int` in Python.
- String quoting (`yaml_scalar`): a string is emitted plain only if it is
  non-empty, has no leading/trailing whitespace, does not start with an
  indicator character (`- ? : , [ ] { } # & * ! | > ' " % @ \``), contains
  none of `{ } [ ] , & * # ? | > @ \`` or `"` anywhere, contains no `: `
  or ` #` and does not end with `:`, contains no control characters or
  newlines, and does not look like a non-string scalar (`true`, `false`,
  `null`, `~`, `yes`/`no`/`on`/`off`, or a number). In practice the rule is
  conservative: any doubt → double-quoted with `json.dumps` escaping, which
  is valid YAML double-quoted style. This over-quotes a few strings a YAML
  expert would leave plain (e.g. a string containing `#` without a
  preceding space); over-quoting is safe, under-quoting corrupts data, so
  the bias is deliberate. Interior hyphens and apostrophes stay plain
  (`well-known`, `don't`), since plain YAML allows them mid-word.
- Keys use the same rule as string scalars, except an empty key becomes
  `""`. Non-string keys cannot occur: JSON object keys are always strings.
- Top-level scalar: emitted as a single line. Top-level empty dict/list:
  a single `{}` / `[]` line.

## Error locations

`json.JSONDecodeError` already carries `lineno`/`colno` (1-based). The
report prints:

```
Invalid JSON: Expecting ',' delimiter at line 1, column 18
{"name": "John" "job": "software engineer"}
                 ^
```

Column 18 is where `json` stopped; the caret is placed under that column
of the source line. Two known `json`-module quirks are documented, not
hidden: for a trailing comma, the error points at the `}` that follows the
comma; for a missing value such as `{"a": }`, it points at the `}`. Both
still identify the fault to a human reader, and the tests pin the exact
messages.

## Exit-code contract

0 = valid, output written. 1 = invalid JSON (message + caret on stderr).
2 = usage/IO error (argparse handles unknown flags and bad `--indent`
values with its own exit-2 message; file-read failures and the
`--compress --yaml` conflict print a short error and exit 2). This split
lets scripts distinguish "bad document" from "bad invocation".

## Assumptions and limits (see also SPEC)

- Input is UTF-8; undecodable bytes are an IO error (exit 2), not a
  "invalid JSON" verdict, because the failure is in reading, not parsing.
- Extremely deep nesting hits Python's recursion limit in `json.loads`
  itself (a `RecursionError`, reported as invalid JSON with a plain message
  rather than a traceback) and in `sort_value`/`to_yaml`; no depth cap is
  imposed beyond that, matching `json`'s own behaviour.
- No YAML round-trip verification is possible with the standard library
  alone (there is no YAML parser in it); the YAML tests therefore assert
  exact output for the page's examples plus quoting/edge cases.
- No clipboard, dark mode, web UI, or schema validation (see SPEC §
  divergences).

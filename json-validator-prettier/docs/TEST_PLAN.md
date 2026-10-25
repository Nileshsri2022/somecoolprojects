# TEST_PLAN — JSON Validator And Prettier

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

The suite is `tests/test_json_pretty.py`, `unittest` only, no network, no
files outside a temporary directory for the CLI file-input tests. It tests
both the library functions (`validate`, `sort_value`, `compress_json`,
`to_yaml`, `format_error`) and the CLI end to end (stdin, file argument,
exit codes, stdout vs stderr separation).

## Cases

### Validation / pretty-print (Step 2, page examples verbatim)

1. Page valid example `{"name": "John", "job": "software engineer",
   "country": "United Kingdom"}` pretty-prints to the page's 2-space form.
2. Page missing-comma example is invalid; error names line 1 and the column
   of the second string; formatted output is absent; exit code 1.
3. Page trailing-comma example is invalid; error points at the `}`.
4. Minified valid JSON pretty-prints (multi-line, indented).
5. Empty input and whitespace-only input are invalid.
6. `NaN`, `Infinity`, `-Infinity` are invalid (not JSON, despite Python's
   `json` accepting them by default).
7. Single-quoted strings, unquoted keys, comments, and trailing content
   after the top-level value are invalid.
8. Top-level scalars and arrays validate and pretty-print (`42`, `"hi"`,
   `[1, 2]`).
9. Unicode passes through unescaped in pretty output.
10. Error report contains the offending source line and a `^` caret.

### Sort (Step 3, page examples verbatim)

11. `{"zebra": 1, "apple": 2, "banana": 3}` → apple, banana, zebra.
12. Nested example: both the top level and each nested object sorted.
13. Array order is NOT changed by sorting (only object keys).
14. `--sort` on already-sorted input is a no-op.

### Compress (Step 4, page example verbatim)

15. Page example: formatted input compresses to
    `{"name":"John","message":"Hello World"}` — inner space kept.
16. Tabs/newlines between structural tokens are removed.
17. Whitespace inside strings is preserved byte-for-byte, including a
    literal tab and a literal newline inside a string value, and an escaped
    quote `\"` does not end the string early.
18. Compress of invalid JSON fails validation first (exit 1, no output).
19. Original number/escape spellings survive compression (`1.50`, `\u0041`
    are untouched — token-level strip, not re-serialization).

### YAML (Step 5, page examples verbatim)

20. Simple object → `name: John` / `age: 30`.
21. Nested object + array → page's exact layout, list items one step below
    the owning key.
22. Mixed types → `active: true` / `count: 0` / `message: null` /
    `score: 9.5`.
23. Empty object/array → `{}` / `[]` on the key line.
24. Array of objects → first key on the dash line, rest aligned.
25. Strings that look like booleans/null/numbers (`"true"`, `"123"`) are
    quoted so they do not change type; strings containing `:` or `#` are
    quoted; empty string becomes `""`.
26. `--sort --yaml` emits sorted YAML; `--yaml` on invalid JSON exits 1.

### CLI behaviour

27. No file argument reads stdin; `-` also reads stdin; a file path reads
    that file; a missing file exits 2 with an error on stderr.
28. `--check` prints exactly `Valid JSON` on success and nothing on stdout
    for invalid input (error on stderr, exit 1).
29. `--indent 4` pretty-prints with 4 spaces; `--indent 0` / `--indent 9`
    / `--indent abc` exit 2.
30. `--compress --yaml` together exits 2 (contradictory modes).
31. `--help` exits 0 and mentions `--sort`, `--compress`, `--yaml`.
32. Output ends with exactly one trailing newline in every success mode.

## Not covered (honest gaps)

- YAML round-trip through a real YAML parser: no YAML library in the
  standard library, so exact-output assertions stand in for it.
- Interactive/paste UI behaviour: there is no UI; CLI stdin/file behaviour
  is what is tested.
- Performance or very large documents: no benchmark; the tool is linear
  except for the recursive sort/YAML walk.

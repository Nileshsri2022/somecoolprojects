# json-parser — Test plan

Run: `python3 -m unittest discover -s tests -v` from `json-parser/`.

Tests do two things:

1. CLI subprocess tests: run `json_parser.py <file>`, assert
   exit 0 + `Valid JSON` on stdout for valid inputs, and exit 1
   + `Invalid JSON` on stderr for invalid inputs.
2. `parse()` value tests: import `json_parser`, call `parse()`,
   assert the returned Python value equals the expected value
   (dict, list, str, int, float, True, False, None). This checks
   the parser actually understood the document, not just that
   it did not crash.

No test compares against `json.loads`. Expected values are
hand-written in the test file.

## Valid cases (must exit 0)

Step 1: `{}`
Step 2: `{"key": "value"}`, `{"key": "value", "key2": ""}`
Step 3: `{"key1": true, "key2": false, "key3": null,
"key4": "value", "key5": 101}`, plus `101.5`, `-0`, `-12.5e-3`,
`1e10`, `0`, `0.1`
Step 4: nested objects and arrays, `[]`, `{}`, `{"a": [1, 2,
{"b": []}]}`, `[[[[1]]]]`
Step 5 (own): string escapes `\"`, `\\`, `\/`, `\b`, `\f`,
`\n`, `\r`, `\t`, `\u0041` (= `A`), surrogate pair for an
emoji, empty string `""`, top-level array `[1, "a", true, null]`,
top-level string, top-level number, whitespace around the
document (spaces, tabs, newlines).

## Invalid cases (must exit 1, with a useful message)

- Empty input, whitespace-only input.
- `{`, `}`, `[`, `{"key": "value"`, `{"key": "value",}`,
  `[1, 2,]`, `{"key" "value"}`, `{"key": }`, `{key: "value"}`,
  `{'key': 'value'}`, `{"key": 'value'}`.
- `{"key": "value"} extra`, `{} {}`, `{"a": 1} {"b": 2}`.
- Numbers: `01`, `+1`, `1.`, `.5`, `1e`, `1e+`, `-`, `NaN`,
  `Infinity`.
- Literals: `tru`, `truex`, `nul`, `fals`, `True`, `NULL`.
- Strings: unterminated `"abc`, control character inside a
  string (raw newline in a string), bad escape `\x`, bad
  unicode `\u12`, `\uZZZZ`, lone high surrogate `\uD83D`
  with no low surrogate following.
- Arrays/objects with missing commas: `[1 2]`, `{"a": 1 "b": 2}`.

## What is NOT tested

- The challenge's Dropbox test files and the json.org
  JSON_checker zip: neither is a stable, fetchable fixture
  from this environment, and the cases above cover every rule
  those suites exercise at challenge scope.
- Performance on huge documents: the parser is in-memory by
  design (see SPEC.md out-of-scope).

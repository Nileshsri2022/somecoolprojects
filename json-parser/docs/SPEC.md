# json-parser — Specification (docs first)

Source: Coding Challenges, "Build Your Own JSON Parser"
(https://codingchallenges.fyi/challenges/challenge-json-parser/)
Target in this repo: `somecoolprojects/json-parser/`
Original format reverse-engineered by behaviour only: RFC 8259 JSON,
as described on json.org and in the challenge steps. No original
parser source was copied.

## Goal

Build a JSON parser that validates a JSON document and reports
valid or invalid, with exit code 0 for valid and 1 for invalid.
Parsing is broken into two stages, as the challenge describes:

- Lexical analysis: divide characters into tokens.
- Syntactic analysis: match the token list against a formal grammar.

## Commands

```
python3 json_parser.py file.json
python3 json_parser.py < file.json    # via stdin, see below
```

- One file argument: parse that file.
- No file argument: parse stdin. This is an extension beyond the
  challenge (which only specifies a file), added so the tool composes
  with pipes like `ccwc` does. It does not change any file behaviour.
- Valid: print `Valid JSON` to stdout, exit 0.
- Invalid: print `Invalid JSON: <reason> at line L, column C` to
  stderr, exit 1. The challenge says "report to the standard output
  stream a suitable message" — valid output is on stdout as specified;
  error output on stderr is the conventional CLI split (errors from
  `ccwc` already go to stderr in this repo), and the exit code is
  the machine-readable signal the challenge tests rely on.

## Challenge steps

- Step 1: parse `{}` as valid, and an invalid file as invalid.
  A very simple lexer and parser is enough here.
- Step 2: object with string keys and string values, e.g.
  `{"key": "value"}`.
- Step 3: object with string, numeric, boolean, and null values, e.g.
  `"key1": true, "key2": false, "key3": null, "key4": "value",
  "key5": 101`.
- Step 4: object and array values, including empty objects and
  arrays, e.g. `"key-o": {}, "key-l": []`.
- Step 5: own tests for valid and invalid JSON, with useful error
  messages, then the json.org JSON_checker test suite if available.

## Grammar (RFC 8259, challenge scope)

```
value     := object | array | string | number | true | false | null
object    := '{' [ string ':' value (',' string ':' value)* ] '}'
array     := '[' [ value (',' value)* ] ']'
string    := '"' (unescaped | escape)* '"'
escape    := '\"' | '\\' | '\/' | '\b' | '\f' | '\n' | '\r' | '\t'
             | '\u' hex hex hex hex
number    := '-'? ( '0' | [1-9][0-9]* ) ( '.' [0-9]+ )?
             ( [eE] [+-]? [0-9]+ )?
whitespace:= ' ' | '\t' | '\n' | '\r'   (only between tokens)
```

Top level: the challenge steps only require objects at the top
level, but the implementation accepts any single `value` at the
top level (array, string, number, literal). That is RFC-correct,
and it still passes every object step. After the top-level value
only whitespace may follow; trailing content is invalid.

## Validity rules enforced

- Strings: double quotes only, no unescaped control characters
  (U+0000–U+001F) inside a string, no unterminated string, only the
  escapes listed above, `\u` must have exactly four hex digits.
  Surrogate pairs (`\uD83D\uDE00`) are combined into one code point;
  a lone surrogate is rejected.
- Numbers: no leading `+`, no leading zeros (`01` is invalid),
  no trailing dot (`1.` invalid), no missing digits after `.` or
  after `e`/`E`, no bare `-`, no `NaN`/`Infinity` (not JSON).
- Literals: exactly `true`, `false`, `null`, not followed by a
  letter or digit (`tru`, `truex`, `nul` are invalid).
- Objects: keys must be strings, `:` required, no trailing comma,
  no missing value, no missing closing `}`.
- Arrays: no trailing comma, no missing closing `]`.
- Empty input is invalid. A single top-level value followed by
  another value (e.g. `{} {}`) is invalid.

Duplicate object keys: RFC 8259 says names SHOULD be unique but
does not make duplicates invalid. The parser accepts them, last
value wins, like Python's `dict`. This is documented, not a bug.

## Out of scope (ponytail: smallest change that solves the challenge)

- No pretty-printing, no JSON output, no schema validation.
  The tool validates only; `parse()` returns the Python value
  for tests, but the CLI prints only Valid/Invalid.
- No streaming / incremental parsing of huge documents: the
  whole input is read, tokenised, and parsed in memory. That is
  the challenge's scope; `ccwc` streaming does not apply here.
- No non-standard extensions: no comments, no trailing commas,
  no single quotes, no unquoted keys.

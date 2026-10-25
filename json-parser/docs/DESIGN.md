# json-parser — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single file
   `json_parser.py`, same as `ccwc.py` in this repo. Reason:
   consistency across `somecoolprojects`, no build step, and
   the challenge allows any language. The standard library's
   own `json` module is NOT used for parsing — that would be
   the whole challenge. It is used only nowhere in the tool;
   tests compare against hand-computed expected values, not
   against `json.loads`, so a bug in this parser cannot be
   masked by the library.
2. Two stages, as the challenge teaches: a `Lexer` that turns
   text into a token list, then a `Parser` that consumes tokens
   by recursive descent. A single-pass character parser would be
   shorter, but the lexer/parser split is the learning point
   of this challenge, and it makes error positions clearer.
3. The CLI is a thin wrapper around `parse(text)`. Tests test
   both: `parse()` for the returned Python value, and the CLI
   subprocess for exit codes and messages.
4. Ask-matt / ponytail skill files: same status as for `ccwc` —
   ask-matt install was still running with no output, ponytail
   was never confirmed installed. The ponytail behavioural
   guidelines recorded in memory are applied anyway.

## Algorithm

### Lexer

Scan left to right, skipping whitespace between tokens. At each
position, dispatch on the next character:

- `{`, `}`, `[`, `]`, `:`, `,` — single-character tokens.
- `"` — read a string: consume characters until the closing
  `"`, handling escapes as they appear. Control characters
  are rejected. `\uXXXX` is validated as hex; a high surrogate
  must be followed by `\uDC00–\uDFFF`, and the pair is combined.
- `-` or digit — read a number with the grammar in SPEC.md.
  Validate the shape with a strict check (no leading zeros,
  fraction and exponent digits required when present), then
  convert with `int` (no fraction/exponent) or `float`.
- `t`, `f`, `n` — read `true`, `false`, `null` literally, and
  reject if the next character could continue an identifier.
- Anything else, or end of input inside a token — `JsonError`
  with the byte offset where the problem starts.

Each token carries its type, its value (for STRING/NUMBER),
and its start offset. At end of input the lexer appends EOF.

### Parser (recursive descent, one function per grammar rule)

```
parse_value():  dispatch on the next token type
parse_object(): '{' (STRING ':' parse_value (',' ...)*)? '}'
parse_array():  '[' (parse_value (',' ...)*)? ']'
parse():        value = parse_value(); expect EOF; return value
```

`expect(type)` consumes the token if it matches, otherwise
raises `JsonError` naming the expected token and the token found.
Because the lexer already validated strings and numbers, the
parser only has to check structure: token order, colons, commas,
and closing brackets. Trailing commas fail naturally: after a
comma the parser calls `parse_value` (or expects a string key),
and `}` / `]` is not a valid value start.

### Errors

`JsonError` carries a message and a character offset. The CLI
converts the offset to line/column by counting newlines before
it in the original text (line = newlines + 1, column = offset
- last-newline-offset). Messages name what was expected or what
was wrong, e.g. `expected ':'`, `unterminated string`,
`invalid number`, `trailing characters after top-level value`.

### File layout

```
json-parser/
  README.md            usage, examples, how to run tests
  json_parser.py       Lexer, Parser, parse(), CLI
  docs/
    SPEC.md            challenge spec and grammar
    DESIGN.md          this file
    TEST_PLAN.md       what is tested, and against what
  tests/
    test_json_parser.py  unittest, CLI subprocess + parse() values
```

## Success criteria

- `python3 -m unittest discover -s tests -v` passes.
- Steps 1–4 examples from the challenge all parse as valid.
- Every invalid case in TEST_PLAN.md exits 1 with a message
  naming the problem; no invalid case exits 0.
- No use of the `json` module in `json_parser.py` (checked by
  reading the file, and by construction: the parser is hand-written).

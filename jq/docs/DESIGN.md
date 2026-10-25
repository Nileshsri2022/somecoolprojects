# DESIGN — jq

## Assumptions (stated before coding, ponytail rules)

- Python 3 standard library only, single file `jq.py`. The JSON parser
  is written in this project from scratch (recursive descent); it does
  NOT import the `json-parser` project and does NOT use Python's `json`
  module for parsing or printing — printing is a hand-written
  serializer, so number-literal preservation and `jq`-style escaping
  are under our control.
- Evaluation is generator-based: every filter is a function
  `eval(node, value) -> iterator of values`. This makes pipes, commas,
  iterate, array/object construction, and `select`/`map` fall out
  naturally, with no special cases.
- One input document at a time; the CLI splits the input stream into
  documents with the same parser, then applies the filter to each.
- `jq`'s semantics are followed where they were cheap to verify
  against system `jq` 1.7 (installed on this machine): missing field →
  `null`; field access on the wrong type is an error unless `?` is
  present; `select` yields the input at most once; object `+` is a
  shallow merge; pipe binds looser than comma; `//` treats only
  `false`/`null` (and no output) as "empty". Where verification was
  ambiguous, the choice is recorded in the README divergences.

## Pipeline

```
input text --[JSON parser]--> Python value (dict/list/str/JqNumber/
                              bool/None, dicts keep insertion order)
filter text --[filter lexer]--> tokens
            --[recursive-descent parser, precedence per SPEC.md]-->
            AST (tuples: (kind, ...))
            --[evaluator, generator-based]--> output values
            --[serializer]--> stdout (pretty / -c / -r / --sort-keys)
```

## Key structures

- `JqNumber`: wraps a numeric value plus, for parsed numbers, the
  original literal text. Arithmetic creates a value-only `JqNumber`.
  Equality and ordering use the numeric value, so `1 == 1.0`.
- JSON parser: `JsonParser` over the raw string with an index, line/col
  tracking for error messages. Strict JSON: no trailing commas, no
  single quotes, no bare words, `\uXXXX` escapes with surrogate-pair
  combining, duplicate object keys keep the last value.
- Filter lexer: single pass producing tokens for `.`, identifiers,
  string literals (raw text retained for interpolation), numbers,
  operators (`| , : ; ? // == != <= >= < > + - * / %`), brackets and
  parentheses. Keywords `and`/`or` are identifiers recognised in the
  parser; function names are identifiers too.
- Filter parser: recursive descent following the precedence in
  SPEC.md. Suffixes (`.name`, `.[...]`, `.[]`, slices, `?`) attach to
  a `.` term; a bare identifier term is a builtin call or, with
  parentheses, a function call. String interpolation is handled at
  evaluation time: the string's raw text is scanned for balanced
  `\( ... )` spans, each span parsed as a filter and evaluated.
- Evaluator nodes: `ident`, `field`, `index`, `slice`, `iterate`,
  `opt` (catches `JqError` from its child and yields nothing), `pipe`,
  `comma`, `alt` (`//`), `and`/`or` (truthiness = not false/null),
  comparison, arithmetic, `array` (collect), `object` (cartesian
  product over multi-output keys/values), `call` (builtins),
  `literal`, `string` (with interpolation parts).
- Field access rules: on `None`, any access yields `None` (not an
  error); on a dict, a missing key yields `None`; on a list, a string
  key is an error; on any other type, access is an error. `?` turns
  an access error into no output. Iterate on `None` is an error
  (unless `?`); iterate on a dict yields its values in insertion
  order; on a list yields elements.
- Errors: `JqError` (runtime), `FilterSyntaxError` (compile),
  `JsonError` (input). The CLI maps them to exit codes 5 / 3 / 5.

## What was deliberately NOT built

- No `$` variables, no `def`, no `if/then/else`, no `..` recursion,
  no `reduce`/`foreach`, no `getpath`/`paths`, no `--slurp`/`-n`/
  `-e` flags, no modules. These are all real `jq`, but none is in the
  page's steps or the assigned subset; adding them would be
  speculative code. They are listed as divergences in the README.

# jq — Build Your Own jq

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A `jq` clone in a single Python file (standard library only) that
pretty-prints JSON and evaluates a filter subset: identity, field
access (`.name`, `.["name"]`, `.[n]`, slices `.[n:m]`), iterate (`.[]`),
pipes, commas, `//`, `and`/`or`, comparisons, arithmetic, array/object
construction, string interpolation, and the builtins `select`, `map`,
`length`, `keys`, `type`, `values`, `empty`, `not`, `has`, `tostring`,
`tonumber`. The JSON parser and serializer are hand-written in this
project (no `json` module, nothing imported from `json-parser`), so
parsed number literals print exactly as written (`1.0` stays `1.0`),
like system `jq`.

## Usage

```sh
python3 jq.py [-c] [-r] [--sort-keys] [filter] [file ...]
# no filter means '.'; no files means read stdin

curl -s 'https://dummyjson.com/quotes?limit=2' | python3 jq.py
curl -s 'https://dummyjson.com/quotes?limit=2' | python3 jq.py '.quotes'
curl -s 'https://dummyjson.com/quotes?limit=2' | python3 jq.py '[.quotes[].quote]'
echo '{"a":1,"b":2}' | python3 jq.py '.a, .b | .+10'
echo '[1,2,3,4]' | python3 jq.py '.[] | select(. % 2 == 0)'
echo '{"a":1}' | python3 jq.py -c .
echo '"hi"' | python3 jq.py -r .
```

Missing object fields print `null`; a `?` after an access (`.a?`,
`.["a"]?`, `.[]?`) suppresses type errors for that access. Exit
codes match observed system `jq` 1.7 behaviour: 0 ok, 3 filter
compile error, 5 input JSON error or filter runtime error, 2
unreadable input file.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover all page steps, the builtins, operators, flags, error
exit codes, and — where system `jq` is installed — a comparison
suite that runs both binaries on the same inputs and asserts
identical stdout (skipped automatically without `jq`).

## Divergences from real jq (honest list)

- No `$` variables, `def`, `if/then/else`, `..` recursion,
  `reduce`/`foreach`, `getpath`/`paths`, `--slurp`, `-n`, `-e`, or
  modules. These are under the page's "Going Further", not its steps
  or the assigned subset, so they were deliberately left out.
- Bare `[]` is iterate (as in `jq`), not an empty-array literal;
  use `[empty]` for the empty array.
- Error message wording differs from system `jq` (exit codes match).
- Numbers produced by arithmetic are formatted from their value
  (integral floats print without a fraction); only parsed literals
  keep their original text. Computed-float exponent formatting may
  differ from `jq` in case/sign details.
- `and`/`or` use truthiness (not `false`/`null`) rather than
  requiring booleans; this matches system `jq` for the cases tested
  (e.g. `1 and true` → `true`).

## Files

- `jq.py` — JSON parser, filter lexer/parser/evaluator, CLI.
- `docs/SPEC.md` — challenge spec and supported syntax.
- `docs/DESIGN.md` — pipeline and design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_jq.py` — the test suite.

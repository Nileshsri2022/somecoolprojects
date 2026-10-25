# TEST_PLAN — jq

Run: `python3 -m unittest discover -s tests -v` from the `jq/` directory.

## Coverage map

Page steps:
- Step 1: pretty print (no filter and `.`), stdin and file input,
  nested objects/arrays, empty input → no output.
- Step 2: `.[0]`, `.[1]`, negative index `.[-1]`, out-of-range → null.
- Step 3: `.name`, `.["name"]`, `.name?`, `.["name"]?`, nested
  `.a.b.c`, missing field → null, `?` suppressing a type error.
- Step 4: pipes, including `.a, .b | .c` binding (comma inside the
  left side of the pipe) and chained pipes.
- Step 5: `[.quotes[].quote]`-style collection, `.[]` on arrays and
  objects, `[]` collection of a multi-output filter.

Assigned subset / extras:
- Array/object construction: `[.a, .b]`, `{x: .a, y: .b}`,
  `{a}` shorthand, computed keys `{(.k): .v}`, multi-output values
  producing multiple objects.
- `select(f)` (truthy / falsy / multi-output → at most one input),
  `map(f)`, `length`, `keys`, `type`, `values`, `empty`, `not`,
  `has`, `tostring`, `tonumber`.
- Operators: comma, `//`, `and`/`or`, comparisons (including the
  cross-type order null < false < true < number < string < array <
  object), `+ - * / %` on numbers/strings/arrays/objects.
- String interpolation `"\(.name)"`.
- Slices `.[1:3]`, negative slice bounds.
- Flags: `-c`, `-r` (strings raw, `null` → `null`), `--sort-keys`.
- JSON parser errors (trailing data, bad number, unterminated
  string, trailing comma) and filter syntax errors, with exit codes
  5 and 3 respectively; runtime type errors exit 5.
- Number formatting: parsed literals preserved (`1.0`, `1.50`,
  `1e20` → `1E+20`); arithmetic results formatted from value.

## Comparison against system jq

Where system `jq` is installed, `tests/test_jq.py` additionally runs
both binaries on the same inputs/filters (class `TestAgainstSystemJq`,
skipped automatically when `jq` is not on PATH) and asserts identical
stdout for the shared subset: identity, field access, index, pipe,
collection, select, map, arithmetic, `//`, comparisons, `-c`, `-r`,
`--sort-keys`. Divergences found this way are recorded in the README,
not papered over in the tests.

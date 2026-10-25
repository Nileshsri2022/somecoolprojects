# SPEC — jq (Build Your Own jq)

Source page: https://codingchallenges.fyi/challenges/challenge-jq/
Slug used: `challenge-jq` — the first-guess URL worked, no 404, no
correction needed. The page's steps are implemented in full (Steps 0–5),
plus the small, explicitly listed extras below. Anything under the page's
"Going Further" that is not listed here is NOT implemented (see
Divergences in the project README).

## Page steps

- Step 0: the clone is `jq.py` (run as `python3 jq.py ...`).
- Step 1: pretty-print JSON. With no filter, or with the identity
  filter `.`, the input is printed pretty (2-space indent, like `jq`).
  Input comes from stdin or from file argument(s).
- Step 2: array index `.[<number>]` (zero-based; negative counts from
  the end, matching system `jq`).
- Step 3: object identifier `.name` and `.[<string>]`, plus the
  optional operator `?` (`.name?`, `.["name"]?`, and `.[n]?`, `.[]?`).
  Identifiers may be chained (`.a.b.c`) and nested arbitrarily.
  A missing object field yields `null`, exactly as in `jq`.
- Step 4: pipe `|` — the output(s) of the left filter feed the right
  filter. Pipe binds loosest: `.a, .b | .c` means `(.a, .b) | .c`
  (verified against system `jq` 1.7).
- Step 5: collect output as an array by wrapping a filter in square
  brackets, e.g. `[.quotes[].quote]`. This requires the iterate
  operator `.[]` (array elements, or object values), which is included.

## Filter language implemented (superset of the page steps)

```
filter   := pipe
pipe     := comma ("|" comma)*
comma    := alt ("," alt)*
alt      := orexpr ("//" orexpr)*
orexpr   := andexpr ("or" andexpr)*
andexpr  := cmpexpr ("and" cmpexpr)*
cmpexpr  := additive (("==" | "!=" | "<" | "<=" | ">" | ">=") additive)?
additive := multiplicative (("+" | "-") multiplicative)*
multi    := unary (("*" | "/" | "%") unary)*
unary    := "-" unary | term
term     := "." suffix* | literal | "(" filter ")"
          | "[" filter? "]"              (array construction;
                                           bare "[]" is iterate)
          | "{" object-body "}"          (object construction)
          | func-call | bare-func
suffix   := ".name" | ".[expr]" | ".[]" | "[expr]" | ".[n:m]"
          | "?" (marks the preceding access optional)
literal  := number | string (with "\(filter)" interpolation)
          | true | false | null
func-call:= name "(" filter (";" filter)* ")"
bare-func:= length | keys | type | values | empty | not | tostring
```

Builtins: `select(f)` (yields the input once if any output of `f` is
truthy, i.e. not `false`/`null` — verified against system `jq`),
`map(f)` (equivalent to `[.[] | f]`), `length`, `keys` (sorted keys /
array indices), `type`, `values`, `empty`, `not`, `has(key-or-index)`,
`tostring`, `tonumber`.

Operators: `+` (numbers, string concatenation, array concatenation,
shallow object merge — right-hand keys replace left-hand keys, verified
against system `jq`), `-` (numbers, array difference), `*` (numbers,
deep object merge), `/` (numbers), `%` (numbers, integral result).
Comparisons use `jq`'s total order: null < false < true < numbers <
strings < arrays < objects; `==` is deep equality (1 == 1.0).

## CLI

```
python3 jq.py [-c] [-r] [--sort-keys] [filter] [file ...]
```

- No filter → `.`. No files → read stdin. Several files are processed
  in order. Each JSON document in the input stream is filtered
  independently (concatenated documents, as `jq` does); empty input
  produces no output and exits 0.
- `-c`: compact output (one JSON value per line).
- `-r`: raw output — strings print without quotes; other values print
  as JSON (pretty unless `-c`). `null` prints as `null`.
- `--sort-keys`: sort object keys recursively on output.
- Exit codes (matching observed system `jq` 1.7 behaviour): 0 ok,
  3 filter compile error, 5 input JSON error or filter runtime error.
  Error messages go to stderr.

## Output formatting

- Pretty: 2-space indent; empty arrays/objects print as `[]` / `{}`.
- Parsed numbers keep their literal text (system `jq` prints `1.0` as
  `1.0` and `1.50` as `1.50`); a literal's exponent is normalised to
  `E±` form (`1e20` → `1E+20`), matching system `jq`. Numbers produced
  by arithmetic are formatted from their value: integral floats print
  without a fraction; other floats use Python `repr` with the exponent
  normalised to `E±` form.
- Strings are escaped as in `jq`: `"`, `\`, and control characters
  (`\n`, `\t`, `\r`, `\b`, `\f`, other controls as `\u00XX`);
  non-ASCII characters print as UTF-8, unescaped.

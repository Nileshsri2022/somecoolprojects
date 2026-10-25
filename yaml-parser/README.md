# yaml-parser — Build Your Own YAML Parser

Coding Challenge #67, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A hand-written YAML parser (Python 3 standard library only, no
PyYAML) that parses YAML text into Python data and prints it as
JSON. This parses YAML; it does not query it (that is the
separate `yq` challenge).

Supported subset: block mappings/sequences (arbitrarily nested,
including sequences of mappings), flow sequences `[1, 2]` and
flow mappings `{k: v}`, YAML 1.1 scalars (null, booleans
including `off`/`yes`/`no`/`on`, ints including `0x` hex and
legacy-octal `023332`, floats including `.inf`/`.NAN`),
single/double-quoted strings (quoted escapes translated, plain
strings not), folded (`>`) and literal (`|`) block scalars with
clip/strip/keep chomping, comments, and a leading `---` marker.

NOT full YAML: no anchors, aliases, merge keys, tags,
directives, multi-document streams, timestamps (kept as
strings), sexagesimal numbers, complex keys, or multi-line
plain scalars. Duplicate keys are rejected. See `docs/SPEC.md`
for the full honest scope, the resolved challenge URL, and
every divergence.

## Usage

```sh
python3 yaml_parser.py FILE        # parse FILE, print JSON (indent 2)
python3 yaml_parser.py              # read YAML from stdin
printf 'name: Coding Challenges\nchallenge:\n  name: YAML Parser\n' | python3 yaml_parser.py
```

Output for that example:

```json
{
  "name": "Coding Challenges",
  "challenge": {
    "name": "YAML Parser"
  }
}
```

Errors go to stderr as `yaml_parser.py: line N: <message>`
with exit code 1.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover all five challenge steps (simple nested mapping,
scalar typing, quoted/folded/literal strings, block and flow
collections, own tests + useful errors), plus CLI behaviour.

## Files

- `yaml_parser.py` — hand-written parser + CLI (single file).
- `docs/SPEC.md` — challenge spec, resolved URL, scope limits.
- `docs/DESIGN.md` — pipeline and design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_yaml_parser.py` — the test suite.

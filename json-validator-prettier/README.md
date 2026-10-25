# json-validator-prettier — Build Your Own JSON Validator And Prettier

Coding Challenges "Build Your Own JSON Validator And Prettier"
(<https://codingchallenges.fyi/challenges/challenge-json-validator>),
worked in `somecoolprojects/`. Docs first, then code — see `docs/`.

The challenge page shows a paste-in UI but explicitly allows a CLI tool,
so this build is a CLI: feed it JSON on stdin or from a file and it
validates, pretty-prints, sorts keys, compresses, or converts to YAML.

Distinct from the already-built `json-parser` (verdict-only, hand-written
parser) and `yaml-parser`: this tool parses with Python's `json` module
(the page itself cites the parser as a prerequisite) and its original work
is error-location reporting, recursive key sorting, a token-level
compressor that preserves string contents byte-for-byte, and its own YAML
emitter. No code was copied from those projects.

## Usage

```sh
python3 json_pretty.py [options] [file]
cat file.json | python3 json_pretty.py
echo '{"b": 1, "a": 2}' | python3 json_pretty.py --sort
echo '{"name": "John"}' | python3 json_pretty.py --yaml
echo '{ "a": 1 }' | python3 json_pretty.py --compress
python3 json_pretty.py --check file.json
```

| Option | Effect |
| --- | --- |
| (none) | Validate, then pretty-print (2-space indent). |
| `--check` | Verdict only: prints `Valid JSON`. |
| `--sort` | Sort object keys alphabetically at every level. |
| `--compress` / `--minify` | Remove all whitespace outside strings. |
| `--yaml` | Convert JSON to YAML. |
| `--indent N` | Indent width, 1–8 (default 2). |

`--sort` combines with `--yaml` and `--compress`. `--compress --yaml`
is rejected (exit 2). Note: `--sort --compress` re-serializes the sorted
value compactly, so original escape/number spellings are normalized in
that one combination; plain `--compress` preserves them byte-for-byte.

Exit codes: 0 = valid, 1 = invalid JSON (message + line/column + caret
on stderr, no output), 2 = usage or file error.

Invalid example:

```
$ echo '{"name": "John" "job": "x"}' | python3 json_pretty.py
Invalid JSON: Expecting ',' delimiter at line 1, column 18
{"name": "John" "job": "x"}
                 ^
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

## Files

- `json_pretty.py` — validation, error reporting, sort, compress, YAML
  emitter, CLI. Python 3 standard library only.
- `docs/SPEC.md` — challenge spec, output contract, divergences.
- `docs/DESIGN.md` — pipeline, compressor, YAML quoting rules, limits.
- `docs/TEST_PLAN.md` — test cases and honest gaps.
- `tests/test_json_pretty.py` — the test suite.

## Not built (honest list)

- No web/paste-in UI (CLI instead, as the page allows); no dark mode.
- No copy-to-clipboard (no meaning for a CLI without a platform tool).
- No JSON Schema validation — the page asks for syntax validation only.
- YAML output is not round-trip verified through a real YAML parser:
  the standard library has no YAML parser, so tests assert exact output
  for the page's examples plus quoting and edge cases.

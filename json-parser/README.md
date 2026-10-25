# json-parser — Build Your Own JSON Parser

Coding Challenges #2, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

## Usage

```sh
python3 json_parser.py file.json
cat file.json | python3 json_parser.py
```

Valid input prints `Valid JSON` and exits 0. Invalid input
prints `Invalid JSON: <reason> at line L, column C` to stderr
and exits 1.

The parser is hand-written: a lexer (characters to tokens)
plus a recursive-descent parser (tokens to a Python value).
It does not use Python's `json` module.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests check both the CLI exit codes and the parsed Python
values returned by `parse()`.

## Files

- `json_parser.py` — Lexer, Parser, `parse()`, CLI.
- `docs/SPEC.md` — challenge spec and grammar.
- `docs/DESIGN.md` — algorithm, assumptions, file layout.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_json_parser.py` — the test suite.

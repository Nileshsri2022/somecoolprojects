# grep — Build Your Own grep

Coding Challenges #9, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Search input lines for a regular expression (Python `re`,
ERE-like), printing each matching line. Supports the options
on the challenge page only: `-r` (recurse), `-v` (invert),
`-i` (ignore case).

## Usage

```sh
python3 grep.py "" tests/fixtures/test.txt
python3 grep.py J tests/fixtures/rockbands.txt
python3 grep.py -r Nirvana tests/fixtures
python3 grep.py -r Nirvana tests/fixtures | python3 grep.py -v Madonna
python3 grep.py '\d' tests/fixtures/test-subdir/BFS1985.txt
python3 grep.py '\w' tests/fixtures/symbols.txt
python3 grep.py ^A tests/fixtures/rockbands.txt
python3 grep.py na$ tests/fixtures/rockbands.txt
python3 grep.py -i A tests/fixtures/rockbands.txt
cat tests/fixtures/rockbands.txt | python3 grep.py Nirvana
python3 grep.py -ri nirvana tests/fixtures
python3 grep.py -- -v tests/fixtures/rockbands.txt
```

Exit codes: 0 match found, 1 no match, 2 error (missing
file, directory without `-r`, invalid pattern, bad usage).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests check the challenge page's examples exactly, and
compare stdout bytes and exit codes against system
`grep -E` on the same fixtures (Python `re` is ERE-like),
plus error cases. Recursive comparisons sort output
lines first: GNU walks in readdir order, this tool in
sorted name order.

## Files

- `grep.py` — argument parsing, recursion, matching, CLI.
- `docs/SPEC.md` — challenge spec and divergences from GNU grep.
- `docs/DESIGN.md` — assumptions and structure.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_grep.py` — the test suite.
- `tests/fixtures/` — test files modelled on the page's examples.

# ccwc — Build Your Own wc Tool

Coding Challenges #1, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

## Usage

```sh
python3 ccwc.py -c file.txt
python3 ccwc.py -l file.txt
python3 ccwc.py -w file.txt
python3 ccwc.py -m file.txt
python3 ccwc.py file.txt        # default: lines, words, bytes
cat file.txt | python3 ccwc.py -l
python3 ccwc.py a.txt b.txt     # plus a total line
```

Options: `-c` bytes, `-l` lines (`\n` count), `-w` words,
`-m` characters (UTF-8 code points).

One deliberate difference from GNU `wc`: in a C locale system
`wc -m` equals `-c`. `ccwc -m` always counts UTF-8 characters.
See `docs/SPEC.md` for why, and `docs/TEST_PLAN.md` for how
`-m` is tested.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests run `ccwc.py` as a subprocess and compare against system
`wc`, except `-m`, which is compared against hand-computed
code-point counts (see above).

## Files

- `ccwc.py` — the tool, Python 3 stdlib only, streaming.
- `docs/SPEC.md` — challenge spec and observed `wc` behaviour.
- `docs/DESIGN.md` — algorithm, assumptions, file layout.
- `docs/TEST_PLAN.md` — test cases and oracles.
- `tests/test_ccwc.py` — the test suite.

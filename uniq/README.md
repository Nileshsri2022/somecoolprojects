# uniq — Build Your Own uniq Tool

Coding Challenges #10, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Filters adjacent duplicate lines: one copy of each
run of identical lines is written out. Non-adjacent
repeats are left alone (sort first if you want them
collapsed).

## Usage

```sh
python3 uniq.py test.txt
python3 uniq.py -c test.txt
python3 uniq.py -d test.txt
python3 uniq.py -u test.txt
python3 uniq.py -c -d test.txt
cat test.txt | python3 uniq.py -
cat test.txt | python3 uniq.py - out.txt
```

Options: `-c`/`--count` (prefix each line with its
run size, GNU-style width-7 field), `-d`/`--repeated`
(only repeated lines), `-u`/`--unique` (only lines
occurring once). Options combine; `-d` with `-u`
prints nothing, matching GNU uniq. Input `-` or
absent means stdin; a second argument is an output
file, otherwise stdout.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests compare output byte-for-byte against system
uniq (GNU coreutils 9.4) on the same fixtures for
default, `-c`, `-d`, `-u` and combinations, plus
stdin/file/output-file modes, byte fidelity (CRLF,
no trailing newline, non-UTF-8), and error cases.

## Files

- `uniq.py` — streaming byte filter, CLI.
- `docs/SPEC.md` — challenge spec and GNU
  tie-breakers.
- `docs/DESIGN.md` — assumptions, streaming design.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_uniq.py` — the test suite.

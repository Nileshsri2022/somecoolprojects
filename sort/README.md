# sort — Build Your Own Sort Tool

Coding Challenges #6, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Sort lines lexicographically (byte order, C locale),
with unique and random-sort modes and four selectable
sorting algorithms.

## Usage

```sh
python3 ssort.py words.txt
python3 ssort.py -u words.txt
python3 ssort.py --algorithm quick words.txt
python3 ssort.py --algorithm radix words.txt
python3 ssort.py -R words.txt
python3 ssort.py -R -u words.txt
cat words.txt | python3 ssort.py
python3 ssort.py - < words.txt
# challenge step 1 pipeline:
python3 ssort.py words.txt | uniq | head -n5
```

Algorithms: `merge` (default, stable), `quick`
(iterative, median-of-three), `heap`, `radix` (LSD
over bytes, stable). Random sort hashes each line
with a fresh random salt per run and sorts by hash,
so equal lines stay together.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests check every algorithm against Python's
`sorted()`, and CLI output against system `sort`
under `LC_ALL=C`, plus unique, random, stdin,
multi-file, and error cases.

## Files

- `ssort.py` — algorithms, random sort, CLI.
- `docs/SPEC.md` — challenge spec and sorting order.
- `docs/DESIGN.md` — algorithm implementations.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_ssort.py` — the test suite.

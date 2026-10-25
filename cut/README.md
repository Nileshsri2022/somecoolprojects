# cut — Build Your Own cut Tool

Coding Challenges #4, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Field mode only: select fields from each line, split on a
delimiter (tab by default).

## Usage

```sh
python3 ccut.py -f2 sample.tsv
python3 ccut.py -f1 -d, fourchords.csv
python3 ccut.py -f1,2 sample.tsv
python3 ccut.py -d, -f"1 2" fourchords.csv
tail -n5 fourchords.csv | python3 ccut.py -d, -f"1 2"
python3 ccut.py -d, -f2 - < fourchords.csv
# pipeline (challenge step 5):
python3 ccut.py -f2 -d, fourchords.csv | uniq | wc -l
```

Field list: `N`, `N-M`, `N-`, `-M`, separated by commas
and/or whitespace. Fields are numbered from 1. Output
fields are joined by the delimiter, in line order,
duplicates collapsed. A line without the delimiter is
printed whole.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests compare output against system `cut` on the same
fixtures, plus error cases.

## Files

- `ccut.py` — field-list parsing, line cutting, CLI.
- `docs/SPEC.md` — challenge spec and GNU-checked behaviour.
- `docs/DESIGN.md` — algorithm, assumptions, file layout.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_ccut.py` — the test suite.

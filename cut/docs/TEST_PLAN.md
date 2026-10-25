# cut — Test plan

Run: `python3 -m unittest discover -s tests -v` from `cut/`.

Two kinds of tests:

1. Function tests: import `ccut`, call `parse_field_list`
   and `cut_line` directly, assert sets / output bytes.
2. CLI tests: run `ccut.py` and system `cut` on the same
   fixture files and stdin, assert byte-identical output.
   System `cut` is the oracle here, as system `wc` was
   for `ccwc`. If system `cut` is absent, the CLI tests
   that need it are skipped, not failed.

## Fixtures

- `sample.tsv` (challenge step 1 shape):
  `f0\tf1`, `0\t1`, `5\t6`, `10\t11`, ...
- `fourchords.csv` (challenge step 2 shape, a few rows):
  `Song title,Artist` / `"10000 Reasons (Bless the Lord)",Matt Redman ...`
- Edge fixture: `a\tb\tc\td`, `x` (no delimiter),
  `p\tq`, empty line, `a,,c` (comma variant).

## Cases, each compared to system cut unless noted

- `-f2` on TSV (challenge step 1).
- `-f1 -d,` on CSV (challenge step 2).
- `-f1,2` on TSV and `-f"1 2" -d,` on CSV (step 3).
- Ranges: `2-3`, `3-`, `-2`, mixed `1,3-4`.
- Out-of-order `3,1` and duplicate `2,2` (line order,
  duplicates collapsed).
- Out-of-range field `5` (empty line for delimited lines,
  whole line for no-delimiter lines).
- No-delimiter line under `-d,` (whole line out).
- Empty fields: `a,,c` with `-f1,3 -d,` gives `a,c`.
- Stdin: no file argument, and explicit `-` argument.
- Multi-file: two files concatenated in order.
- No trailing newline on the last input line: output
  still ends with `\n` (GNU behaviour, checked).
- Errors (must exit non-zero, message on stderr):
  missing `-f`, field `0`, decreasing range `2-1`,
  multi-character delimiter, missing file. The missing-
  file case must still process a later good file and
  exit 1.

## What is NOT tested

- The challenge's Dropbox sample files: not stable
  fixtures here. The fixtures above reproduce their
  shapes (TSV with the same field pattern, CSV with
  quoted titles).
- The step 5 pipeline count (155 unique artists):
  it depends on the full challenge CSV, not on `cut`
  itself. Piping `ccut` into `uniq | wc -l` is covered
  in the README example only.
- `-b` / `-c` modes, `--complement`, `-s`,
  `--output-delimiter`: out of scope, see SPEC.md.

# uniq — Design

Assumptions stated before coding (ponytail: think
before coding, minimum code, nothing speculative).

## Approach

- Python 3 standard library only, single file
  `uniq.py`, no dependencies.
- Work in **bytes** throughout (`sys.stdin.buffer`,
  files opened `'rb'`, `'wb'`), not text: uniq is a
  byte filter, and text decoding would fail or mangle
  non-UTF-8 input that system uniq handles fine.
- Stream, don't slurp: keep only the current run
  (its line bytes and its count) in memory, so
  arbitrarily large inputs cost O(1) memory. One
  pass: read a line, if it equals the current run's
  line bump the count, else flush the previous run
  and start a new one; flush the last run at EOF.

## Comparison key

- Key = line with only the trailing `\n` removed
  (`line[:-1] if line.endswith(b"\n")`). `\r` is
  kept, per the GNU check in SPEC.md.
- The emitted bytes are the run's key plus `\n`:
  CRLF endings round-trip exactly (the key keeps
  `\r`), and a final unterminated line gains a
  newline, matching GNU (caught by the system
  comparison test during development).

## Run filtering

A run is emitted when it passes the filter:

- default: every run.
- `-d`: only runs with count > 1.
- `-u`: only runs with count == 1.
- `-d` + `-u`: no run passes (GNU behaviour).
- `-c`: prefix `f"{count:7d} "` to the emitted line.
  With `-c`, the count is printed even for `-u`
  runs (always 1 there) and for `-d` runs — that is
  exactly the page's step 6 combination.

## CLI parsing

- `argparse` with `-c/--count`, `-d/--repeated`,
  `-u/--unique` (store_true) and two optional
  positionals. Argparse already accepts combined
  short flags (`-cd`) and `--count`/`--repeated`/
  `--unique` long forms, so no hand-rolled parser.
- Input `-` or absent → stdin; otherwise open the
  file. Output argument → open for writing, else
  stdout. Input is opened before the output file is
  truncated, so `uniq missing.txt out.txt` does not
  clobber `out.txt` — and so a missing input file
  errors before any output file is touched.
- Errors: missing/unreadable input and extra operands
  are reported GNU-style with exit 1 (argparse's
  exit 2 is kept only for unknown options, where
  argparse itself reports). `main()` returns the exit
  code; `sys.exit(main())` is the only exit path,
  which keeps the module importable for tests.

## What is deliberately NOT built

- No case-insensitive, field-skip, char-skip, or
  width-limited comparison (`-i`, `-f`, `-s`, `-w`):
  the page never asks for them.
- No `--group` / `--all-repeated`: same reason.
- No locale-aware comparison: bytes only, matching
  the C-locale behaviour the tests compare against.

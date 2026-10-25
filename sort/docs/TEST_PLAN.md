# sort — Test plan

Run: `python3 -m unittest discover -s tests -v` from `sort/`.

Two kinds of tests:

1. Function tests: import `ssort`, call each algorithm
   on lists of byte lines, assert equality with
   Python's `sorted()`.
2. CLI tests: run `ssort.py` and system `sort` (with
   `LC_ALL=C` in the environment, so its order is the
   byte order this tool implements) on the same
   fixtures, assert byte-identical output. If system
   sort is absent, those tests are skipped.

## Fixtures

- Words fixture in the challenge's shape: mixed case
  (`A`, `ACTUAL`, `AGREE`, `AGREEMENT`, `AND`, `apple`,
  `banana`), duplicates, empty line, prefix pairs
  (`a`, `aa`, `ab`, `b`), digits (`10`, `2`).
- A shuffled list of 500 distinct words plus
  duplicates, generated in the test (deterministic
  seed), used for the algorithm tests.

## Cases

- Each algorithm (merge, quick, heap, radix) sorts:
  empty list, single line, already sorted, reverse
  sorted, all duplicates, prefix pairs, and the 500
  word shuffled fixture — all equal to `sorted()`.
- Default CLI output equals system sort (`LC_ALL=C`)
  on the words fixture, and equals `sorted()` on the
  shuffled fixture.
- `-u`: duplicates appear once, order otherwise
  unchanged; equals system `sort -u` (`LC_ALL=C`).
- `--algorithm` for each of the four, via CLI, on the
  words fixture: all four give the same output.
- `-R`: output is a permutation of the input (same
  multiset), and equal lines are adjacent (grouped).
  No assertion that two runs differ — that would be
  flaky on small inputs — but on the 500-word
  fixture the run is checked to be a permutation,
  not the input order.
- `-R -u`: output is the set of distinct input lines,
  each once, in some order (checked as a set).
- Input handling: file, stdin (no file), `-` file,
  multi-file concatenation, no trailing newline on
  the last line (output still ends with `\n`),
  empty file (no output).
- Errors: missing file exits 1, but a later good
  file is still sorted and output.

## What is NOT tested

- The challenge's Project Gutenberg text and
  `words.txt` pipeline: not stable fixtures here.
  The words fixture above reproduces its shape
  (mixed case, duplicates, the step-1 first five).
- Locale-aware ordering: out of scope, see SPEC.md.
- `-r`, `-n`, `-k`, `-t`, `-f`, `-o`, `-c`: out of
  scope, see SPEC.md.
- Performance: no benchmark is asserted. Radix is
  O(n * maxlen) and the others O(n log n) by
  construction; the 500-word fixture is a
  correctness check, not a benchmark.

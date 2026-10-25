# TEST_PLAN — diff

Suite: `tests/test_diff.py`, run with
`python3 -m unittest discover -s tests -v` from `diff/`.

## Step 1 — LCS of strings (all five page cases verbatim)

- Identical strings → whole string.
- Disjoint strings → `""`.
- `"AABCXY"` vs `"XYZ"` → `"XY"`.
- Empty vs empty → `""`.
- `"ABCD"` vs `"AC"` → `"AC"`.
- Extra: one side empty, single character match/mismatch,
  repeated characters (`"AAB"` vs `"ABA"` → length 2, and the
  result must be a subsequence of both), reversed strings
  (`"ABCDEF"` vs `"FEDCBA"` → length 1).

## Step 2 — LCS of lines

- Page two-line case → `["this is the lcs"]`.
- Page paragraph case → the two unchanged lines, in order.
- Empty vs non-empty, identical line lists, no common lines,
  duplicate lines (assert maximal length + subsequence property,
  not one arbitrary LCS).

## Step 3 — diff output

- Page paragraph case → exactly the page's four lines
  (`<` old, `>` new, `<` old, `>` new).
- Identical inputs → `[]`.
- Empty vs non-empty → all `>` lines; non-empty vs empty →
  all `<` lines.
- Pure insertion in the middle, pure deletion in the middle,
  single-line change (one `<`, one `>`).
- Blank lines are real lines: deleting a blank line emits `"< "`.
- LCS-anchor check: the diff must equal the `<`/`>` sequence
  obtained by walking both lists alongside their full LCS
  (property test over several fixtures, including duplicates).
  This guards the prefix/suffix trimming in `diff_lines`.
  Note: the page's bare `<`/`>` format has no position
  markers, so a pure insertion cannot be replayed from the
  diff text alone — no such replay test is claimed.

## Oracle checks (difflib, test-only)

- For unambiguous fixtures (no repeated lines), the `<`/`>`
  sequence derived from `difflib.SequenceMatcher.get_opcodes()`
  must equal `diff_lines` output exactly.
- For every fixture, `len(lcs_lines(a, b))` must equal the
  total matched size reported by `difflib` (both compute a
  maximal LCS length, even when they pick different LCSes).

## System-diff comparison

- For unambiguous fixtures, the set of changed line contents
  from this tool must match the set from system `diff`
  (normal format), ignoring GNU's hunk headers, `---` lines,
  and line numbers. Exact byte equality is NOT asserted:
  GNU groups changes into hunks and may pair changes
  differently; the page's format has no hunks.

## CLI (subprocess, temp files)

- Page paragraph files → exactly the page's four output lines,
  exit `0`.
- Identical files → no output, exit `0`.
- Wrong argument count (0, 1, 3 args) → usage on stderr,
  exit `2`.
- Missing file → error on stderr, exit `1`.
- Missing final newline in one file → no output (documented
  trailing-newline rule).
- CRLF vs LF version of the same content → no output.

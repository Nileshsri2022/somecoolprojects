# DESIGN — diff

Assumptions stated before coding (ponytail: think before coding).

## Algorithm choice: DP LCS, not Myers

The challenge's own steps build the tool out of LCS (Step 1: LCS
of strings, Step 2: LCS of lines, Step 3: differences from the
LCS), so the core is a longest-common-subsequence computation.
I implement the classic dynamic-programming LCS:

- `dp[i][j]` = length of the LCS of `a[:i]` and `b[:j]`,
  filled with `dp[i][j] = dp[i-1][j-1] + 1` on a match, else
  `max(dp[i-1][j], dp[i][j-1])`.
- Backtrack from the end to recover one LCS: on a match take the
  element; otherwise move in the direction of the larger `dp`
  value, preferring to drop an element of the first sequence on
  a tie (`dp[i-1][j] >= dp[i][j-1]` → drop from `a`). The
  tie-break is arbitrary but deterministic, so output is stable
  run to run.

Why not Myers O(ND), which the page mentions as git's default?
Myers is faster on near-identical large files, but it is a
different, substantially more intricate algorithm, and it does
not follow the page's Step 1 → 2 → 3 progression. DP is the
minimum code that fully satisfies the stated steps and is easy
to verify against the page's test cases. Its cost is O(N·M)
time and O(N·M) space on the sequences it is run on.

## Scale (Step 5): trim before the DP table

Before running DP, `diff_lines` strips the common prefix and the
common suffix (non-overlapping) of the two line lists and runs DP
only on the middle. For the common case — files that differ in a
small region — the table is tiny even for large files, and the
result is identical to running DP on the whole input (a common
prefix/suffix line is in every LCS). Fully different large files
still cost O(N·M); that is the documented limit of this design,
not something papered over. No other Step 5 optimisation is
attempted: no chunking, no hashing, no Myers fallback.

## From LCS to diff output

Walk the two lists alongside the LCS. Between consecutive LCS
elements, every skipped element of the first list is emitted as
`"< " + line` and every skipped element of the second list as
`"> " + line`. Skipped first-file lines come before skipped
second-file lines within each gap, which matches the page's
Step 3 example (`<` old line, then `>` new line, per changed
region). Unchanged lines are never emitted.

## Why difflib is not in the production code

Python's `difflib` exists in the standard library, but the point
of this challenge is the diff algorithm itself, so `diff.py`
implements LCS from scratch. `difflib` is used only in the test
suite as an oracle: for unambiguous fixtures, the `<`/`>`
sequence derived from `difflib.SequenceMatcher` opcodes must
match this tool's output, and the LCS length must equal
`difflib`'s match total. Where duplicate lines make several
maximal LCSes possible, tests assert properties (maximal length,
subsequence of both inputs, reconstruction) instead of exact
equality with any one oracle.

## Deliberate divergences from GNU diff

- **Output format**: only `< ` / `> ` changed lines, no `---`,
  no hunk headers (`1,2c1,2`), no line numbers, no context.
  That is the page's format, not GNU's.
- **Exit status**: `0` even when files differ; GNU exits `1`.
  The page never specifies an exit status, and `0`-on-difference
  keeps the tool composable in pipelines without `|| true`.
- **Trailing newline**: ignored (see SPEC.md). GNU diff reports
  `\ No newline at end of file`. The page says nothing about
  it, and line-content comparison is the simpler contract.
- **No options**: no `-u`, `-c`, `-r`, `--brief`, etc. The page
  specifies a two-argument tool; flags would be speculative.

## Structure (single file, stdlib only)

`diff.py` contains, in order: `lcs(a, b)` (generic over strings
and lists of strings), `diff_lines(old, new)` (returns the
formatted `<`/`>` list), `split_lines(text)` / `read_lines(path)`
(file → lines), and `main(argv)` (argument handling, I/O,
exit codes). No third-party dependencies.

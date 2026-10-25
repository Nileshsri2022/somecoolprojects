# SPEC — Build Your Own diff Tool (Coding Challenges #13)

Source: https://codingchallenges.fyi/challenges/challenge-diff/
(read 2026-10-25; the page's steps below are the spec, not GNU diff's manual.)

## What the tool does

Compare two files and print the list of changes necessary to convert
the first file into the second. No output is produced if the files
are identical.

## Challenge steps

- **Step 0** — Set up the environment and a unit-test harness.
  (The page's Dropbox test files were not used; fixtures are written
  locally in `tests/test_diff.py` instead, so the build is
  self-contained.)
- **Step 1** — Implement longest common subsequence (LCS) for a
  single string. Page test cases:
  - `"ABCDEF"` vs `"ABCDEF"` → `"ABCDEF"`
  - `"ABC"` vs `"XYZ"` → `""`
  - `"AABCXY"` vs `"XYZ"` → `"XY"`
  - `""` vs `""` → `""`
  - `"ABCD"` vs `"AC"` → `"AC"`
- **Step 2** — Apply LCS to arrays of strings (lines). Page test
  cases: a two-line case whose LCS is `"this is the lcs"`, and the
  longer Coding Challenges paragraph case whose LCS is the two
  unchanged lines (the "I share a weekly coding challenge…" line and
  the "Each challenge will have you writing…" line).
- **Step 3** — Generate the differences between two arrays of
  strings as a third array of strings. For the paragraph case the
  page's output is (lines unwrapped):

  ```
  < Coding Challenges helps you become a better software engineer through that build real applications.
  > Helping you become a better software engineer through coding challenges that build real applications.
  < I’ve used or am using these coding challenges as exercises to learn a new programming language or technology.
  > These are challenges that I’ve used or am using as exercises to learn a new programming language or technology.
  ```

  Format: `< ` followed by a line present only in the first file,
  `> ` followed by a line present only in the second file, in file
  order. Unchanged (LCS) lines are not printed. There are no hunk
  headers, line numbers, `---` separators, or context lines — the
  page specifies none of those.
- **Step 4** — CLI: two command-line arguments, original file then
  new file. Read both files, run them through the Step 1–3
  functions, print the differences. Example from the page:

  ```
  % ccdiff origcc.txt newcc.txt
  < Coding Challenges helps you become a better software engineer through that build real applications.
  > Helping you become a better software engineer through coding challenges that build real applications.
  < I’ve used or am using these coding challenges as exercises to learn a new programming language or technology.
  > These are challenges that I’ve used or am using as exercises to learn a new programming language or technology.
  ```
- **Step 5 (optional)** — Scale. See DESIGN.md: common
  prefix/suffix trimming before the DP table is built.

## CLI contract (this implementation)

```
python3 diff.py ORIGINAL NEW
```

- Exactly two file arguments; anything else is a usage error.
- Input is read as UTF-8 text, split into lines on `\n`
  (one trailing `\r` per line is stripped, so CRLF files compare
  by content). A missing final newline is not a difference:
  `"a\n"` and `"a"` are the same one-line file.
- Output: one `< line` / `> line` per changed line, in order,
  printed to stdout. Identical files print nothing.
- Exit status: `0` whether the files are identical or different;
  `2` for wrong argument count; `1` for an unreadable/missing
  file (message on stderr). This deliberately differs from GNU
  diff, which exits `1` when files differ — see DESIGN.md.
- No flags, no stdin mode, no context/unified output. Those are
  outside the challenge page and are not implemented.

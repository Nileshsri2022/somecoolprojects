# SPEC — Build Your Own grep (Coding Challenges #9)

Source: https://codingchallenges.fyi/challenges/challenge-grep/
Difficulty taken: **Easy** — use the programming language's regular
expression library (Python `re`). The Hard path (own regex engine)
is out of scope; see DESIGN.md.

## What grep does

Search input lines for a pattern. A pattern matches a line if the
regular expression matches anywhere in the line, without its trailing
newline. An empty pattern matches every line. Each matching line is
written to standard output. Matching lines are printed in input order.

## Challenge steps (from the page)

- **Step 1 — empty expression:** `grep "" test.txt` writes every line
  of the file (verifiable with `diff`).
- **Step 2 — simple pattern + exit code:** `grep J rockbands.txt`
  prints `Judas Priest`, `Bon Jovi`, `Junkyard`. Exit code 0 when a
  match is found, non-zero when none is found.
- **Step 3 — recurse:** `-r` walks a directory tree. `grep -r Nirvana *`
  prefixes every match with its file path, e.g.
  `test-subdir/BFS1985.txt:Since Bruce Springsteen, Madonna, way
  before Nirvana`.
- **Step 4 — invert:** `-v` prints lines that do NOT match, so
  `grep -r Nirvana * | grep -v Madonna` leaves only
  `rockbands.txt:Nirvana`.
- **Step 5 — `\d` and `\w`:** `\d` is a digit, `\w` is a word
  character. `grep "\d" test-subdir/BFS1985.txt` prints the digit
  lines; `grep "\w" symbols.txt` prints `pound` and `dollar`.
- **Step 6 — anchors:** `^` matches the start of a line, `$` the end.
  `grep ^A rockbands.txt` prints `AC/DC`, `Aerosmith`, `Accept`,
  `April Wine`, `Autograph`; `grep na$ rockbands.txt` prints `Nirvana`.
- **Final step — case-insensitive:** `-i` ignores case. The page's
  counts (`grep A rockbands.txt | wc -l` = 8, `grep -i A` = 58)
  depend on the page's own `rockbands.txt` (Dropbox download); our
  fixture is smaller, so our counts differ — the behaviour (case
  folding widens the match set) is what the tests check, against
  system grep on the same fixture.

## Command line

```
grep.py [-riv] [--] PATTERN [FILE ...]
```

- Options may be bundled: `-ri` means `-r -i`. `--` ends option
  parsing, so a pattern starting with `-` can be given after it.
- No FILE operands: read standard input — except with `-r`, where
  GNU recurses the working directory instead (paths printed without
  a leading `./`).
- `-` as a FILE operand: read standard input at that position.
- Multiple FILE operands, or any recursed directory: prefix each
  match with `path:` (standard input shows as `(standard input):`).
  A missing file still counts as an operand for this rule. A single
  FILE operand, even with `-r`, gets no prefix.
- A directory operand without `-r`: error to stderr, exit code 2.
  With `-r`, directories are walked recursively.
- Unknown option, missing pattern, or an invalid regular expression:
  usage/error to stderr, exit code 2.

## Exit codes

- `0` — at least one line matched.
- `1` — no line matched.
- `2` — an error occurred (missing/unreadable file, directory without
  `-r`, invalid pattern, bad usage). If any error occurred, the exit
  code is 2 even if some lines matched, matching GNU grep.

## Output details

- A matched final line that lacks a trailing newline is printed with
  a newline appended, matching GNU grep.
- Matching is byte-based: input is read as bytes and the pattern is
  compiled as a bytes regular expression, so `\d` is `[0-9]` and `\w`
  is `[A-Za-z0-9_]`, the same as GNU grep in the C locale. Non-UTF-8
  input is passed through unchanged.

## Deliberate divergences from GNU grep

- No `-e`, `-f`, `-c`, `-n`, `-l`, `-x`, `-E`/`-F`, `--color`, or context
  flags: the challenge page asks only for `-r`, `-v`, `-i`.
- No "Binary file ... matches" message: binary input is searched and
  matching lines are printed raw (as with GNU `grep -a`).
- Recursive traversal visits directory entries in sorted name order,
  for deterministic output; GNU grep uses readdir order.
- Regex flavour is Python `re` (ERE-like) rather than GNU BRE: for
  the patterns on the challenge page the two agree. Tests compare
  against system `grep -E` for this reason.

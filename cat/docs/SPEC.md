# cat — Specification

Challenge: Build Your Own cat Tool, Coding Challenges #15.
Source page: https://codingchallenges.fyi/challenges/challenge-cat/
(the page loaded successfully; no corrected slug was needed).

The page quotes the cat man page:

> The cat utility reads files sequentially, writing them to the
> standard output. The file operands are processed in command-line
> order. If file is a single dash ('-') or absent, cat reads from
> the standard input.

## Steps from the page

- Step 0: set up, and grab test data (quotes from dummyjson).
  Test data here is local fixtures instead (see TEST_PLAN.md);
  the behaviour under test is identical.
- Step 1: open the file given on the command line and write its
  contents to standard output.
  Example: `cccat test.txt` prints the file.
- Step 2: read from standard input.
  Example: `head -n1 test.txt | cccat -` prints the first line.
- Step 3: concatenate files.
  Example: `cccat test.txt test2.txt` prints both, in order.
- Step 4: number the lines as they are printed.
  Example: `head -n3 test.txt | cccat -n` prints numbered lines.
- Step 5: number lines both including and excluding blank lines.
  Examples: `sed G test.txt | cccat -n` numbers every line
  (blanks included); `sed G test.txt | cccat -b` numbers only
  non-blank lines. The page concludes: "If you've got this
  far, congratulations you've built your own version of `cat`."

## Required behaviour

- Operands are processed in command-line order.
- No operands, or an operand `-`, means standard input.
  `-` may appear anywhere in the operand list, including more
  than once (a later `-` reads whatever stdin still has left,
  normally nothing).
- Multiple files are concatenated with no separator added.
- `-n`: number every output line.
- `-b`: number only non-blank output lines; blank lines are
  printed unchanged and unnumbered.
- Line numbering continues across concatenated files and across
  stdin segments — it is one counter for the whole run, not one
  per file.
- A file that cannot be opened is reported on stderr, the
  remaining operands are still processed, and the exit status
  is 1. If every operand succeeds, the exit status is 0.
- Unknown options are an error on stderr with exit status 1.

## Out of scope (not on the page — not built)

No other GNU cat options (`-E`, `-T`, `-s`, `-v`, `-A`, and
friends). The page asks only for `-n` and `-b`; this is not a
full GNU cat clone.

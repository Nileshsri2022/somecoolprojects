# ccwc — Specification (docs first)

Source: Coding Challenges, "Build Your Own wc Tool"
(https://codingchallenges.fyi/challenges/challenge-wc/)
Target in this repo: `somecoolprojects/ccwc/`
Original tool reverse-engineered by behaviour only: GNU `wc`.
No original source code was copied. Behaviour below is what was observed
from running `wc` and from the challenge steps.

## Goal

Build `ccwc`, a clone of Unix `wc`: word, line, character, and byte count.
One tool, one job, text in from a file or from stdin, counts out.

## Commands

```
ccwc [-c] [-l] [-w] [-m] [file]
cat file | ccwc [-c] [-l] [-w] [-m]
```

- No file argument: read stdin.
- No option argument: same as `-c -l -w`, in that order.
  (Challenge order for the default case is lines, words, bytes in the
  printed output — see Output below. The flag order on the command line
  does not change the output order.)
- Options, in challenge order:
  - Step 1, `-c`: number of bytes in the file.
  - Step 2, `-l`: number of lines.
  - Step 3, `-w`: number of words.
  - Step 4, `-m`: number of characters.
  - Step 5, default: `-c`, `-l`, `-w` together.
  - Final step: stdin when no filename is given.

## Challenge expected outputs (challenge test file)

These are the challenge's own numbers for its `test.txt`, not numbers
from this repo's sample files:

```
ccwc -c test.txt   ->   342190 test.txt
ccwc -l test.txt   ->     7145 test.txt
ccwc -w test.txt   ->    58164 test.txt
ccwc -m test.txt   ->   339292 test.txt   (locale-dependent, see below)
ccwc test.txt      ->     7145   58164  342190 test.txt
cat test.txt | ccwc -l  ->  7145
```

## Counting rules (observed from GNU wc)

- Bytes (`-c`): total bytes read.
- Lines (`-l`): number of `\n` bytes. A final line with no trailing
  newline is NOT counted as a line. Verified: `hello world\nhello again`
  (no trailing newline) gives `-l = 1`, not 2.
- Words (`-w`): maximal runs of non-whitespace bytes. Whitespace is
  space, tab, newline, vertical tab, form feed, carriage return.
  Transition whitespace -> non-whitespace starts a new word.
- Characters (`-m`): number of Unicode code points in the input when
  decoded as UTF-8. See the locale note below.
- Empty input: all counts are 0.

## Locale note on -m (deliberate, documented divergence)

GNU `wc -m` follows the current locale. In a C locale it does not
decode multibyte characters, so `-m` equals `-c`. Verified in this
environment (GNU coreutils 9.4): a file with `café` + two CJK characters
+ newline is 13 bytes, and system `wc -m` also reported 13.

`ccwc -m` instead always counts UTF-8 code points (that same file: 8).
This matches the challenge's description of `-m` as "characters",
and it is the only intentional divergence from system `wc` in a C
locale. In a UTF-8 locale the two agree. Tests for `-m` therefore
compare against the expected code-point count, not against system
`wc -m` in a C locale. All other options are tested against system
`wc` directly.

## Output formatting (observed from GNU wc)

- One count, one file: `<count> <filename>` — no padding.
  Example: `24 /tmp/ccwc_sample.txt`
- Several counts, one file: each count is right-justified to the width
  of the total byte count for that run (sum over all files given),
  joined by a single space, then a space and the filename.
  Example (file is 24 bytes, counts 2, 4, 24): ` 2  4 24 /tmp/ccwc_sample.txt`
  Verified against GNU: two 5000-byte files print with width 5
  (total 10000 bytes), one 5000-byte file alone prints with width 4.
- Stdin, one count: just the count, no filename, no padding.
  Example: `7145`
- Stdin, several counts: GNU pads each count to width 7. `ccwc`
  reproduces that for stdin multi-count output.
- Several files: one line per file, then a `total` line with the summed
  counts, labelled `total`. Width is the largest count across all files
  and the total.
- Errors: unknown option or missing file goes to stderr, exit code
  non-zero. A missing file does not print a counts line for it.

## Out of scope (ponytail: smallest change that solves the challenge)

- No `--files0-from`, `--total`, long options, or locale switching.
- No reading of directories, no binary-specific handling beyond
  counting bytes as read.
- No multiple-file total for stdin (stdin is a single stream).

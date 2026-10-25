# uniq — Spec

Source: Coding Challenges #10, "Build Your Own uniq Tool"
(https://codingchallenges.fyi/challenges/challenge-uniq/),
read 2026-10-25. This spec follows that page's steps, not
memory of GNU uniq; where the page is silent, GNU uniq
(9.4, the system uniq used for comparison tests) is the
tie-breaker, and any deliberate difference is noted below.

## Behaviour

`uniq` reads lines, compares only *adjacent* lines, and
writes one copy of each run of identical adjacent lines.
Repeated lines that are not adjacent are NOT collapsed,
so input may need sorting first (the page's own note).

## Steps (from the page)

- Step 1 — default: read an input file, drop duplicate
  adjacent lines. Example input `line1, line2, line2,
  line3, line4` becomes `line1, line2, line3, line4`.
  (The page also cites `uniq countries.txt | wc -l` = 246
  on its downloadable test data; that file is not used
  here — see TEST_PLAN.md.)
- Step 2 — input `-` or absent means standard input;
  a second argument is an output file, otherwise output
  goes to standard output. E.g. `cat test.txt | uniq -`
  and `cat test.txt | uniq - out.txt`.
- Step 3 — `-c` / `--count`: prefix each output line
  with the size of its run.
- Step 4 — `-d` / `--repeated`: output only lines that
  occurred more than once in a run.
- Step 5 — `-u` / `--unique`: output only lines that
  occurred exactly once.
- Step 6 — option combinations, e.g. `uniq -c -d
  countries.txt` (counts of repeated lines only).

## Command line

```
uniq [-c|--count] [-d|--repeated] [-u|--unique] [input [output]]
```

- Options may be combined (`-c -d`, `-cd`); `-d` and
  `-u` together select nothing, matching GNU (a run is
  never both repeated and unique).
- No other options are implemented: this is the page's
  lite version, not a full GNU clone (no `-f`, `-s`,
  `-w`, `-i`, `--group`, `--all-repeated`, etc.).

## Output details (GNU tie-breakers)

- Comparison is byte-for-byte on the line content
  excluding the trailing `\n` only; a `\r` is part of
  the line, so `a\r\n` and `a\n` are different lines.
- The emitted line is the comparison key plus `\n`:
  a final input line without a trailing newline
  *gains* one on output (verified GNU behaviour —
  an earlier version preserved the missing newline
  and failed the system comparison), while a `\r\n`
  line keeps its `\r` because the key strips only
  the `\n`.
- `-c` format is GNU's, not the page's simplified
  example: the count is right-justified in a field of
  width 7, then a single space, then the line
  (`      2 line2`). The page shows `2 line2`
  unpadded; matching system uniq byte-for-byte was
  judged more useful than matching the illustration.
- Empty input produces no output. Empty lines are
  ordinary lines (a run of blank lines collapses to one).

## Errors (exit status 1, message on stderr)

- Input file does not exist / cannot be read:
  `uniq: <file>: No such file or directory`
  (program name in the message is `uniq`, GNU-style,
  even though the script file is `uniq.py`).
- More than two file arguments: `uniq: extra operand
  '<arg>'` plus a `Try 'uniq --help'...` hint.
- Output file cannot be opened: `uniq: <file>: ...`
  with the OS error text.
- Unknown option: usage message on stderr, exit 2
  (argparse default, same as most Unix tools).

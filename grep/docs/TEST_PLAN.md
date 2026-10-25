# TEST_PLAN — grep.py

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests are in `tests/test_grep.py` (unittest). Fixtures live in
`tests/fixtures/` and mirror the challenge page's examples:

- `rockbands.txt` — bands for Steps 2, 3, 4, 6 and the final step:
  `AC/DC`, `Aerosmith`, `Accept`, `April Wine`, `Autograph`,
  `Bon Jovi`, `Judas Priest`, `Junkyard`, `Nirvana`, plus a few
  filler lines with no `J`, no leading `A`, and no trailing `na`.
- `test-subdir/BFS1985.txt` — the page's Nirvana/Madonna lines and
  digit lines for Steps 3 and 5.
- `symbols.txt` — `#`, `$`, `%`, `&`, `pound`, `dollar` for Step 5.
- `test.txt` — small multi-line file for Step 1 and stdin tests.
- `no-newline.txt` — final line without a trailing newline.

## Cases

Page examples, exact expected output:

1. Empty pattern prints the whole file (Step 1).
2. `J` on `rockbands.txt` prints exactly `Judas Priest`, `Bon Jovi`,
   `Junkyard`, exit 0 (Step 2).
3. `-r Nirvana` over the fixtures dir prints the `rockbands.txt`
   line plus the four `BFS1985.txt` lines, each prefixed (Step 3).
4. Piping the Step 3 output through `-v Madonna` leaves only
   `rockbands.txt:Nirvana` (Step 4).
5. `\d` on `BFS1985.txt` prints exactly the page's digit lines;
   `\w` on `symbols.txt` prints exactly `pound`, `dollar` (Step 5).
6. `^A` prints the five A-bands; `na$` prints only `Nirvana`
   (Step 6).
7. `-i` widens the match set versus case-sensitive search on the
   same fixture (final step; counts differ from the page because
   the fixture is not the page's Dropbox file).

System-grep comparisons (reference: `grep -E`, since Python `re`
is ERE-like — see SPEC.md):

8. For a matrix of patterns/options (empty, literal, `\w`,
   anchors, `-i`, `-v`, `-r`, multi-file, stdin), stdout bytes and
   exit code equal system `grep -E` on the same fixtures. `\d` is
   deliberately NOT in the matrix: GNU `grep -E` treats `\d` as
   literal `d` (verified), while the page defines it as a digit —
   `\d` is covered by the exact page-example test instead.
   Recursive comparisons sort output lines first, because GNU
   traversal order is readdir order while ours is sorted (SPEC.md).
9. Final line without trailing newline: our output equals system
   grep's (newline appended).
10. Multi-file and stdin (`-`) prefixing matches system grep,
    including `(standard input):`.

Error cases (exit code compared with system grep; stderr text is
ours, so only non-emptiness is asserted):

11. Missing file → exit 2, no stdout.
12. Directory operand without `-r` → exit 2.
13. Invalid regex (`[`) → exit 2.
14. No pattern at all → exit 2.
15. Unknown option (`-x`) → exit 2.
16. No match → exit 1, empty stdout.
17. Pattern after `--` (e.g. `-- -v`) works; `-v` without `--` is
    parsed as the invert flag, not the pattern.

Also: bundled flags (`-ri`) behave like the separate flags.

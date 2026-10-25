# head — Specification

Source: Coding Challenges, "Build Your Own head",
https://codingchallenges.fyi/challenges/challenge-head/
(slug `challenge-head`; first-guess slug, no 404 correction needed).
Steps implemented, in the page's order:

- Step 0: test input is the Project Gutenberg text
  (`https://www.gutenberg.org/cache/epub/132/pg132.txt`,
  saved as `test.txt` in the page's wording). Tests here use
  small local fixtures instead, plus byte-for-byte comparison
  against system `head`, which covers the same behaviour.
- Step 1: no options, one file (or no file) prints the first
  10 lines. With no file operand, input is standard input and
  output stops after line 10.
- Step 2: `-n N` prints the first N lines (`-n1` and `-n 1`
  both accepted, as on the page). Fewer lines than N in the
  input prints all of them; the program terminates normally.
- Step 3: `-c N` prints the first N bytes (`-c 31`, `-c 30`
  as on the page). Reaching end of input first prints what
  there is.
- Step 4: multiple files each get a header
  `==> NAME <==` before their output, with a blank line
  between one file's output and the next file's header, and
  up to N lines (or N bytes) per file.

Behaviour taken from system (GNU coreutils 9.4) `head`,
verified by experiment and matched by the test suite, where
the page is silent:

- `-` as an operand means standard input; in a header it is
  shown as `standard input`. With no operands at all, input
  is standard input with no header.
- Headers appear when there is more than one operand, or
  with `-v`/`--verbose`; `-q`/`--quiet` suppresses them.
- `--lines=N`, `--bytes=N`, and the obsolete `-N` form
  (e.g. `head -2 file`) are accepted. The last of `-n`/`-c`
  on the command line wins. Short options take no `=`
  (`-n=4` is an invalid number, as with system head).
- Negative counts print all but the last N lines/bytes
  (`-n -2`, `-c -3`); `-n -0` / `-c -0` print everything.
- Errors go to stderr, processing continues with the next
  file, exit status is 1 if any file failed, else 0:
  `head: cannot open 'NAME' for reading: No such file or directory`
  for a missing file, `head: error reading 'NAME': Is a directory`
  for a directory. A failed file prints no header and no
  blank-line separator; a file whose header was already
  printed before a read error still counts as output for
  the separator before the next file.
- Invalid counts and unknown options are errors on stderr
  with exit status 1, e.g.
  `head: invalid number of lines: 'x'`.

Page display caveat (not a code divergence): the page's
Step 3 shows `-c 31` output as `The Project Gutenberg
eBook`, but the first 31 bytes of that Gutenberg line are
`The Project Gutenberg eBook of ` (trailing space after
`of`); the implementation and system head agree on the
31 bytes, and the test asserts exactly that.

Deliberate divergences from system `head` (see DESIGN.md):

- No byte-count suffix multipliers (`-c 1K`, `-c 1KB`, …):
  only plain integers are accepted; a suffixed value is an
  "invalid number" error.
- No `-z`/`--zero-terminated` (NUL line delimiter) option.
- No `--help`/`--version` beyond a short usage message on
  `--help`; `--version` is treated as an unknown option.
  (Usage text itself is our own, not GNU's.)
- Error-message prefix is `head:` (the program is invoked
  as `head.py`, so this matches the tool name, unlike the
  repo's `ccat:`-style prefixes for other tools).

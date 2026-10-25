# cat — Test Plan

Tests live in `tests/test_cat.py` (unittest, stdlib only)
and are run from the `cat/` directory with:

```sh
python3 -m unittest discover -s tests -v
```

Every test runs `cat.py` as a subprocess (and, where the
behaviour is meant to match, system `cat` on the same
fixtures) and compares bytes, exit status, and — for error
cases — stderr text.

## Fixtures (created in a temporary directory per test)

- `one.txt`: three short text lines, trailing newline.
- `two.txt`: two short text lines, trailing newline.
- `blank.txt`: text lines with blank lines between them
  (`a\n\nb\n\n\nc\n`), including a whitespace-only line
  (` \n`) in the `-b` fixture to pin down "blank".
- `nonewline.txt`: text with no trailing newline.
- `empty.txt`: zero bytes.
- `binary.bin`: all 256 byte values plus NULs and invalid
  UTF-8 sequences.
- A subdirectory, for the "is a directory" error case.

## Cases

1. Step 1 — single file: stdout byte-identical to system
   `cat` on `one.txt`, exit 0.
2. Step 2 — stdin: no operands with piped stdin, and
   operand `-` with piped stdin, both byte-identical to
   system `cat` (same stdin).
3. Step 3 — concatenation: two and three files, in order,
   byte-identical to system `cat`; also file, `-`, file
   with stdin in the middle.
4. Step 4 — `-n`: numbered output byte-identical to
   system `cat -n` on text with blanks, on a file with no
   trailing newline, and on stdin.
5. Step 5 — `-b`: numbered-non-blank output byte-identical
   to system `cat -b`, including the whitespace-only line
   (numbered, not blank) and blank lines printed bare.
6. `-b` overrides `-n`: `-n -b` and `-b -n` both match
   system `cat -b`.
7. Combined flags: `-nb` matches system `cat -b`.
8. Numbering continues across files: `-n` over two files
   matches system `cat -n` (second file does not restart
   at 1).
9. Empty file and empty stdin: no output, exit 0.
10. Binary file: unnumbered and `-n` output byte-identical
    to system `cat` / `cat -n` on `binary.bin`.
11. Missing file: stderr names the file, exit 1, and a
    good file listed after it is still printed. (stderr
    is checked against our own `ccat:` format, not
    system cat's `cat:` prefix — see DESIGN.md point 9.)
12. Directory operand: stderr reports it, exit 1, other
    operands still printed.
13. Unknown option: stderr reports the option, exit 1,
    no stdout.
14. `--` ends option parsing: a file literally named
    `-n` in the fixture directory is printed, not treated
    as an option.
15. No trailing newline is preserved: output of
    `nonewline.txt` ends without `\n`, for unnumbered,
    `-n`, and `-b` modes.

## Oracle

System `cat` (GNU coreutils 9.4 on this machine) is the
oracle wherever behaviour is meant to match it. The only
deliberate non-match is the stderr program-name prefix
(`ccat:` vs `cat:`), covered by cases 11–13 checking our
own format instead of byte-comparing stderr.

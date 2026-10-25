# cat — Design

## Assumptions (stated before coding, per ponytail)

1. Language: Python 3, standard library only, single file
   `cat.py`, same as the previous projects in this repo.
2. Everything is bytes, never decoded text. Reason: cat
   concatenates files, it does not interpret them. Bytes
   keep binary files, invalid UTF-8, and files with no
   trailing newline byte-identical to system cat.
3. Unnumbered output streams in 8 KiB chunks. Reason: no
   need to hold a whole file in memory, and chunked copies
   are byte-identical to line-by-line copies for
   unnumbered output.
4. Numbered output reads line by line (a "line" is bytes up
   to and including the next `\n`, or up to end of input).
   Reason: the number has to be inserted before each line,
   so chunked copying cannot be used there.
5. Number format follows system (GNU) cat, not the page's
   simplified display: a right-aligned width-6 decimal
   number, a tab, then the line, i.e. `f"{n:6d}\t"`.
   Reason: the page's examples show `1  "Life ..."` with
   plain spaces and no padding, which is not what any real
   cat prints, and this repo's convention (ccwc, cut, sort)
   is byte-for-byte agreement with system cat. See the
   divergence note in the README.
6. A blank line for `-b` is a line that is exactly `b"\n"`.
   Verified against system cat: a line containing a single
   space is numbered by `cat -b`, so "blank" does not mean
   "whitespace-only".
7. `-b` overrides `-n` regardless of option order. Verified
   against system cat: both `cat -n -b` and `cat -b -n`
   number only non-blank lines.
8. A line with no trailing newline (the last line of a file
   or of stdin) is still numbered, and no newline is added
   after it. Verified against system cat.
9. Error messages use this program's own name, `ccat:`,
   following the repo convention (`ccut:`, `ssort:`), not
   system cat's `cat:` prefix. Format:
   `ccat: <path>: <strerror>`, e.g.
   `ccat: nope.txt: No such file or directory`.
   The exit status (1) and the continue-with-next-file
   behaviour match system cat; only the program-name
   prefix differs, so stderr is not byte-compared with
   system cat in tests.
10. Option parsing is hand-rolled, not argparse. Reason:
    the option set is tiny (`-n`, `-b`, combined forms like
    `-nb`, `--` to end options); argparse's error text and
    `--help` output would be extra surface for no benefit.
    Unknown options fail with
    `ccat: invalid option -- 'x'` and exit status 1, in
    the style of GNU cat's message.

## Structure

- `parse_args(argv)`: returns `(number_mode, operands)`.
  `number_mode` is `None`, `"n"`, or `"b"`. Options may
  appear before, between, or after operands (as with
  system cat). `--` ends option parsing; a later `-n`
  is then a filename. `-` on its own is always stdin,
  never an option.
- `copy_stream(in_stream, out_stream, number_mode, state)`:
  `state` is a one-element list holding the next line
  number, so the counter survives across files. Unnumbered:
  chunked copy. Numbered: per-line copy, prefixing
  `f"{n:6d}\t"` for numbered lines and incrementing only
  for lines that get a number.
- `main(argv)`: parses args, defaults to `["-"]` when no
  operands are given, opens each file in binary mode (or
  uses `sys.stdin.buffer` for `-`), reports open errors
  and continues, returns 1 if any operand failed else 0.

## Edge cases handled

- Empty file: produces no output, exit 0.
- Empty stdin: same.
- File with no trailing newline: last line copied (and
  numbered, if numbering) with no newline added.
- Binary input, invalid UTF-8, NUL bytes: copied verbatim
  (bytes throughout, no decoding).
- Missing file or directory in the middle of the list:
  error on stderr, other operands still printed, exit 1.
- Numbering across files: the second file's first line
  gets the next number after the first file's last line,
  not 1 again.

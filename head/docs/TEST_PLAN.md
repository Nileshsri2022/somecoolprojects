# head — Test plan

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests are in `tests/test_head.py` (unittest). Each case
runs `head.py` as a subprocess and, for normal cases,
system `head` on the same fixtures, and asserts stdout,
stderr and exit status match exactly (byte-for-byte).
Fixtures are created in a temporary directory per test;
nothing is read from the repo checkout.

Cases:

1. Step 1 — default: one file, 20 lines -> first 10;
   no operands with piped stdin -> first 10 lines.
2. Step 2 — `-n`: `-n1`, `-n 3`, `-n0`, `-n` larger than
   the file, file shorter than N, empty file, file with
   no trailing newline, attached and separate values,
   obsolete `-2` form, `--lines=3`.
3. Step 2/3 — negative counts: `-n -2`, `-c -3`,
   `-n -0` (all lines), negative count larger than input
   (empty output).
4. Step 3 — `-c`: `-c 31`, `-c 30`, `-c0`, `-c` larger
   than the file, binary bytes (all 256 byte values).
5. Step 4 — multi-file: two and three files, headers
   `==> name <==`, blank-line separators, per-file N,
   `-q` suppresses headers, `-v` forces a header for a
   single file, `-` operand shown as `standard input`,
   `-v` with stdin.
6. Last-wins: `-n1 -c2` behaves as `-c2` (and vice
   versa), matching system head.
7. Errors: missing file (message, exit 1, continues to
   the next file, no separator blank line for the failed
   file), directory (header printed, then read error,
   exit 1), invalid count (`-n x`, `-c 1K` suffix),
   unknown option (`--bogus`, `-z`), both `-n` and `-c`
   is NOT an error (last wins — case 6), missing value
   after `-n`/`-c`.
8. Page examples: a Gutenberg-style first line via
   `-n1`, and `-c 31` producing exactly
   `The Project Gutenberg eBook`.

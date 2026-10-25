# ccwc — Test plan

Run: `python3 -m unittest discover -s tests -v` from `ccwc/`.

Tests run `ccwc.py` as a subprocess, exactly as a user would,
and compare its stdout to one of two oracles:

1. System `wc` (GNU coreutils 9.4 in this environment) — for
   `-c`, `-l`, `-w`, default, stdin, and multi-file total.
   This is the reverse-engineering oracle: same input, same
   output, no shared code.
2. Hand-computed code-point counts — for `-m` only, because
   system `wc -m` in a C locale equals `-c` (see SPEC.md).

## Fixtures (created by the tests, in a temp dir)

- `sample.txt`: `hello world\nhello again\n`
  Expected: bytes 24, lines 2, words 4, chars 24.
- `no_nl.txt`: `hello world\nhello again` (no trailing newline)
  Expected: bytes 23, lines 1, words 4, chars 23.
- `empty.txt`: empty.
  Expected: all counts 0.
- `utf8.txt`: `café 中文\n` as UTF-8 bytes.
  Expected: bytes 13, lines 1, words 2, chars 8.

## Cases

- Each single option (`-c`, `-l`, `-w`, `-m`) on `sample.txt`.
- Default (no option) on `sample.txt` — must equal `-l -w -c`
  in that output order.
- No-trailing-newline: `-l` must be 1, not 2.
- Empty file: all options, and default, must be 0.
- UTF-8 file: `-c` 13, `-l` 1, `-m` 8.
- Stdin: `cat sample.txt | ccwc -l` must print `2` with no
  filename; stdin default must match system `wc` default
  (with the GNU width-7 stdin rule).
- Multiple files: two files plus a `total` line, counts summed.
- Errors: unknown option exits non-zero with usage on stderr;
  missing file exits non-zero with an error on stderr and no
  counts line for that file.

## What is NOT tested

- The challenge's own `test.txt` (342190 bytes etc.): its
  download link is a Dropbox link, not a stable fixture, and
  its numbers are already recorded in SPEC.md. The fixtures
  above cover every counting rule that file would exercise.
- Performance on gigabyte files: streaming is by construction
  (8 KiB chunks, constant state), not benchmarked here.

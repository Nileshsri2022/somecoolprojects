# head — Design

## Assumptions (stated before coding, ponytail rule)

- Python 3 standard library only, single file `head.py`.
- All I/O is in bytes (`sys.stdin.buffer` /
  `sys.stdout.buffer`, files opened `'rb'`). This makes
  output byte-identical for binary input, for a final line
  with no trailing newline, and for non-UTF-8 bytes — text
  decoding would corrupt or crash on those. A "line" is
  bytes up to and including the next `\n`; a trailing
  partial line still counts as one line.
- Streaming, not slurp-whole-file: line mode reads one
  line at a time; byte mode reads in 8 KiB chunks. The
  only buffering is the bounded hold-back needed for
  negative counts (last N lines in a deque, last N bytes
  in a small byte buffer).
- Argument parsing is hand-written, not `argparse`:
  GNU head accepts clustered short options, attached
  values (`-n1`), the obsolete `-N` form, and
  `--lines=N`/`--bytes=N`, and its error messages and
  exit behaviour differ from argparse's. A small manual
  parser matches the real tool with less code than
  bending argparse into shape.

## Pipeline

```
argv -> parse_args() -> (mode, count, verbose, quiet, operands)
  mode: 'lines' | 'bytes'; count: int (may be negative)
  operands: [] means "read stdin once"
for each operand (or stdin if none):
  show header? verbose or (len(operands) > 1 and not quiet)
    header name: operand, except '-' -> 'standard input'
    blank line before the header if any output already printed
  open file ('rb') or use stdin buffer
  lines:  not negative -> emit first `count` readline()s
          negative   -> deque(maxlen=count); emit a line
                        only when it is pushed out of the
                        deque; count 0 with the negative flag
                        (i.e. `-0`) emits everything
  bytes:  not negative -> emit first `count` bytes from chunks
          negative   -> hold back last `count` bytes in a
                        buffer; emit bytes that fall out of it
  The negative flag is carried separately from the integer
  because `int("-0") == 0` would otherwise conflate `-0`
  (all) with `0` (none).
  on open/read OSError -> stderr message, exit status 1,
    continue with the next operand
```

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes.
- The suite compares stdout, stderr and exit status
  byte-for-byte against system `head` for every normal
  case (defaults, `-n`, `-c`, negative counts, multi-file
  headers, `-q`/`-v`, stdin, `-` operand, empty file, file
  with no trailing newline, binary bytes), and checks the
  documented error messages for missing files, directories,
  invalid counts, and unknown options.
- The page's own examples reproduce: `-n1 test.txt`
  prints the Gutenberg first line, `-c 31` prints
  `The Project Gutenberg eBook` (31 bytes, no newline),
  multi-file output shows `==> … <==` headers.

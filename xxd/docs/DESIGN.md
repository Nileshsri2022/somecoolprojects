# xxd — Design

## Assumptions (stated before coding)

1. The page's examples are the contract. Where the page is silent
   (exact padding of short lines, error exit codes, reverse-mode
   tolerance), this implementation follows real `xxd` conventions
   as far as they can be stated without the binary present, and the
   choice is recorded here.
2. System `xxd` is NOT installed in this environment (`which xxd`
   finds nothing), so byte-for-byte comparison against system `xxd`
   was impossible. The page's own example lines are the oracle
   instead, and every divergence from the page is listed in the
   README under "Divergences".
3. Python 3 standard library only; one file, `xxd.py`; streaming
   (line-sized chunks), no whole-file reads except the stdin
   negative-seek case below.

## Layout of a dump line

```
00000000: 6669 6c65 312e 7478 7400 0000 0000 0000  file1.txt.......
^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^
offset    hex field                                ASCII field
```

- Offset: `f"{offset:08x}"` — minimum 8 digits, grows naturally.
- Hex field: bytes split into groups of `groupsize`; within a group
  bytes print in file order, or reversed in `-e` mode. Groups join
  with one space. A short final group prints only its bytes.
- Short lines (last line, or `-c`/`-l` cut): the hex field is padded
  with spaces to the width of a full line's hex field for the current
  `-c`/`-g`, so the ASCII column aligns within one invocation.
- Separator between hex field and ASCII is exactly two spaces,
  including on full lines. (See README: the page's Step 2 `-e`
  examples appear to show three spaces; that is recorded as a
  possible divergence, not silently "fixed" to match an unverified
  reading.)
- ASCII: `chr(b) if 0x20 <= b <= 0x7e else "."`.

Full-line hex width = `cols * 2 + (ceil(cols / groupsize) - 1)`.
If `groupsize > cols`, the whole line is a single group (the width
formula still holds: one group, no separators).

## Options and validation

- Default group size: 2 normally, 4 with `-e`; an explicit `-g`
  always wins.
- `-g` must be a power of two in 1..256. Rationale: real `xxd`
  groups are word-sized; 3, 5, 6, 0, negatives and non-numbers are
  rejected. (The page only says "handle invalid values for `-g`";
  this is the rule chosen.)
- `-c` must be in 1..256, `-l` must be >= 0. Both are plain ints;
  `-l` also accepts `0x` hex like `-s` for consistency.
- `-s` parsing: `int(value, 0)` semantics — decimal, or `0x`
  hex, with an optional leading `+`/`-`. Negative forward seek
  means "that many bytes before EOF": for a seekable file this is a
  real seek; for stdin the input is read fully, then the tail is
  dumped (streaming is impossible for a negative seek on a pipe,
  and this is the only whole-input read in the program).
- `+N` seek (relative to current position) is the same as `N` here
  because dumping always starts at position 0; it is accepted and
  treated as absolute.

## Forward dump algorithm

1. Open input (or stdin buffer). Seek to the start offset
   (clamped: past EOF yields no output).
2. Loop reading at most `cols` bytes, stopping after `length`
   bytes if `-l` was given. Format and write each line.

## Reverse algorithm

1. Read input as text (ASCII superset; decode errors are fatal —
   a hex dump is text).
2. Per line: strip a leading `^[0-9a-fA-F]+:` offset if present;
   split the rest on `\s{2,}` and keep the first segment; split
   that on whitespace into tokens; each token must be all hex
   digits with even length, else error.
3. If `-e`, reverse the bytes inside each group-sized chunk of
   that line's hex bytes (chunks do not cross line boundaries,
   matching how the forward dump groups within a line).
4. Apply `-l` limit and `-s` output positioning; write bytes.

## Structure (`xxd.py`)

- `parse_offset(value)` — shared `-s`/`-l` number parser.
- `format_line(offset, chunk, cols, groupsize, little_endian)` —
  pure function, unit-tested directly.
- `dump(in_stream, out_stream, opts)` / `revert(in_text, out_stream,
  opts)` — the two directions, unit-tested on in-memory streams.
- `main(argv)` — argument parsing (argparse), file handling,
  error reporting. Kept thin so tests can drive the library parts
  without subprocesses, plus a few subprocess tests for exit codes.

## Verifiable success criteria

- Every page example line in Steps 1–4 reproduces exactly (see
  tests, which encode the page's lines verbatim, modulo the `-e`
  spacing note).
- Dump → revert round-trips byte-for-byte for empty input, text,
  and all 256 byte values, in both normal and `-e` modes.
- Invalid `-g`/`-c`/missing-file cases exit non-zero with a
  stderr message.

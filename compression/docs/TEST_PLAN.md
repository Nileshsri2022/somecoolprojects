# compression — Test plan

Run: `python3 -m unittest discover -s tests -v` from `compression/`.

Tests do two things:

1. Function tests: import `huffman`, call `compress()` /
   `decompress()` on bytes in memory, assert roundtrip
   equality and code-table properties.
2. CLI subprocess tests: run `huffman.py compress` then
   `huffman.py decompress` on files, assert the final file
   is byte-identical to the original, and assert corrupt
   inputs exit non-zero.

## Cases

- Empty input: compresses to just the 8-byte header
  (`CHUF` + distinct 0), decompresses to empty.
- Single byte: `b"a"` roundtrips.
- Single symbol repeated: `b"aaaaaaa"` roundtrips (the
  special single-symbol code path).
- Challenge example: `b"aaabbc"` — code table must be
  prefix-free, `a` must have the shortest code, roundtrip
  must be exact. (Compressed size is NOT asserted smaller
  here: the 8-byte header + symbol entries dwarf 6 bytes
  of input, by design.)
- All byte values: `bytes(range(256))` roundtrips, and a
  file with all 256 values twice roundtrips.
- Repetitive text: a paragraph repeated many times.
  Roundtrip exact, and compressed size must be smaller
  than the original (the challenge's step 7 check).
- Larger repetitive text: ~100 KiB of repeated words.
  Roundtrip exact, compressed smaller, and the ratio is
  reported in the test output for inspection (not asserted
  to a specific number, since it depends on the text).
- Frequency table: for a known input, `frequencies()`
  returns the exact counts (challenge step 1 check, e.g.
  `b"aaabbc"` gives a=3, b=2, c=1).
- Corrupt inputs (CLI, must exit non-zero, no output file
  written as valid):
  - bad magic (`XXXX` instead of `CHUF`),
  - truncated header (magic + distinct count only),
  - truncated bitstream (header valid, bitstream cut short),
  - missing input file,
  - unknown subcommand / wrong argument count.

## What is NOT tested

- The challenge's Les Misérables Dropbox file: it is not a
  stable, fetchable fixture from this environment. The
  repetitive-text cases above exercise the same properties
  (unequal frequencies, large text, size reduction).
- Interoperability with other Huffman tools: the format is
  this tool's own (see SPEC.md), so no other tool is
  expected to read it.
- Performance: Huffman over bytes in Python is O(n) with
  a small constant, but no benchmark is asserted.

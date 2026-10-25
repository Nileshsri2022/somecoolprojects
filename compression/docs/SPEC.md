# compression — Specification (docs first)

Source: Coding Challenges, "Build Your Own Compression Tool"
(https://codingchallenges.fyi/challenges/challenge-huffman/)
Target in this repo: `somecoolprojects/compression/`
Original algorithm reverse-engineered by behaviour only: David
Huffman's optimal prefix-code algorithm (early 1950s), as
described in the challenge. No original compressor source was copied.

## Goal

Build a command-line Huffman encoder/decoder that compresses a
file losslessly, then decompresses it to a byte-identical copy.

The challenge's steps, in order:

1. Read text, determine the frequency of each character.
2. Build the binary tree from the frequencies.
3. Generate the prefix-code table from the tree.
4. Write a header to the output file, with enough information
   to decode it (tree, or frequency table, plus a way to know
   where the header ends and compressed data starts).
5. Encode the text with the code table, pack bits into bytes,
   append after the header.
6. Read the header back and rebuild the prefix table.
7. Read the remainder, decode with the prefix table, write the
   decoded text out. Compress, check the output is smaller,
   decompress, check the copy is identical.

The challenge's example: `aaabbc` is 6 bytes normally. With
`a: 1, b: 01, c: 10` (most frequent = shortest code) it becomes
9 bits. Codes must be prefix-free: no code is a prefix of another.

## Commands

```
python3 huffman.py compress <input> <output>
python3 huffman.py decompress <input> <output>
```

- `compress` reads any file (bytes, not just text), writes the
  format below.
- `decompress` reads that format, writes the original bytes.
- Errors (missing file, bad magic, truncated header or bitstream)
  go to stderr, exit code non-zero. Usage errors exit 2.

## File format (this tool's own format, documented here)

This is not a standard format like gzip or ZIP. It is the
simplest format that satisfies step 4: the header carries the
frequency table, from which the decoder rebuilds the exact
same tree (deterministic tie-breaking, see DESIGN.md).

```
offset  size  field
0       4     magic: ASCII "CHUF"
4       4     distinct symbol count, unsigned big-endian (0-256)
8       5*n   per symbol, in ascending byte order:
                1 byte  symbol (0-255)
                4 bytes frequency, unsigned big-endian
8+5*n   ...   bitstream: Huffman codes packed MSB-first,
                padded with 0 bits to a byte boundary at the end
```

- Total original length is the sum of the frequencies, so the
  decoder knows exactly how many symbols to produce and can
  ignore the padding bits. No separate length field is needed.
- Empty input: distinct = 0, no symbol entries, no bitstream.
  Decompressing that yields an empty file.
- Single distinct symbol: its code is defined as `"0"` (see
  DESIGN.md for why a zero-length code cannot work).

Limits, documented: each frequency and the distinct count fit
in the fields above, so a single symbol may occur at most
2^32-1 times and the file may contain at most 256 distinct
bytes (true for bytes by definition). Files larger than that
per-symbol limit are out of scope.

## Validity rules enforced on decompress

- Magic must be exactly `CHUF`, otherwise: not a file this
  tool produced.
- Header must not be truncated: distinct count, then that
  many 5-byte symbol entries, must all be present.
- Distinct count must be 0-256, symbols must be distinct
  (a duplicate symbol in the header is corrupt).
- Bitstream must contain enough bits to decode the number of
  symbols implied by the frequencies. Running out of bits is
  corrupt input, not a silent short output.
- A file with extra trailing bytes after the needed bitstream
  is accepted only if those bytes are the padding to the last
  byte boundary; anything beyond that is ignored by design
  (the decoder stops after the known symbol count). This is
  documented, not checked as an error, because the padding
  rule makes trailing-byte detection ambiguous by construction.

## Out of scope (ponytail: smallest change that solves the challenge)

- No canonical Huffman codes, no DEFLATE / LZ77, no ZIP container.
  Those were a separate, earlier ZIP/DEFLATE project, not this
  challenge. This tool is Huffman only, over bytes.
- No streaming of multi-gigabyte files: input is read whole,
  frequencies counted, then encoded. `ccwc` streaming does not
  apply here because Huffman needs two passes (count, then encode).
- No compression ratio guarantee for tiny or random inputs:
  the header (5 bytes per distinct symbol + 8 bytes) can make
  a tiny compressed file larger than its input. The challenge's
  "output is smaller" check only makes sense on repetitive text,
  and that is what the tests check.

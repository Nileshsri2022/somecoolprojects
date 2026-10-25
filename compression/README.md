# compression — Build Your Own Compression Tool

Coding Challenges #3, worked one by one in
`somecoolprojects/`. Docs first, then code — see `docs/`.

Huffman coding only: frequency table, binary tree, prefix
codes, bit packing. Not DEFLATE, not ZIP.

## Usage

```sh
python3 huffman.py compress input.txt output.huff
python3 huffman.py decompress output.huff restored.txt
# restored.txt must be byte-identical to input.txt
```

Format: `CHUF` magic, distinct-symbol count, then per-symbol
(byte + frequency, ascending byte order), then the bitstream
packed MSB-first. See `docs/SPEC.md` for the full format.

Tiny or random inputs can compress larger than the original:
the header costs 8 + 5 bytes per distinct symbol. The size
win appears on repetitive text, as the challenge intends.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests check roundtrip equality, prefix-free codes, frequency
counts, size reduction on repetitive text, and corrupt-input
failures.

## Files

- `huffman.py` — frequencies, tree, codes, format, CLI.
- `docs/SPEC.md` — challenge spec and file format.
- `docs/DESIGN.md` — algorithm, assumptions, file layout.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_huffman.py` — the test suite.

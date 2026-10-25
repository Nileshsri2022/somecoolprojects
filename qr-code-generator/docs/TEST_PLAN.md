# TEST_PLAN — QR Code Generator

Run: `python3 -m unittest discover -s tests -v` from the
project directory. Stdlib `unittest` only.

## Test groups (in `tests/test_qr_code.py`)

1. **Mode detection** (challenge Step 1): numeric strings ->
   numeric; uppercase + symbols + space -> alphanumeric;
   lowercase / mixed / punctuation outside the set -> byte;
   empty string -> byte. Alphanumeric symbol set exactly as
   the page lists it.
2. **Bit encoding** (Step 2): the page's worked example —
   `HELLO CC WORLD` encodes to mode `0010`, count `000001110`,
   and the page's exact data bit string. Numeric grouping
   (3 digits -> 10 bits, remainder 1 -> 4 bits, 2 -> 7 bits)
   and alphanumeric pairing (2 chars -> 11 bits, odd tail ->
   6 bits) checked on small inputs.
3. **Padding** (Step 2.6): padded bit stream length equals the
   data-codeword capacity in bits; terminator and `EC/11`
   alternation checked on a short input.
4. **Reed-Solomon** (Step 3): every generated block's syndrome
   is zero (remainder of the full codeword polynomial divided
   by the generator polynomial); EC codeword counts match the
   DESIGN.md table for every version 1-10 x level.
5. **Structure** (Step 4): matrix size is `17 + 4*version`;
   finder patterns (7x7 + separators) exact at all three
   corners; timing patterns alternate on row/col 6; alignment
   pattern centres correct per version; dark module set at
   `(4*version + 9, 8)`; quiet-zone handling in renderers.
6. **Format/version info** (Step 6): format bits for EC L,
   mask 0 equal the published value `111011111000100`;
   format bits are identical in both copies in the matrix;
   version info for v7 equals published `000111110010010100`.
7. **Masking** (Step 5): all 8 masks produce distinct matrices
   for a non-trivial input; a forced mask is honoured; the
   auto-selected mask is the minimum-penalty one (recomputed
   independently in the test).
8. **Round-trip decode** (the strongest check): an independent
   decoder written in the test file (it reads format info,
   unmasks, walks the zigzag, de-interleaves, parses mode /
   count / payload) recovers the original text for numeric,
   alphanumeric, and byte inputs at several EC levels, and for
   a long input that forces version 10. No code is shared with
   the encoder's placement logic beyond the spec itself.
9. **Renderers**: ASCII output has the right number of rows
   and uses a quiet zone by default; SVG is well-formed XML
   with one black rect per dark module (plus background);
   PNG bytes start with the PNG signature, decode with stdlib
   `zlib`, and have the expected dimensions.
10. **CLI**: `qr_code.py "HELLO"` prints ASCII; `--svg` /
    `--png` write files; bad EC level / bad version / bad mask
    exit non-zero with a message on stderr; too-long input
    for v10 is rejected, not silently truncated.
11. **Cross-check against an independent library** (verification
    script, NOT part of the shipped test suite, since it needs
    a third-party package): `verify_against_qrcode.py` in
    `/tmp` compares our matrix byte-for-byte with the `qrcode`
    package for a grid of inputs, EC levels, versions, and
    masks. Run during development; results recorded in the
    final report. The shipped code never imports it.

## Success criteria

All shipped tests pass; cross-check matches on every compared
case; no test depends on network access or third-party packages.

# DESIGN — QR Code Generator

Ponytail rules applied: smallest change that fully solves the
task, no speculative features. One file, `qr_code.py`, stdlib only.

## Assumptions (stated before coding)

1. **Versions 1-10 only.** The page works version 4 in detail;
   generalising to 1-10 needs only the standard capacity/block/
   alignment tables (reproduced below), all cross-checked against
   the independent `qrcode` library during verification (see
   TEST_PLAN.md). Versions 11-40 add no new algorithm, only rows.
2. **Byte mode charset.** The page says ISO-8859-1. Implemented:
   encode as Latin-1 when every character is in range, else UTF-8.
   ASCII (the common case) is identical either way, and this keeps
   non-Latin text encodable instead of failing.
3. **Kanji out of scope.** Implementing Shift JIS double-byte
   encoding would need a codec table; byte mode covers the same
   text (less compactly). Documented, not silently wrong.
4. **Mask choice.** Default: evaluate all 8 masks with the
   standard penalty rules (N1=3, N2=3, N3=40, N4=10) and keep the
   lowest-penalty mask, ties -> lowest mask number. `--mask`
   forces one mask (useful for test-vector comparison).
5. **Interleaving with unequal blocks.** Where the data-codeword
   count is not divisible by the block count, the shorter blocks
   come first (group 1), then the longer blocks (group 2), each
   one codeword longer. This is the spec's group construction and
   matches the standard tables for versions 1-10.

## Pipeline

```
text -> detect_mode -> encode_bits (mode + count + payload)
     -> pad to data-codeword capacity (terminator, 0-pad, EC/11)
     -> split into blocks -> Reed-Solomon EC codewords per block
     -> interleave data, then EC codewords
     -> build matrix (function patterns, reserved areas)
     -> place data bits (zigzag, columns right-to-left, skip col 6)
     -> try 8 masks, keep lowest penalty
     -> write format info (BCH, XOR mask 0x5412) and, for v>=7,
        version info (BCH) -> QRCode
     -> render: ASCII / SVG / PNG (zlib, 8-bit greyscale)
```

## Key tables (versions 1-10)

Total codewords: v1 26, v2 44, v3 70, v4 100, v5 134, v6 172,
v7 196, v8 242, v9 292, v10 346.

EC codewords per block, by level (L/M/Q/H), and block counts:

| v | L ec/blk | M ec/blk | Q ec/blk | H ec/blk | blocks L/M/Q/H |
|---|----------|----------|----------|----------|----------------|
| 1 | 7  | 10 | 13 | 17 | 1/1/1/1 |
| 2 | 10 | 16 | 22 | 28 | 1/1/1/1 |
| 3 | 15 | 26 | 18 | 22 | 1/1/2/2 |
| 4 | 20 | 18 | 26 | 16 | 1/2/2/4 |
| 5 | 26 | 24 | 18 | 22 | 1/2/4/4 |
| 6 | 18 | 16 | 24 | 28 | 2/4/4/4 |
| 7 | 20 | 18 | 18 | 26 | 2/4/6/5 |
| 8 | 24 | 22 | 22 | 26 | 2/4/6/6 |
| 9 | 30 | 22 | 20 | 24 | 2/5/8/8 |
| 10| 18 | 26 | 24 | 28 | 4/5/8/8 |

Data codewords = total - blocks * ec-per-block (e.g. v4: 80/64/48/36,
matching the page). Character-count bits: v1-9 numeric 10 /
alphanumeric 9 / byte 8; v10 numeric 12 / alphanumeric 11 / byte 16.

Alignment-pattern centres: v1 none; v2 [6,18]; v3 [6,22];
v4 [6,26]; v5 [6,30]; v6 [6,34]; v7 [6,22,38]; v8 [6,24,42];
v9 [6,26,46]; v10 [6,28,50]. (Patterns overlapping a finder
pattern are skipped.)

## Reed-Solomon over GF(256)

Field with primitive polynomial `0x11D`, generator `0x02`;
exp/log tables built at import. Generator polynomial for `n`
EC codewords: product over i in 0..n-1 of (x - alpha^i).
EC codewords = remainder of message(x) * x^n divided by the
generator polynomial (polynomial long division in the field).
A valid block has all-zero syndromes — checked in tests.

## Format / version info

Format: 5 data bits (EC indicator L=01, M=00, Q=11, H=10, then
3 mask bits), 10 BCH bits from generator `0x537`, whole 15-bit
value XOR `0x5412`. Written twice: around the top-left finder
and split around the top-right / bottom-left finders.
Version (v>=7 only): 6 version bits + 12 BCH bits from generator
`0x1F25`, written in the 6x3 blocks by the finders.

## Divergences from the page (honest list)

- **Page's v4-Q block row is arithmetically inconsistent with
  its own capacity table.** The page lists Q as 2 blocks, 26 EC
  per block, and (in the block table) 29 data codewords per block,
  but 2*29 = 58 != 48, its own Q capacity. Implemented: 2 blocks
  x 24 data codewords (100 - 2*26 = 48). The standard tables
  agree with 24, and the `qrcode` cross-check confirms it.
- **Scope beyond the page's worked version 4:** versions 1-10
  auto-selected instead of version 4 only, and mask selection by
  full penalty evaluation (the page describes masking but does
  not fix a selection rule). Both are the spec's standard
  behaviour, not inventions.
- **Byte charset** (assumption 2) and **no Kanji** (assumption 3).
- The page's final "reproduce this QR code" image has no
  machine-readable payload published with it, so it cannot be
  used as a byte-exact test vector; instead, matrices are
  verified byte-for-byte against the independent `qrcode`
  library (verification only, never a runtime dependency).

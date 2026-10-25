# SPEC — QR Code Generator

Challenge page: https://codingchallenges.fyi/challenges/challenge-qr-generator
(slug `challenge-qr-generator` — the first guess `challenge-qr-code-generator`
404s; the correct slug was found via the site's "graphics" tag page).

## Challenge steps (as on the page)

- Step 0: set up; QR codes are defined in ISO/IEC 18004:2015.
- Step 1: analyse the input and pick the simplest encoding mode.
  Modes: numeric (digits 0-9), alphanumeric (digits, uppercase A-Z,
  `$ % * + - . / :` and space), byte (ISO-8859-1), Kanji (Shift JIS).
- Step 2: encode the data as bits.
  - 2.1 Error-correction levels L (7%), M (15%), Q (25%), H (30%).
  - 2.2 Smallest version. The page scopes the worked example to
    version 4 and gives its capacities (see below); versions are
    21x21 (v1) growing by 4 modules per version to 177x177 (v40).
  - 2.3 Mode indicators: numeric `0001`, alphanumeric `0010`,
    byte `0100`, Kanji `1000`.
  - 2.4 Character-count indicator bits, versions 1-9:
    numeric 10, alphanumeric 9, byte 8, Kanji 8.
  - 2.5 Encode the data in the selected mode. Worked example on the
    page: `HELLO CC WORLD` -> mode `0010`, count `000001110`, data
    `01100001011011110001101000101110001000101000110011101001000101001101110111110`.
  - 2.6 Pad: terminator `0000` (shortened if it would overflow),
    zero-pad to a byte boundary, then alternate pad bytes `0xEC, 0x11`.
    Version 4 data-codeword capacities: L 80, M 64, Q 48, H 36.
- Step 3: Reed-Solomon error correction over GF(256). Version 4
  block layout on the page: L 1 block / 20 EC / 80 data per block,
  M 2 / 18 / 32, Q 2 / 26 / (see divergence note in DESIGN.md),
  H 4 / 16 / 9. No group 2 for version 4.
- Step 4: build the matrix — finder patterns (top-left, top-right,
  bottom-left), separators, alignment pattern, timing patterns,
  dark module, reserved format/version areas, then data bits in
  the standard zigzag, skipping function areas.
- Step 5: choose a data mask (8 masks, section 7.8) to make the
  code as scannable as possible (penalty evaluation).
- Step 6: format and version information (sections 7.9, 7.10).
- Step 7: render with a quiet zone of 4 modules on all sides;
  1 = black, 0 = white. Final check on the page: reproduce its
  example QR code image.

## This implementation's scope

- Versions 1-10 (auto-selected smallest that fits; explicit
  `--version` also allowed). Versions 11-40 are out of scope:
  same algorithm, larger tables, no new concepts.
- Error-correction levels L, M, Q, H (default M).
- Modes numeric, alphanumeric, byte. Kanji is NOT implemented
  (no Shift JIS handling in scope; inputs needing it fall back
  to byte mode — see DESIGN.md).
- Outputs: ASCII art (default, stdout), SVG, and PNG
  (hand-written, stdlib `zlib` only — no Pillow, no `qrcode` lib).
- CLI: `python3 qr_code.py TEXT [--ec LEVEL] [--version N]
  [--mask N] [--svg FILE] [--png FILE] [--scale N] [--no-quiet-zone]`
- Library API: `generate(text, ec='M', version=None, mask=None)`
  returns a `QRCode` with `.matrix`, `.version`, `.ec_level`,
  `.mask`, `.mode`, `.size`, and `.to_ascii()`, `.to_svg()`,
  `.to_png_bytes(scale=...)`.
- Errors: empty input is allowed (encodes as byte mode, 0 chars);
  input too long for version 10 at the chosen EC level, an
  unknown EC level, or a version/mask out of range raise
  `ValueError` with a message on stderr and a non-zero exit code.

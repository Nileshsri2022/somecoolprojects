#!/usr/bin/env python3
"""QR Code generator, written from scratch (Python standard library only).

Implements ISO/IEC 18004 QR codes for versions 1-10, error-correction
levels L/M/Q/H, and numeric / alphanumeric / byte modes, following the
Coding Challenges page "Build Your Own QR Code Generator"
(https://codingchallenges.fyi/challenges/challenge-qr-generator).
See docs/SPEC.md, docs/DESIGN.md, docs/TEST_PLAN.md.

Outputs: ASCII art (default), SVG, and PNG (hand-written, zlib only).

Usage:
    python3 qr_code.py "HELLO WORLD"
    python3 qr_code.py "HELLO WORLD" --ec Q --svg out.svg --png out.png
"""

import argparse
import binascii
import struct
import sys
import zlib

# ---------------------------------------------------------------- GF(256)

# Field GF(2^8) with primitive polynomial 0x11D and generator element 0x02.
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gf_poly_mul(p, q):
    """Multiply two polynomials (coefficients highest-degree first)."""
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            out[i + j] ^= _gf_mul(a, b)
    return out


def _rs_generator_poly(n):
    """Generator polynomial for n error-correction codewords."""
    gen = [1]
    for i in range(n):
        gen = _gf_poly_mul(gen, [1, _EXP[i]])
    return gen


def reed_solomon_ec(data, n):
    """Return the n Reed-Solomon error-correction codewords for data."""
    gen = _rs_generator_poly(n)
    result = list(data) + [0] * n
    for i in range(len(data)):
        coef = result[i]
        if coef == 0:
            continue
        for j in range(len(gen)):
            result[i + j] ^= _gf_mul(gen[j], coef)
    return result[-n:]


def rs_syndromes(codewords, n):
    """Remainder of codewords(x) divided by the generator polynomial.

    All zeros iff the block is a valid Reed-Solomon codeword.
    """
    gen = _rs_generator_poly(n)
    result = list(codewords)
    for i in range(len(codewords) - n):
        coef = result[i]
        if coef == 0:
            continue
        for j in range(len(gen)):
            result[i + j] ^= _gf_mul(gen[j], coef)
    return result[-n:]


# ---------------------------------------------------------------- Tables

EC_LEVELS = "LMQH"
# EC indicator bits in format information (spec section 7.9).
_EC_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}

# Total codewords per version (index 0 unused).
_TOTAL_CODEWORDS = [0, 26, 44, 70, 100, 134, 172, 196, 242, 292, 346]
# EC codewords per block, by (version, level).
_EC_PER_BLOCK = {
    1: {"L": 7, "M": 10, "Q": 13, "H": 17},
    2: {"L": 10, "M": 16, "Q": 22, "H": 28},
    3: {"L": 15, "M": 26, "Q": 18, "H": 22},
    4: {"L": 20, "M": 18, "Q": 26, "H": 16},
    5: {"L": 26, "M": 24, "Q": 18, "H": 22},
    6: {"L": 18, "M": 16, "Q": 24, "H": 28},
    7: {"L": 20, "M": 18, "Q": 18, "H": 26},
    8: {"L": 24, "M": 22, "Q": 22, "H": 26},
    9: {"L": 30, "M": 22, "Q": 20, "H": 24},
    10: {"L": 18, "M": 26, "Q": 24, "H": 28},
}
# Number of error-correction blocks, by (version, level).
_NUM_BLOCKS = {
    1: {"L": 1, "M": 1, "Q": 1, "H": 1},
    2: {"L": 1, "M": 1, "Q": 1, "H": 1},
    3: {"L": 1, "M": 1, "Q": 2, "H": 2},
    4: {"L": 1, "M": 2, "Q": 2, "H": 4},
    5: {"L": 1, "M": 2, "Q": 4, "H": 4},
    6: {"L": 2, "M": 4, "Q": 4, "H": 4},
    7: {"L": 2, "M": 4, "Q": 6, "H": 5},
    8: {"L": 2, "M": 4, "Q": 6, "H": 6},
    9: {"L": 2, "M": 5, "Q": 8, "H": 8},
    10: {"L": 4, "M": 5, "Q": 8, "H": 8},
}
# Alignment-pattern centres (empty for version 1).
_ALIGNMENT = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46],
    10: [6, 28, 50],
}

MODE_NUMERIC = "numeric"
MODE_ALPHANUMERIC = "alphanumeric"
MODE_BYTE = "byte"
_MODE_INDICATOR = {MODE_NUMERIC: 0b0001, MODE_ALPHANUMERIC: 0b0010,
                   MODE_BYTE: 0b0100}
_ALPHANUMERIC_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


def data_codewords(version, ec_level):
    """Number of data codewords for a version / EC level."""
    return (_TOTAL_CODEWORDS[version]
            - _NUM_BLOCKS[version][ec_level] * _EC_PER_BLOCK[version][ec_level])


def _count_bits(mode, version):
    if version <= 9:
        return {MODE_NUMERIC: 10, MODE_ALPHANUMERIC: 9, MODE_BYTE: 8}[mode]
    return {MODE_NUMERIC: 12, MODE_ALPHANUMERIC: 11, MODE_BYTE: 16}[mode]


# ---------------------------------------------------------------- Encoding


def detect_mode(text):
    """Simplest mode that can encode text (challenge Step 1)."""
    if text == "":
        return MODE_BYTE
    if all("0" <= ch <= "9" for ch in text):
        return MODE_NUMERIC
    if all(ch in _ALPHANUMERIC_CHARS for ch in text):
        return MODE_ALPHANUMERIC
    return MODE_BYTE


def _text_bytes(text):
    """Byte-mode payload: Latin-1 when possible, else UTF-8 (see DESIGN)."""
    try:
        return text.encode("latin-1")
    except UnicodeEncodeError:
        return text.encode("utf-8")


def _bits_needed(mode, text, payload, version):
    n = 4 + _count_bits(mode, version)
    if mode == MODE_NUMERIC:
        n += (len(text) // 3) * 10
        rem = len(text) % 3
        n += {0: 0, 1: 4, 2: 7}[rem]
    elif mode == MODE_ALPHANUMERIC:
        n += (len(text) // 2) * 11
        if len(text) % 2:
            n += 6
    else:
        n += len(payload) * 8
    return n


def encode_data_bits(text, mode, version):
    """Mode indicator + character count + payload, as a list of 0/1."""
    bits = []

    def append(value, length):
        for i in range(length - 1, -1, -1):
            bits.append((value >> i) & 1)

    append(_MODE_INDICATOR[mode], 4)
    payload = _text_bytes(text) if mode == MODE_BYTE else None
    count = len(payload) if mode == MODE_BYTE else len(text)
    append(count, _count_bits(mode, version))
    if mode == MODE_NUMERIC:
        for i in range(0, len(text), 3):
            chunk = text[i:i + 3]
            append(int(chunk), {1: 4, 2: 7, 3: 10}[len(chunk)])
    elif mode == MODE_ALPHANUMERIC:
        for i in range(0, len(text) - 1, 2):
            v = (_ALPHANUMERIC_CHARS.index(text[i]) * 45
                 + _ALPHANUMERIC_CHARS.index(text[i + 1]))
            append(v, 11)
        if len(text) % 2:
            append(_ALPHANUMERIC_CHARS.index(text[-1]), 6)
    else:
        for byte in payload:
            append(byte, 8)
    return bits


def _bits_to_codewords(bits, capacity):
    """Pad a bit list to exactly capacity codewords (challenge 2.6)."""
    bits = list(bits)
    # Terminator, shortened if it would overflow.
    bits.extend([0] * min(4, capacity * 8 - len(bits)))
    # Zero-pad to a byte boundary.
    while len(bits) % 8:
        bits.append(0)
    # Alternate pad bytes 0xEC, 0x11.
    pad = 0xEC
    while len(bits) < capacity * 8:
        for i in range(7, -1, -1):
            bits.append((pad >> i) & 1)
        pad = 0x11 if pad == 0xEC else 0xEC
    out = []
    for i in range(0, len(bits), 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        out.append(byte)
    return out


def choose_version(mode, text, payload, ec_level):
    """Smallest version 1-10 whose data capacity fits the bit stream."""
    for version in range(1, 11):
        if (_bits_needed(mode, text, payload, version)
                <= data_codewords(version, ec_level) * 8):
            return version
    raise ValueError(
        "input too long for version 10 at error-correction level %s"
        % ec_level)


def _interleave(data_codewords_list, ec_blocks):
    """Interleave data codewords, then EC codewords, block by block."""
    out = []
    for i in range(max(len(b) for b in data_codewords_list)):
        for block in data_codewords_list:
            if i < len(block):
                out.append(block[i])
    for i in range(max(len(b) for b in ec_blocks)):
        for block in ec_blocks:
            if i < len(block):
                out.append(block[i])
    return out


def build_codewords(text, mode, version, ec_level):
    """Full (data + EC, interleaved) codeword sequence for the input."""
    payload = _text_bytes(text) if mode == MODE_BYTE else None
    bits = encode_data_bits(text, mode, version)
    data = _bits_to_codewords(bits, data_codewords(version, ec_level))
    n_blocks = _NUM_BLOCKS[version][ec_level]
    ec_len = _EC_PER_BLOCK[version][ec_level]
    # Shorter blocks first (group 1), then one-codeword-longer blocks.
    short_len = len(data) // n_blocks
    long_count = len(data) % n_blocks
    blocks, pos = [], 0
    for i in range(n_blocks):
        size = short_len + 1 if i >= n_blocks - long_count else short_len
        blocks.append(data[pos:pos + size])
        pos += size
    ec_blocks = [reed_solomon_ec(block, ec_len) for block in blocks]
    return _interleave(blocks, ec_blocks)


# ---------------------------------------------------------------- Format info


def _bch_remainder(value, generator, data_bits):
    """Remainder of (value << data_bits) divided by generator (binary)."""
    rem = value << data_bits
    gen_len = generator.bit_length()
    while rem.bit_length() >= gen_len:
        rem ^= generator << (rem.bit_length() - gen_len)
    return rem


def format_bits(ec_level, mask):
    """15-bit format value: 5 data bits + 10 BCH bits, XOR 0x5412."""
    data = (_EC_BITS[ec_level] << 3) | mask
    rem = _bch_remainder(data, 0x537, 10)
    return ((data << 10) | rem) ^ 0x5412


def version_bits(version):
    """18-bit version value: 6 version bits + 12 BCH bits."""
    return (version << 12) | _bch_remainder(version, 0x1F25, 12)


# ---------------------------------------------------------------- Matrix


def _mask_bit(mask, row, col):
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


class _Matrix:
    """Matrix plus a function-module map (True = function/reserved)."""

    def __init__(self, size):
        self.size = size
        self.modules = [[0] * size for _ in range(size)]
        self.function = [[False] * size for _ in range(size)]

    def set(self, row, col, value, is_function=True):
        if 0 <= row < self.size and 0 <= col < self.size:
            self.modules[row][col] = 1 if value else 0
            self.function[row][col] = is_function

    def _finder(self, top, left):
        for dy in range(-1, 8):
            for dx in range(-1, 8):
                r, c = top + dy, left + dx
                if not (0 <= r < self.size and 0 <= c < self.size):
                    continue
                if 0 <= dy <= 6 and 0 <= dx <= 6:
                    dark = (dx in (0, 6) or dy in (0, 6)
                            or (2 <= dx <= 4 and 2 <= dy <= 4))
                    self.set(r, c, dark)
                else:
                    self.set(r, c, 0)  # separator

    def _alignment(self, row, col):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                dark = (dx in (-2, 2) or dy in (-2, 2)
                        or (dx == 0 and dy == 0))
                self.set(row + dy, col + dx, dark)

    def build_function_patterns(self, version):
        size = self.size
        self._finder(0, 0)
        self._finder(0, size - 7)
        self._finder(size - 7, 0)
        # Timing patterns.
        for i in range(8, size - 8):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        # Alignment patterns (skip any overlapping a finder pattern).
        for row in _ALIGNMENT[version]:
            for col in _ALIGNMENT[version]:
                if ((row < 9 and col < 9) or (row < 9 and col > size - 10)
                        or (row > size - 10 and col < 9)):
                    continue
                self._alignment(row, col)
        # Reserve format-information areas.
        for i in range(9):
            if i != 6:
                self.set(8, i, 0)
                self.set(i, 8, 0)
        for i in range(7):
            self.set(size - 1 - i, 8, 0)
        for i in range(8):
            self.set(8, size - 1 - i, 0)
        # Reserve version-information areas (v >= 7).
        if version >= 7:
            for i in range(6):
                for j in range(3):
                    self.set(i, size - 11 + j, 0)
                    self.set(size - 11 + j, i, 0)
        # Dark module (set last: it sits just below the bottom-left
        # format area and must not be overwritten by the reservation).
        self.set(4 * version + 9, 8, 1)

    def place_data(self, codewords):
        bits = []
        for byte in codewords:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        idx = 0
        upward = True
        col = self.size - 1
        while col > 0:
            if col == 6:
                col -= 1
            for k in range(self.size):
                row = self.size - 1 - k if upward else k
                for c in (col, col - 1):
                    if not self.function[row][c]:
                        bit = bits[idx] if idx < len(bits) else 0
                        idx += 1
                        self.modules[row][c] = bit
            upward = not upward
            col -= 2

    def draw_format(self, ec_level, mask):
        fmt = format_bits(ec_level, mask)
        size = self.size
        # First copy (around the top-left finder), MSB first.
        copy1 = ([(8, i) for i in range(6)] + [(8, 7), (8, 8), (7, 8)]
                 + [(5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)])
        # Second copy (bottom-left vertical, then top-right horizontal).
        copy2 = ([(size - 1 - i, 8) for i in range(7)]
                 + [(8, size - 8 + i) for i in range(8)])
        for positions in (copy1, copy2):
            for i, (row, col) in enumerate(positions):
                # Bits are read MSB-first along each copy's positions.
                self.set(row, col, (fmt >> (14 - i)) & 1)

    def draw_version(self, version):
        if version < 7:
            return
        bits = version_bits(version)
        for i in range(18):
            bit = (bits >> i) & 1
            a = self.size - 11 + i % 3
            b = i // 3
            self.set(a, b, bit)
            self.set(b, a, bit)


# ---------------------------------------------------------------- Mask penalty


def _penalty(matrix):
    size = len(matrix)
    score = 0
    # Rule 1: runs of 5+ same-colour modules in rows and columns.
    for line in list(matrix) + [[matrix[r][c] for r in range(size)]
                                for c in range(size)]:
        run_val, run_len = None, 0
        for val in line:
            if val == run_val:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_val, run_len = val, 1
        if run_len >= 5:
            score += 3 + (run_len - 5)
    # Rule 2: 2x2 blocks of the same colour.
    for r in range(size - 1):
        for c in range(size - 1):
            v = matrix[r][c]
            if (matrix[r][c + 1] == v and matrix[r + 1][c] == v
                    and matrix[r + 1][c + 1] == v):
                score += 3
    # Rule 3: finder-like patterns 10111010000 / 00001011101.
    for line in list(matrix) + [[matrix[r][c] for r in range(size)]
                                for c in range(size)]:
        for i in range(len(line) - 10):
            window = line[i:i + 11]
            if window == [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0] or \
                    window == [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]:
                score += 40
    # Rule 4: deviation of the dark-module proportion from 50%.
    total = size * size
    dark = sum(sum(row) for row in matrix)
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    score += k * 10
    return score


def _apply_mask(base, mask):
    """base: _Matrix with data placed; returns masked module grid."""
    size = base.size
    out = [row[:] for row in base.modules]
    for r in range(size):
        for c in range(size):
            if not base.function[r][c] and _mask_bit(mask, r, c):
                out[r][c] ^= 1
    return out


# ---------------------------------------------------------------- Public API


class QRCode:
    """A generated QR code: module matrix plus its parameters."""

    def __init__(self, matrix, version, ec_level, mask, mode):
        self.matrix = matrix
        self.version = version
        self.ec_level = ec_level
        self.mask = mask
        self.mode = mode

    @property
    def size(self):
        return len(self.matrix)

    def to_ascii(self, quiet_zone=True):
        quiet = 4 if quiet_zone else 0
        blank = " " * ((self.size + 2 * quiet) * 2)
        lines = []
        for _ in range(quiet):
            lines.append(blank)
        for row in self.matrix:
            line = " " * (quiet * 2)
            line += "".join("██" if v else "  " for v in row)
            line += " " * (quiet * 2)
            lines.append(line)
        for _ in range(quiet):
            lines.append(blank)
        return "\n".join(lines) + "\n"

    def to_svg(self, scale=10, quiet_zone=True):
        quiet = 4 if quiet_zone else 0
        dim = (self.size + 2 * quiet) * scale
        parts = ['<svg xmlns="http://www.w3.org/2000/svg" '
                 'width="%d" height="%d" viewBox="0 0 %d %d">' % (dim, dim, dim, dim),
                 '<rect width="100%" height="100%" fill="white"/>']
        for r, row in enumerate(self.matrix):
            for c, val in enumerate(row):
                if val:
                    parts.append(
                        '<rect x="%d" y="%d" width="%d" height="%d" fill="black"/>'
                        % ((c + quiet) * scale, (r + quiet) * scale, scale, scale))
        parts.append("</svg>")
        return "\n".join(parts) + "\n"

    def to_png_bytes(self, scale=10, quiet_zone=True):
        quiet = 4 if quiet_zone else 0
        dim = (self.size + 2 * quiet) * scale
        raw = bytearray()
        for pr in range(dim):
            raw.append(0)  # filter: none
            mr = pr // scale - quiet
            for pc in range(dim):
                mc = pc // scale - quiet
                dark = (0 <= mr < self.size and 0 <= mc < self.size
                        and self.matrix[mr][mc])
                raw.append(0 if dark else 255)

        def chunk(kind, data):
            out = struct.pack(">I", len(data)) + kind + data
            return out + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", dim, dim, 8, 0, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw)))
        png += chunk(b"IEND", b"")
        return bytes(png)


def generate(text, ec="M", version=None, mask=None):
    """Generate a QR code for text. Raises ValueError on bad parameters."""
    if ec not in EC_LEVELS:
        raise ValueError("error-correction level must be one of L, M, Q, H")
    if version is not None and not 1 <= version <= 10:
        raise ValueError("version must be between 1 and 10")
    if mask is not None and not 0 <= mask <= 7:
        raise ValueError("mask must be between 0 and 7")
    mode = detect_mode(text)
    payload = _text_bytes(text) if mode == MODE_BYTE else None
    if version is None:
        version = choose_version(mode, text, payload, ec)
    elif _bits_needed(mode, text, payload, version) > \
            data_codewords(version, ec) * 8:
        raise ValueError("input does not fit version %d at level %s"
                         % (version, ec))
    codewords = build_codewords(text, mode, version, ec)

    base = _Matrix(17 + 4 * version)
    base.build_function_patterns(version)
    base.place_data(codewords)

    candidates = [mask] if mask is not None else range(8)
    best = None
    for candidate in candidates:
        masked = _apply_mask(base, candidate)
        score = _penalty(masked) if mask is None else 0
        if best is None or score < best[0]:
            best = (score, candidate, masked)
    _, chosen_mask, modules = best

    final = _Matrix(17 + 4 * version)
    final.build_function_patterns(version)  # function map + patterns
    final.modules = modules  # masked data modules
    final.draw_format(ec, chosen_mask)
    final.draw_version(version)
    return QRCode(final.modules, version, ec, chosen_mask, mode)


# ---------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a QR code (versions 1-10, stdlib only).")
    parser.add_argument("text", help="text to encode")
    parser.add_argument("--ec", default="M", choices=list(EC_LEVELS),
                        help="error-correction level (default M)")
    parser.add_argument("--version", type=int, default=None,
                        help="force a version 1-10 (default: smallest that fits)")
    parser.add_argument("--mask", type=int, default=None,
                        help="force a mask 0-7 (default: lowest penalty)")
    parser.add_argument("--svg", metavar="FILE", help="also write an SVG file")
    parser.add_argument("--png", metavar="FILE", help="also write a PNG file")
    parser.add_argument("--scale", type=int, default=10,
                        help="pixels per module for SVG/PNG (default 10)")
    parser.add_argument("--no-quiet-zone", action="store_true",
                        help="omit the 4-module quiet zone in all outputs")
    args = parser.parse_args(argv)
    try:
        qr = generate(args.text, ec=args.ec, version=args.version,
                      mask=args.mask)
    except ValueError as exc:
        print("qr_code: %s" % exc, file=sys.stderr)
        return 2
    quiet = not args.no_quiet_zone
    sys.stdout.write(qr.to_ascii(quiet_zone=quiet))
    if args.svg:
        with open(args.svg, "w", encoding="utf-8") as fh:
            fh.write(qr.to_svg(scale=args.scale, quiet_zone=quiet))
    if args.png:
        with open(args.png, "wb") as fh:
            fh.write(qr.to_png_bytes(scale=args.scale, quiet_zone=quiet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

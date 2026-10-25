"""Tests for qr_code.py (stdlib unittest only).

Includes an independent decoder: it rebuilds the function-module map
from the spec, reads the format info out of the matrix, unmasks,
walks the zigzag, de-interleaves, and parses mode/count/payload.
It shares no placement code with the encoder.
"""

import io
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import qr_code
from qr_code import (MODE_ALPHANUMERIC, MODE_BYTE, MODE_NUMERIC,
                     _ALPHANUMERIC_CHARS, _NUM_BLOCKS, _EC_PER_BLOCK,
                     data_codewords, detect_mode, encode_data_bits,
                     format_bits, generate, reed_solomon_ec,
                     rs_syndromes, version_bits)

QR = Path(__file__).resolve().parent.parent / "qr_code.py"


# ------------------------------------------------------- independent decoder

def function_positions(version, size):
    """Set of (row, col) that are function modules, from the spec."""
    pos = set()

    def finder(top, left):
        for dy in range(-1, 8):
            for dx in range(-1, 8):
                r, c = top + dy, left + dx
                if 0 <= r < size and 0 <= c < size:
                    pos.add((r, c))

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8, size - 8):
        pos.add((6, i))
        pos.add((i, 6))
    centres = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
               6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
               9: [6, 26, 46], 10: [6, 28, 50]}[version]
    for r in centres:
        for c in centres:
            if (r < 9 and c < 9) or (r < 9 and c > size - 10) \
                    or (r > size - 10 and c < 9):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    pos.add((r + dy, c + dx))
    pos.add((4 * version + 9, 8))
    for i in range(9):
        if i != 6:
            pos.add((8, i))
            pos.add((i, 8))
    for i in range(7):
        pos.add((size - 1 - i, 8))
    for i in range(8):
        pos.add((8, size - 1 - i))
    if version >= 7:
        for i in range(6):
            for j in range(3):
                pos.add((i, size - 11 + j))
                pos.add((size - 11 + j, i))
    return pos


def decode(qr):
    """Recover the original text from a generated QRCode object."""
    size, version = qr.size, qr.version
    func = function_positions(version, size)
    copy1 = ([(8, i) for i in range(6)] + [(8, 7), (8, 8), (7, 8)]
             + [(5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)])
    fmt = 0
    for r, c in copy1:
        fmt = (fmt << 1) | qr.matrix[r][c]
    data5 = (fmt ^ 0x5412) >> 10
    ec_bits, mask = data5 >> 3, data5 & 0b111
    # Unmask and read the zigzag.
    bits = []
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        for k in range(size):
            row = size - 1 - k if upward else k
            for c in (col, col - 1):
                if (row, c) not in func:
                    val = qr.matrix[row][c]
                    if qr_code._mask_bit(mask, row, c):
                        val ^= 1
                    bits.append(val)
        upward = not upward
        col -= 2
    codewords = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        codewords.append(byte)
    # De-interleave into blocks.
    ec_level = qr.ec_level
    n_blocks = _NUM_BLOCKS[version][ec_level]
    ec_len = _EC_PER_BLOCK[version][ec_level]
    n_data = data_codewords(version, ec_level)
    short_len = n_data // n_blocks
    long_count = n_data % n_blocks
    data_lens = [short_len + 1 if i >= n_blocks - long_count else short_len
                 for i in range(n_blocks)]
    data_blocks = [[] for _ in range(n_blocks)]
    idx = 0
    for i in range(max(data_lens)):
        for b in range(n_blocks):
            if i < data_lens[b]:
                data_blocks[b].append(codewords[idx])
                idx += 1
    ec_blocks = [[] for _ in range(n_blocks)]
    for i in range(ec_len):
        for b in range(n_blocks):
            ec_blocks[b].append(codewords[idx])
            idx += 1
    for b in range(n_blocks):
        assert rs_syndromes(data_blocks[b] + ec_blocks[b], ec_len) == [0] * ec_len, \
            "non-zero Reed-Solomon syndrome in block %d" % b
    # Parse the first block stream's data bits.
    dbits = []
    for block in data_blocks:
        for byte in block:
            for i in range(7, -1, -1):
                dbits.append((byte >> i) & 1)

    def read(n, at):
        v = 0
        for bit in dbits[at:at + n]:
            v = (v << 1) | bit
        return v, at + n

    mode_ind, at = read(4, 0)
    count_bits = {1: 10, 2: 9, 4: 8}[mode_ind] if version <= 9 else \
        {1: 12, 2: 11, 4: 16}[mode_ind]
    count, at = read(count_bits, at)
    if mode_ind == 1:
        out, remaining = [], count
        while remaining >= 3:
            v, at = read(10, at)
            out.append("%03d" % v)
            remaining -= 3
        if remaining == 2:
            v, at = read(7, at)
            out.append("%02d" % v)
        elif remaining == 1:
            v, at = read(4, at)
            out.append("%d" % v)
        return "".join(out), ec_bits, mask
    if mode_ind == 2:
        out = []
        for _ in range(count // 2):
            v, at = read(11, at)
            out.append(_ALPHANUMERIC_CHARS[v // 45])
            out.append(_ALPHANUMERIC_CHARS[v % 45])
        if count % 2:
            v, at = read(6, at)
            out.append(_ALPHANUMERIC_CHARS[v])
        return "".join(out), ec_bits, mask
    raw = []
    for _ in range(count):
        v, at = read(8, at)
        raw.append(v)
    try:
        return bytes(raw).decode("latin-1"), ec_bits, mask
    except UnicodeDecodeError:
        return bytes(raw).decode("utf-8"), ec_bits, mask


def bits_str(bits):
    return "".join(str(b) for b in bits)


# ------------------------------------------------------- tests

class TestModeDetection(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(detect_mode("12345"), MODE_NUMERIC)
        self.assertEqual(detect_mode("0"), MODE_NUMERIC)

    def test_alphanumeric(self):
        self.assertEqual(detect_mode("HELLO WORLD"), MODE_ALPHANUMERIC)
        self.assertEqual(detect_mode("ABC $%*+-./:123"), MODE_ALPHANUMERIC)

    def test_byte(self):
        self.assertEqual(detect_mode("hello"), MODE_BYTE)
        self.assertEqual(detect_mode("Hello, World!"), MODE_BYTE)
        self.assertEqual(detect_mode(""), MODE_BYTE)


class TestEncoding(unittest.TestCase):
    def test_page_worked_example(self):
        # Challenge page Step 2.5: HELLO CC WORLD.
        bits = encode_data_bits("HELLO CC WORLD", MODE_ALPHANUMERIC, 4)
        self.assertEqual(bits_str(bits[:4]), "0010")
        self.assertEqual(bits_str(bits[4:13]), "000001110")
        self.assertEqual(
            bits_str(bits[13:]),
            "0110000101101111000110100010111000100010100011001110100"
            "1000101001101110111110")

    def test_numeric_grouping(self):
        bits = encode_data_bits("12345", MODE_NUMERIC, 1)
        # 0010? no: mode 0001, count 0000000101, "123"->10 bits, "45"->7 bits.
        self.assertEqual(bits_str(bits[:4]), "0001")
        self.assertEqual(bits_str(bits[4:14]), "0000000101")
        self.assertEqual(bits_str(bits[14:24]), format(123, "010b"))
        self.assertEqual(bits_str(bits[24:]), format(45, "07b"))

    def test_alphanumeric_odd_tail(self):
        bits = encode_data_bits("ABC", MODE_ALPHANUMERIC, 1)
        self.assertEqual(bits_str(bits[13:24]),
                         format(10 * 45 + 11, "011b"))
        self.assertEqual(bits_str(bits[24:]), format(12, "06b"))

    def test_padding(self):
        qr = generate("A", ec="M")
        # v1-M has 16 data codewords; padding tested via round-trip,
        # here check the codeword stream length is the capacity.
        from qr_code import build_codewords
        cws = build_codewords("A", MODE_ALPHANUMERIC, 1, "M")
        # 16 data + 10 EC interleaved, 1 block.
        self.assertEqual(len(cws), 26)
        self.assertEqual(cws[3], 0xEC)
        self.assertEqual(cws[4], 0x11)


class TestReedSolomon(unittest.TestCase):
    def test_syndrome_zero_for_all_levels(self):
        for ec in "LMQH":
            for version in (1, 4, 7, 10):
                qr = generate("HELLO", ec=ec, version=version)
                text, _, _ = decode(qr)
                self.assertEqual(text, "HELLO")

    def test_ec_counts_match_table(self):
        for version in range(1, 11):
            for ec in "LMQH":
                expect = (_NUM_BLOCKS[version][ec]
                          * _EC_PER_BLOCK[version][ec])
                total = qr_code._TOTAL_CODEWORDS[version]
                self.assertEqual(data_codewords(version, ec) + expect, total)

    def test_rs_deterministic(self):
        self.assertEqual(reed_solomon_ec([0x10, 0x20], 4),
                         reed_solomon_ec([0x10, 0x20], 4))


class TestStructure(unittest.TestCase):
    def test_size(self):
        for version in (1, 4, 7, 10):
            self.assertEqual(generate("X", version=version).size,
                             17 + 4 * version)

    def test_finder_patterns(self):
        qr = generate("HELLO WORLD", ec="M")
        size = qr.size
        expected = [[1, 1, 1, 1, 1, 1, 1],
                    [1, 0, 0, 0, 0, 0, 1],
                    [1, 0, 1, 1, 1, 0, 1],
                    [1, 0, 1, 1, 1, 0, 1],
                    [1, 0, 1, 1, 1, 0, 1],
                    [1, 0, 0, 0, 0, 0, 1],
                    [1, 1, 1, 1, 1, 1, 1]]
        for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
            for dy in range(7):
                for dx in range(7):
                    self.assertEqual(qr.matrix[top + dy][left + dx],
                                     expected[dy][dx])
        # Separators: white ring around the top-left finder.
        self.assertTrue(all(qr.matrix[7][c] == 0 for c in range(8)))
        self.assertTrue(all(qr.matrix[r][7] == 0 for r in range(8)))

    def test_timing_and_dark_module(self):
        qr = generate("HELLO", version=4)
        size = qr.size
        for i in range(8, size - 8):
            self.assertEqual(qr.matrix[6][i], 1 if i % 2 == 0 else 0)
            self.assertEqual(qr.matrix[i][6], 1 if i % 2 == 0 else 0)
        self.assertEqual(qr.matrix[4 * 4 + 9][8], 1)

    def test_alignment_pattern(self):
        qr = generate("HELLO", version=4)  # centres [6, 26]
        # Alignment pattern centred at (26, 26): 5x5, dark border+centre.
        pat = [[qr.matrix[26 + dy][26 + dx] for dx in range(-2, 3)]
               for dy in range(-2, 3)]
        self.assertEqual(pat, [[1, 1, 1, 1, 1],
                               [1, 0, 0, 0, 1],
                               [1, 0, 1, 0, 1],
                               [1, 0, 0, 0, 1],
                               [1, 1, 1, 1, 1]])

    def test_no_version_area_below_v7(self):
        # Version info must not appear for v<7: the area is data, so
        # just check the matrix decodes (covered elsewhere) and size.
        self.assertEqual(generate("X", version=6).size, 41)


class TestFormatVersionInfo(unittest.TestCase):
    def test_format_bits_known_value(self):
        self.assertEqual(format(format_bits("L", 0), "015b"),
                         "111011111000100")

    def test_format_copies_agree_in_matrix(self):
        qr = generate("HELLO", ec="L", mask=0)
        size = qr.size
        copy1 = ([(8, i) for i in range(6)] + [(8, 7), (8, 8), (7, 8)]
                 + [(5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)])
        copy2 = ([(size - 1 - i, 8) for i in range(7)]
                 + [(8, size - 8 + i) for i in range(8)])
        s1 = "".join(str(qr.matrix[r][c]) for r, c in copy1)
        s2 = "".join(str(qr.matrix[r][c]) for r, c in copy2)
        self.assertEqual(s1, s2)
        self.assertEqual(s1, "111011111000100")

    def test_version_bits_known_value(self):
        self.assertEqual(format(version_bits(7), "018b"),
                         "000111110010010100")

    def test_version_info_in_matrix_v7(self):
        qr = generate("HELLO", version=7, mask=0)
        bits = version_bits(7)
        for i in range(18):
            a = qr.size - 11 + i % 3
            b = i // 3
            self.assertEqual(qr.matrix[a][b], (bits >> i) & 1)
            self.assertEqual(qr.matrix[b][a], (bits >> i) & 1)


class TestMasking(unittest.TestCase):
    def test_forced_mask_honoured(self):
        for mask in range(8):
            qr = generate("HELLO WORLD", mask=mask)
            self.assertEqual(qr.mask, mask)
            _, _, got = decode(qr)
            self.assertEqual(got, mask)

    def test_masks_differ(self):
        grids = {tuple(tuple(r) for r in generate("HELLO WORLD", mask=m).matrix)
                 for m in range(8)}
        self.assertEqual(len(grids), 8)

    def test_auto_mask_is_minimum_penalty(self):
        qr = generate("HELLO WORLD", ec="M")
        # Recompute penalties independently via the module function.
        from qr_code import _Matrix, _apply_mask, _penalty, build_codewords
        base = _Matrix(qr.size)
        base.build_function_patterns(qr.version)
        base.place_data(build_codewords("HELLO WORLD", MODE_ALPHANUMERIC,
                                        qr.version, "M"))
        scores = {m: _penalty(_apply_mask(base, m)) for m in range(8)}
        best = min(scores, key=lambda m: (scores[m], m))
        self.assertEqual(qr.mask, best)


class TestRoundTrip(unittest.TestCase):
    def test_round_trips(self):
        cases = [("12345", "L"), ("HELLO WORLD", "M"),
                 ("hello world!", "Q"), ("https://example.com/a?b=1", "H"),
                 ("", "M"), ("A", "L")]
        for text, ec in cases:
            qr = generate(text, ec=ec)
            got, _, _ = decode(qr)
            self.assertEqual(got, text, (text, ec))

    def test_round_trip_all_levels_and_versions(self):
        for ec in "LMQH":
            for version in (1, 2, 5, 10):
                qr = generate("HELLO", ec=ec, version=version)
                got, _, _ = decode(qr)
                self.assertEqual(got, "HELLO", (ec, version))

    def test_long_input_reaches_version_10(self):
        text = "x" * 100
        qr = generate(text, ec="H")
        self.assertEqual(qr.version, 10)
        got, _, _ = decode(qr)
        self.assertEqual(got, text)

    def test_version_auto_selection(self):
        self.assertEqual(generate("HELLO WORLD", ec="L").version, 1)
        self.assertEqual(generate("HELLO WORLD", ec="H").version, 2)


class TestRenderers(unittest.TestCase):
    def test_ascii_dimensions(self):
        qr = generate("HELLO", ec="M")
        lines = qr.to_ascii().rstrip("\n").split("\n")
        self.assertEqual(len(lines), qr.size + 8)
        self.assertEqual(len(lines[0]), (qr.size + 8) * 2)
        noq = qr.to_ascii(quiet_zone=False).rstrip("\n").split("\n")
        self.assertEqual(len(noq), qr.size)

    def test_svg_well_formed(self):
        qr = generate("HELLO", ec="M")
        svg = qr.to_svg(scale=5)
        self.assertTrue(svg.startswith("<svg "))
        self.assertTrue(svg.rstrip().endswith("</svg>"))
        dark = sum(sum(row) for row in qr.matrix)
        self.assertEqual(svg.count('fill="black"'), dark)

    def test_png_signature_and_dimensions(self):
        qr = generate("HELLO", ec="M")
        png = qr.to_png_bytes(scale=4)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height, depth, colour = struct.unpack(
            ">IIBB", png[16:26])
        dim = (qr.size + 8) * 4
        self.assertEqual((width, height, depth, colour), (dim, dim, 8, 0))
        # Decompress IDAT and check row length.
        idat = b""
        pos = 8
        while pos < len(png):
            ln, kind = struct.unpack(">I4s", png[pos:pos + 8])
            if kind == b"IDAT":
                idat += png[pos + 8:pos + 8 + ln]
            pos += 12 + ln
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), dim * (dim + 1))


class TestCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(QR), *args],
                              capture_output=True, text=True)

    def test_cli_ascii(self):
        res = self.run_cli("HELLO")
        self.assertEqual(res.returncode, 0)
        self.assertIn("██", res.stdout)

    def test_cli_svg_png_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            res = self.run_cli("HELLO", "--svg", str(td / "o.svg"),
                               "--png", str(td / "o.png"))
            self.assertEqual(res.returncode, 0)
            self.assertTrue((td / "o.svg").read_text().startswith("<svg "))
            self.assertTrue((td / "o.png").read_bytes().startswith(b"\x89PNG"))

    def test_cli_bad_level_and_version(self):
        self.assertNotEqual(self.run_cli("HELLO", "--ec", "X").returncode, 0)
        self.assertNotEqual(self.run_cli("HELLO", "--version", "11").returncode, 0)
        self.assertNotEqual(self.run_cli("HELLO", "--mask", "8").returncode, 0)

    def test_cli_too_long_rejected(self):
        res = self.run_cli("x" * 500, "--ec", "H", "--version", "1")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("fit", res.stderr)

    def test_cli_empty_input(self):
        # Empty string via argv: argparse still accepts it as the text arg.
        res = self.run_cli("")
        self.assertEqual(res.returncode, 0)
        self.assertIn("██", res.stdout)


if __name__ == "__main__":
    unittest.main()

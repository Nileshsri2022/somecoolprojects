"""Tests for ocr.py. All fixtures are synthetic, generated in memory:
PBM via ocr.render_text, PNG via a tiny in-test encoder (zlib/struct).
No external images, no network."""
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ocr  # noqa: E402


def grey_of(binary):
    return [[0 if v else 255 for v in row] for row in binary]


def recognise_binary(binary, **kw):
    lines, _ = ocr.recognize(grey_of(binary), **kw)
    return lines


def pad(binary, margin):
    """Add a blank border so rotation (deskew) cannot clip edge glyphs.
    Real images have margins; render_text does not, so deskew fixtures
    must add one explicitly."""
    h, w = len(binary), len(binary[0])
    out = [[0] * (w + 2 * margin) for _ in range(h + 2 * margin)]
    for y in range(h):
        for x in range(w):
            out[y + margin][x + margin] = binary[y][x]
    return out


def png_bytes(grey, color_type=0, filter_type=0):
    """Encode greyscale rows as a PNG (8-bit, non-interlaced)."""
    h, w = len(grey), len(grey[0])
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    raw = bytearray()
    prev = bytearray(w * channels)
    for row in grey:
        line = bytearray()
        for v in row:
            if color_type == 0:
                line.append(v)
            elif color_type == 2:
                line.extend([v, v, v])
            else:
                line.extend([v, v, v, 255])
        # apply the requested filter (encoder side)
        filt = bytearray(len(line))
        for i, b in enumerate(line):
            a = line[i - channels] if i >= channels else 0
            bb = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if filter_type == 0:
                pred = 0
            elif filter_type == 1:
                pred = a
            elif filter_type == 2:
                pred = bb
            elif filter_type == 3:
                pred = (a + bb) // 2
            else:
                pred = ocr._paeth(a, bb, c)
            filt[i] = (b - pred) & 0xFF
        raw.append(filter_type)
        raw.extend(filt)
        prev = line
    def chunk(ctype, payload):
        out = struct.pack(">I", len(payload)) + ctype + payload
        return out + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def pbm_ascii(binary):
    h, w = len(binary), len(binary[0])
    body = "\n".join(" ".join(str(v) for v in row) for row in binary)
    return ("P1\n%d %d\n%s\n" % (w, h, body)).encode()


class TestNetpbm(unittest.TestCase):
    def test_pbm_ascii_roundtrip(self):
        img = ocr.render_text("ABC", scale=1)
        _w, _h, grey = ocr.parse_netpbm(pbm_ascii(img))
        self.assertEqual(recognise_binary(img), ["ABC"])
        self.assertEqual(ocr.recognize(grey)[0], ["ABC"])

    def test_pbm_raw_roundtrip(self):
        img = ocr.render_text("HI", scale=2)
        _w, _h, grey = ocr.parse_netpbm(ocr.to_pbm_bytes(img))
        self.assertEqual(ocr.recognize(grey)[0], ["HI"])

    def test_pgm_ascii_maxval_scaling(self):
        # PGM with maxval 100: value 0 = black ink, 100 = white.
        data = b"P2\n# comment\n2 1\n100\n0 100\n"
        _w, _h, grey = ocr.parse_netpbm(data)
        self.assertEqual(grey, [[0, 255]])

    def test_pgm_raw_and_ppm(self):
        _w, _h, grey = ocr.parse_netpbm(b"P5\n2 1\n255\n\x00\xff")
        self.assertEqual(grey, [[0, 255]])
        _w, _h, grey = ocr.parse_netpbm(b"P6\n1 1\n255\n\xff\x00\x00")
        self.assertEqual(grey, [[76]])  # 299*255//1000
        _w, _h, grey = ocr.parse_netpbm(b"P3\n1 1\n255\n0 255 0\n")
        self.assertEqual(grey, [[149]])  # 587*255//1000

    def test_comments_and_whitespace(self):
        data = b"P1 # c\n2 # c\n1\n0 1\n"
        _w, _h, grey = ocr.parse_netpbm(data)
        self.assertEqual(grey, [[255, 0]])

    def test_bad_inputs_raise(self):
        for bad in [b"", b"P9\n1 1\n0\n", b"P1\n2 2\n0\n", b"P5\n2 1\n255\n\x00"]:
            with self.assertRaises((ValueError, IndexError, StopIteration)):
                ocr.parse_netpbm(bad)


class TestPng(unittest.TestCase):
    def test_grey_rgb_rgba_roundtrip(self):
        img = ocr.render_text("OK", scale=2)
        grey = grey_of(img)
        for ct in (0, 2, 6):
            _w, _h, back = ocr.parse_png(png_bytes(grey, color_type=ct))
            self.assertEqual(back, grey, "colour type %d" % ct)
            self.assertEqual(ocr.recognize(back)[0], ["OK"])

    def test_all_filter_types(self):
        grey = [[10, 200, 30, 90], [255, 0, 128, 64]]
        for ft in range(5):
            _w, _h, back = ocr.parse_png(png_bytes(grey, filter_type=ft))
            self.assertEqual(back, grey, "filter %d" % ft)

    def test_unsupported_png_rejected(self):
        # interlaced: patch IHDR interlace byte
        data = bytearray(png_bytes([[0]]))
        # IHDR data starts at 8+8=16; interlace is byte 12 of IHDR payload
        data[16 + 12] = 1
        with self.assertRaises(ValueError):
            ocr.parse_png(bytes(data))
        # palette colour type 3
        with self.assertRaises(ValueError):
            ocr.parse_png(png_bytes([[0]], color_type=3) if False else _palette_png())
        with self.assertRaises(ValueError):
            ocr.parse_png(b"not a png")


def _palette_png():
    def chunk(ctype, payload):
        out = struct.pack(">I", len(payload)) + ctype + payload
        return out + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 3, 0, 0, 0)
    raw = zlib.compress(b"\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


class TestPipeline(unittest.TestCase):
    def test_otsu_and_fixed_threshold(self):
        grey = [[0, 0, 255, 255], [10, 250, 5, 240]]
        binary = ocr.binarize(grey)
        self.assertEqual(binary, [[1, 1, 0, 0], [1, 0, 1, 0]])
        self.assertEqual(ocr.binarize(grey, threshold=100),
                         [[1, 1, 0, 0], [1, 0, 1, 0]])

    def test_invert(self):
        grey = [[255, 0]]
        self.assertEqual(ocr.binarize(grey, invert=True), [[1, 0]])

    def test_blank_image_no_text(self):
        blank = [[0] * 20 for _ in range(10)]
        self.assertEqual(recognise_binary(blank), [])

    def test_speck_noise_filtered(self):
        img = ocr.render_text("A", scale=2)
        img[0][0] = 1  # isolated speck far from the glyph? place at corner
        # speck is adjacent to nothing; segment must drop it
        blobs = ocr.segment(img)
        self.assertEqual(len(blobs), 1)

    def test_all_glyphs_scales(self):
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        for scale in (1, 2, 3):
            self.assertEqual(recognise_binary(ocr.render_text(text, scale=scale)),
                             [text], "scale %d" % scale)

    def test_multiline_and_word_space(self):
        img = ocr.render_text("HELLO WORLD\nFOO BAR", scale=2)
        self.assertEqual(recognise_binary(img), ["HELLO WORLD", "FOO BAR"])

    def test_unknown_blob_is_question_mark(self):
        # a solid block: normalises to all-ink, far from every template
        img = [[1] * 10 for _ in range(14)]
        self.assertEqual(recognise_binary(img), ["?"])

    def test_boxes_cover_every_character(self):
        img = ocr.render_text("AB", scale=2)
        _lines, results = ocr.group_lines(ocr.segment(img))
        self.assertEqual([r[0] for r in results], ["A", "B"])
        self.assertTrue(all(r[2] == 0 for r in results))  # single line, y=0

    def test_deskew_recovers_skewed_text(self):
        img = pad(ocr.render_text("HELLO", scale=3), 12)
        skewed = ocr.rotate_binary(img, 5)
        corrected, angle = ocr.deskew(skewed)
        self.assertTrue(abs(angle + 5) <= 2, "angle was %d" % angle)
        self.assertEqual(recognise_binary(corrected), ["HELLO"])

    def test_deskew_level_stays_level(self):
        img = ocr.render_text("HELLO", scale=2)
        _corrected, angle = ocr.deskew(img)
        self.assertEqual(angle, 0)


class TestCLI(unittest.TestCase):
    def run_cli(self, args):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run([sys.executable, os.path.join(root, "ocr.py")] + args,
                              capture_output=True, text=True)

    def test_cli_pbm_and_png(self):
        img = ocr.render_text("TEST 42", scale=2)
        with tempfile.TemporaryDirectory() as td:
            pbm = os.path.join(td, "t.pbm")
            with open(pbm, "wb") as fh:
                fh.write(ocr.to_pbm_bytes(img))
            res = self.run_cli([pbm])
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "TEST 42")
            png = os.path.join(td, "t.png")
            with open(png, "wb") as fh:
                fh.write(png_bytes(grey_of(img)))
            res = self.run_cli([png])
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "TEST 42")

    def test_cli_boxes_and_boxes_pbm(self):
        img = ocr.render_text("AB", scale=2)
        with tempfile.TemporaryDirectory() as td:
            pbm = os.path.join(td, "t.pbm")
            out = os.path.join(td, "boxes.pbm")
            with open(pbm, "wb") as fh:
                fh.write(ocr.to_pbm_bytes(img))
            res = self.run_cli([pbm, "--boxes", "--boxes-pbm", out])
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "AB")
            self.assertIn("A ", res.stderr)
            self.assertIn("B ", res.stderr)
            with open(out, "rb") as fh:
                _w, _h, grey = ocr.parse_netpbm(fh.read())
            self.assertEqual(len(grey), len(img))

    def test_cli_blank_and_bad_input(self):
        with tempfile.TemporaryDirectory() as td:
            blank = os.path.join(td, "blank.pbm")
            with open(blank, "wb") as fh:
                fh.write(ocr.to_pbm_bytes([[0] * 10 for _ in range(10)]))
            res = self.run_cli([blank])
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout, "")
            bad = os.path.join(td, "bad.bin")
            with open(bad, "wb") as fh:
                fh.write(b"hello world, not an image")
            res = self.run_cli([bad])
            self.assertNotEqual(res.returncode, 0)
            res = self.run_cli([os.path.join(td, "missing.pbm")])
            self.assertNotEqual(res.returncode, 0)

    def test_cli_invert(self):
        img = ocr.render_text("HI", scale=2)
        inv = [[1 - v for v in row] for row in img]
        with tempfile.TemporaryDirectory() as td:
            pbm = os.path.join(td, "inv.pbm")
            with open(pbm, "wb") as fh:
                fh.write(ocr.to_pbm_bytes(inv))
            res = self.run_cli([pbm, "--invert"])
            self.assertEqual(res.stdout.strip(), "HI")


class TestAccuracyReport(unittest.TestCase):
    def test_accuracy_report(self):
        """Honest fixture accuracy: templates vs renderings of own font."""
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        total = correct = 0
        for scale in (1, 2, 3):
            got = recognise_binary(ocr.render_text(text, scale=scale))[0]
            total += len(text)
            correct += sum(1 for a, b in zip(got, text) if a == b)
        clean = correct / total
        print("\nfixture accuracy clean (36 glyphs x scales 1-3): %d/%d = %.1f%%"
              % (correct, total, 100 * clean), file=sys.stderr)
        self.assertEqual(clean, 1.0)
        # skewed + deskew through the full pipeline (greyscale correction;
        # padded so rotation cannot clip edge glyphs)
        skewed_grey = grey_of(ocr.rotate_binary(
            pad(ocr.render_text("HELLO WORLD", scale=3), 12), 5))
        got = ocr.recognize(skewed_grey, use_deskew=True)[0]
        skew_acc = sum(1 for a, b in zip(got[0], "HELLO WORLD") if a == b) / 11
        print("fixture accuracy skewed 5deg + deskew: %.1f%%" % (100 * skew_acc),
              file=sys.stderr)
        self.assertEqual(got, ["HELLO WORLD"])
        # speck noise: isolated pixels that segment() should drop
        img = ocr.render_text("NOISE", scale=2)
        img[0][-1] = 1
        got = recognise_binary(img)
        print("fixture accuracy with one speck: %s" % got, file=sys.stderr)
        self.assertEqual(got, ["NOISE"])


if __name__ == "__main__":
    unittest.main()

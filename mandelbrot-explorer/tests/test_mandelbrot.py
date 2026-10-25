"""Tests for mandelbrot.py — no display needed."""
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mandelbrot
from mandelbrot import (
    DEFAULT_VIEW,
    ascii_char,
    escape_count,
    main,
    map_pixel,
    palette_color,
    render_ascii,
    render_png_bytes,
    write_png,
    zoom_view,
)

MAX = 100


class EscapeCountTests(unittest.TestCase):
    def test_inside_points(self):
        for c in (0, -1, -2, 0.25, -0.5, 1j):
            with self.subTest(c=c):
                self.assertEqual(escape_count(complex(c), MAX), MAX)

    def test_outside_points(self):
        cases = {3: 1, 2: 2, 1: 3, 0.5: 5, 2j: 2}
        for c, expected in cases.items():
            with self.subTest(c=c):
                self.assertEqual(escape_count(complex(c), MAX), expected)

    def test_max_iter_caps(self):
        self.assertEqual(escape_count(1, max_iter=2), 2)

    def test_bad_max_iter(self):
        with self.assertRaises(ValueError):
            escape_count(0, max_iter=0)


class MappingAndZoomTests(unittest.TestCase):
    def test_top_left_corner(self):
        self.assertEqual(map_pixel(0, 0, 80, 40, DEFAULT_VIEW), complex(-2, 2))

    def test_linear_mapping(self):
        # Halfway across the grid is halfway across the view.
        self.assertEqual(map_pixel(40, 20, 80, 40, DEFAULT_VIEW), complex(0, 0))

    def test_zoom_halves_around_centre(self):
        self.assertEqual(zoom_view(DEFAULT_VIEW, 0, 0, 2), (-1.0, 1.0, -1.0, 1.0))

    def test_zoom_factor_one_is_identity(self):
        self.assertEqual(zoom_view(DEFAULT_VIEW, 0, 0, 1), DEFAULT_VIEW)

    def test_zoom_off_centre(self):
        view = zoom_view(DEFAULT_VIEW, -1, 0.5, 4)
        self.assertEqual(view, (-1.5, -0.5, 0.0, 1.0))

    def test_bad_zoom(self):
        with self.assertRaises(ValueError):
            zoom_view(DEFAULT_VIEW, 0, 0, 0)


class AsciiTests(unittest.TestCase):
    def test_dimensions(self):
        rows = render_ascii(DEFAULT_VIEW, 20, 10, MAX)
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(len(row) == 20 for row in rows))

    def test_inside_and_outside_chars(self):
        self.assertEqual(ascii_char(MAX, MAX), "@")
        self.assertEqual(ascii_char(0, MAX), " ")
        # Denser gradient for slower escapees.
        self.assertLess(" .:-=+*#%".index(ascii_char(1, MAX)),
                        " .:-=+*#%".index(ascii_char(90, MAX)))

    def test_default_view_shows_set_and_background(self):
        text = "\n".join(render_ascii(DEFAULT_VIEW, 80, 40, MAX))
        self.assertIn("@", text)
        self.assertIn(" ", text)

    def test_far_away_box_has_no_set(self):
        text = "\n".join(render_ascii((10.0, 11.0, 10.0, 11.0), 10, 10, MAX))
        self.assertNotIn("@", text)


class PaletteAndPngTests(unittest.TestCase):
    def test_inside_is_black_every_palette(self):
        for name in mandelbrot.PALETTES:
            self.assertEqual(palette_color(MAX, MAX, name), (0, 0, 0))

    def test_outside_is_valid_rgb(self):
        for name in mandelbrot.PALETTES:
            r, g, b = palette_color(10, MAX, name)
            self.assertTrue(all(0 <= v <= 255 for v in (r, g, b)))

    def test_unknown_palette(self):
        with self.assertRaises(ValueError):
            palette_color(10, MAX, "nope")

    def _parse_png(self, data):
        self.assertTrue(data.startswith(mandelbrot.PNG_SIGNATURE))
        pos = len(mandelbrot.PNG_SIGNATURE)
        chunks = []
        while pos < len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            ctype = data[pos + 4:pos + 8]
            body = data[pos + 8:pos + 8 + length]
            (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
            self.assertEqual(crc, zlib.crc32(ctype + body) & 0xFFFFFFFF)
            chunks.append((ctype, body))
            pos += 12 + length
        self.assertEqual(pos, len(data))
        return chunks

    def test_png_structure_and_dpi(self):
        for dpi, expected_ppm in ((72, 2835), (300, 11811)):
            with self.subTest(dpi=dpi):
                data = render_png_bytes(DEFAULT_VIEW, 20, 10, MAX, "grayscale", dpi)
                chunks = dict(self._parse_png(data))
                self.assertEqual(chunks[b"IHDR"][:8], struct.pack(">II", 20, 10))
                ppm_x, ppm_y, unit = struct.unpack(">IIB", chunks[b"pHYs"])
                self.assertEqual((ppm_x, ppm_y, unit), (expected_ppm, expected_ppm, 1))
                raw = zlib.decompress(chunks[b"IDAT"])
                self.assertEqual(len(raw), 10 * (1 + 20 * 3))
                self.assertTrue(all(raw[i * (1 + 20 * 3)] == 0 for i in range(10)))

    def test_png_centre_black_corner_not(self):
        data = render_png_bytes(DEFAULT_VIEW, 20, 20, MAX, "grayscale", 72)
        chunks = dict(self._parse_png(data))
        raw = zlib.decompress(chunks[b"IDAT"])
        stride = 1 + 20 * 3

        def pixel(px, py):
            off = py * stride + 1 + px * 3
            return tuple(raw[off:off + 3])

        self.assertEqual(pixel(10, 10), (0, 0, 0))  # centre: inside the set
        self.assertNotEqual(pixel(0, 0), (0, 0, 0))  # corner: outside

    def test_write_png_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.png")
            write_png(path, DEFAULT_VIEW, 8, 8, MAX, "fire", 72)
            with open(path, "rb") as fh:
                self.assertTrue(fh.read(8) == mandelbrot.PNG_SIGNATURE)


class CliTests(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_ascii_output_dimensions(self):
        code, out = self._run(["--width", "20", "--height", "10"])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 10)
        self.assertTrue(all(len(line) == 20 for line in lines))

    def test_box_and_zoom_runs(self):
        _, out = self._run(["--box", "-1.75", "1.75", "-1.75", "1.75",
                            "--width", "10", "--height", "5"])
        self.assertEqual(len(out.splitlines()), 5)
        _, out = self._run(["--center", "-0.5", "0", "--zoom", "2",
                            "--width", "10", "--height", "5"])
        self.assertEqual(len(out.splitlines()), 5)

    def test_png_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.png")
            code, _ = self._run(["--output", path, "--width", "8",
                                 "--height", "8", "--dpi", "300"])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.getsize(path) > 0)

    def test_bad_arguments_exit_nonzero(self):
        for argv in (["--width", "0"], ["--zoom", "0"],
                     ["--box", "1", "-1", "0", "1"],
                     ["--palette", "nope"],
                     ["--output", "out.jpg"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as ctx:
                with mock.patch.object(sys, "stderr", io.StringIO()):
                    main(argv)
            self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

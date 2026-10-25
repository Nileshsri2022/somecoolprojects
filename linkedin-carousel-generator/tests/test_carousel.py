"""Tests for carousel.py — LinkedIn Carousel Generator (entry 21)."""
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carousel import (CarouselError, Theme, build_html, build_pdf,  # noqa: E402
                      jpeg_dimensions, layout_slide, parse_deck,
                      parse_hex, wrap_text)

FIXTURE_JPG = os.path.join(os.path.dirname(__file__), "fixtures", "sample.jpg")

SAMPLE = """# Stop shipping features nobody asked for
- Talk to five users first
- Write down the one problem

---
# The interview script
Thirty minutes. Five questions. No feature talk.
"""


def check_xref(test, pdf):
    """Every xref offset must point at the start of its object."""
    m = re.search(rb"startxref\n(\d+)\n%%EOF", pdf)
    test.assertIsNotNone(m, "missing startxref trailer")
    xref = pdf[int(m.group(1)):]
    lines = xref.split(b"\n")
    test.assertEqual(lines[0], b"xref")
    count = int(lines[1].split()[1])
    offsets = [int(lines[3 + i].split()[0]) for i in range(count - 1)]
    for i, off in enumerate(offsets, start=1):
        test.assertTrue(pdf[off:].startswith(f"{i} 0 obj".encode()),
                        f"xref offset for object {i} is wrong")


class TestParseHex(unittest.TestCase):
    def test_with_and_without_hash(self):
        self.assertEqual(parse_hex("#ff0000"), (255, 0, 0))
        self.assertEqual(parse_hex("00ff10"), (0, 255, 16))

    def test_rejects_bad(self):
        for bad in ("fff", "gggggg", "1234567", "", "#12"):
            with self.assertRaises(CarouselError):
                parse_hex(bad)


class TestParseDeck(unittest.TestCase):
    def test_single_and_multi(self):
        deck = parse_deck(SAMPLE)
        self.assertEqual(len(deck), 2)
        self.assertEqual(deck[0].title, "Stop shipping features nobody asked for")
        self.assertEqual(deck[0].body[0], "- Talk to five users first")
        self.assertEqual(deck[1].body, ["Thirty minutes. Five questions. No feature talk."])

    def test_heading_hash_stripped_and_empty_slides_dropped(self):
        deck = parse_deck("## Title\nbody\n---\n---\n# Second\n")
        self.assertEqual([s.title for s in deck], ["Title", "Second"])

    def test_empty_raises(self):
        for bad in ("", "   \n", "---\n---\n"):
            with self.assertRaises(CarouselError):
                parse_deck(bad)

    def test_bg_directive(self):
        deck = parse_deck("!bg photo.jpg 0.3\n# T\nbody\n---\n# U\n")
        self.assertEqual(deck[0].bg_image, "photo.jpg")
        self.assertAlmostEqual(deck[0].bg_opacity, 0.3)
        self.assertEqual(deck[0].title, "T")  # directive is not rendered
        self.assertAlmostEqual(deck[1].bg_opacity, 0.15)  # default

    def test_bg_bad_opacity(self):
        with self.assertRaises(CarouselError):
            parse_deck("!bg photo.jpg 2\n# T\n")
        with self.assertRaises(CarouselError):
            parse_deck("!bg\n# T\n")


class TestWrap(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(wrap_text("hello world", 500, 36), ["hello world"])

    def test_wraps_within_width(self):
        lines = wrap_text("one two three four five six", 100, 36)
        self.assertTrue(len(lines) > 1)
        for line in lines:
            self.assertLessEqual(len(line) * 36 * 0.5, 100 + 18)  # one char slack

    def test_long_word_hard_split(self):
        lines = wrap_text("a" * 100, 100, 36)
        self.assertTrue(all(len(ln) * 36 * 0.5 <= 100 + 18 for ln in lines))
        self.assertEqual("".join(lines), "a" * 100)

    def test_empty(self):
        self.assertEqual(wrap_text("   ", 100, 36), [])


class TestLayout(unittest.TestCase):
    def test_footer_and_order_and_bounds(self):
        deck = parse_deck(SAMPLE)
        lines = layout_slide(deck[0], Theme(author="Ada", handle="@ada"), 0, 2)
        self.assertEqual(lines[-1].text, "1 / 2")
        texts = [ln.text for ln in lines]
        self.assertIn("Ada  @ada", texts)
        title_idx = next(i for i, t in enumerate(texts)
                         if t.startswith("Stop shipping"))
        self.assertLess(texts.index("Ada  @ada"), title_idx)
        for ln in lines:
            self.assertGreaterEqual(ln.x, 0)
            self.assertLessEqual(ln.x, 1080)
            self.assertGreaterEqual(ln.y, 0)
            self.assertLessEqual(ln.y, 1080)

    def test_no_author_no_author_line(self):
        deck = parse_deck("# T\nbody\n")
        lines = layout_slide(deck[0], Theme(), 0, 1)
        self.assertEqual(lines[-1].text, "1 / 1")
        self.assertEqual(len(lines), 3)  # title, body, footer


class TestJpeg(unittest.TestCase):
    def test_real_jpeg_dimensions(self):
        self.assertEqual(jpeg_dimensions(FIXTURE_JPG), (8, 8))

    def test_non_jpeg_rejected(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
            path = fh.name
        try:
            with self.assertRaises(CarouselError):
                jpeg_dimensions(path)
        finally:
            os.unlink(path)


class TestPdf(unittest.TestCase):
    def test_structure_page_count_and_content(self):
        deck = parse_deck(SAMPLE)
        pdf = build_pdf(deck, Theme(author="Ada", handle="@ada"))
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertEqual(pdf.count(b"/Type /Page "), 2)
        self.assertIn(b"Stop shipping features", pdf)
        self.assertIn(b"The interview script", pdf)
        self.assertIn(b"1 / 2", pdf)
        self.assertIn(b"2 / 2", pdf)
        self.assertIn(b"/MediaBox [0 0 1080 1080]", pdf)
        check_xref(self, pdf)

    def test_theme_colours_and_font(self):
        deck = parse_deck("# T\nbody\n")
        pdf = build_pdf(deck, Theme(bg=(255, 0, 0), fg=(0, 255, 0),
                                    font="Times-Roman", font_size=40))
        self.assertIn(b"1.0000 0.0000 0.0000 rg", pdf)
        self.assertIn(b"/BaseFont /Times-Roman", pdf)

    def test_bg_image_and_opacity_and_avatar(self):
        deck = parse_deck(f"!bg {FIXTURE_JPG} 0.3\n# T\nbody\n")
        pdf = build_pdf(deck, Theme(avatar=FIXTURE_JPG))
        self.assertIn(b"/Subtype /Image", pdf)
        self.assertIn(b"/Filter /DCTDecode", pdf)
        self.assertIn(b"/ca 0.3000", pdf)
        check_xref(self, pdf)

    def test_bad_font_and_size(self):
        deck = parse_deck("# T\n")
        with self.assertRaises(CarouselError):
            build_pdf(deck, Theme(font="Comic Sans"))
        with self.assertRaises(CarouselError):
            build_pdf(deck, Theme(font_size=0))


class TestHtml(unittest.TestCase):
    def test_sections_nav_counter_and_escaping(self):
        deck = parse_deck("# A <b> & Co\nbody\n---\n# B\n")
        out = build_html(deck, Theme(bg=(1, 2, 3), author="Ada"))
        self.assertEqual(out.count('<section class="slide"'), 2)
        self.assertIn("width: 1080px; height: 1080px", out)
        self.assertIn("1 / 2", out)
        self.assertIn('id="prev"', out)
        self.assertIn('id="next"', out)
        self.assertIn("A &lt;b&gt; &amp; Co", out)
        self.assertIn("Ada", out)

    def test_bg_image_opacity(self):
        deck = parse_deck("!bg pic.jpg 0.25\n# T\n")
        out = build_html(deck, Theme())
        self.assertIn('src="pic.jpg"', out)
        self.assertIn("opacity:0.25", out)


class TestCli(unittest.TestCase):
    def run_cli(self, args, cwd):
        return subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))), "carousel.py")]
            + args, capture_output=True, text=True, cwd=cwd)

    def test_build_pdf_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "deck.txt")
            with open(src, "w") as fh:
                fh.write(SAMPLE)
            res = self.run_cli(["build", src, "--pdf", "out.pdf",
                                "--preview", "out.html",
                                "--author", "Ada", "--handle", "@ada"], tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("2 slides", res.stdout)
            with open(os.path.join(tmp, "out.pdf"), "rb") as fh:
                pdf = fh.read()
            self.assertEqual(pdf.count(b"/Type /Page "), 2)
            check_xref(self, pdf)
            with open(os.path.join(tmp, "out.html")) as fh:
                self.assertEqual(fh.read().count('<section class="slide"'), 2)

    def test_build_with_jpeg_bg(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "deck.txt")
            with open(src, "w") as fh:
                fh.write(f"!bg {FIXTURE_JPG}\n# T\nbody\n")
            res = self.run_cli(["build", src, "--pdf", "out.pdf"], tmp)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(os.path.getsize(os.path.join(tmp, "out.pdf")) > 0)

    def test_error_cases_write_no_output(self):
        cases = [
            ("# T\n", ["--bg", "zzz"]),          # bad colour
            ("# T\n", ["--font-size", "0"]),     # bad size
            ("", []),                             # empty deck
        ]
        for text, extra in cases:
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "deck.txt")
                with open(src, "w") as fh:
                    fh.write(text)
                res = self.run_cli(["build", src, "--pdf", "out.pdf"] + extra, tmp)
                self.assertNotEqual(res.returncode, 0, res.stdout)
                self.assertFalse(os.path.exists(os.path.join(tmp, "out.pdf")))
        with tempfile.TemporaryDirectory() as tmp:  # missing input
            res = self.run_cli(["build", os.path.join(tmp, "nope.txt"),
                                "--pdf", "out.pdf"], tmp)
            self.assertNotEqual(res.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out.pdf")))


if __name__ == "__main__":
    unittest.main()

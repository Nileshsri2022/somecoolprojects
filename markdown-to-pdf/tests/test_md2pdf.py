"""Tests for md2pdf.py — Markdown To PDF Editor (challenge-md-to-pdf)."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import md2pdf
from md2pdf import (Style, _file_changed, convert, edit_loop, parse,
                    render_html, render_pdf)

SAMPLE = """# Hello World

This is a **bold** and *italic* paragraph with `code` and a
[link](https://example.com).

## Shopping

- apples
- bananas
  - ripe ones
- cherries

1. first
2. second

```python
print("hi")
```

> A wise quote.

![Alt text](https://example.com/logo.png)

---
"""

PDFTOTEXT = shutil.which("pdftotext")


def pdf_text(pdf_bytes):
    """Extract text via pdftotext, or fall back to raw-byte checks."""
    if PDFTOTEXT is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf_bytes)
        path = fh.name
    try:
        out = subprocess.run([PDFTOTEXT, path, "-"], capture_output=True,
                             text=True, timeout=30)
        return out.stdout
    finally:
        os.unlink(path)


def assert_text_contains(test, pdf_bytes, needle):
    text = pdf_text(pdf_bytes)
    if text is not None:
        test.assertIn(needle, text)
    else:
        test.assertIn(needle.encode("latin-1"), pdf_bytes)


class TestParser(unittest.TestCase):
    def test_headings(self):
        blocks = parse("# One\n## Two\n### Three\n#### Four\n##### Five\n###### Six\n")
        self.assertEqual([b[1] for b in blocks if b[0] == "heading"],
                         [1, 2, 3, 4, 5, 6])

    def test_hash_without_space_is_paragraph(self):
        blocks = parse("#nospace\n")
        self.assertEqual(blocks[0][0], "para")

    def test_bold_italic_code(self):
        blocks = parse("**bold** __also__ *ital* _also_ `code`\n")
        kinds = [s[0] for s in blocks[0][1]]
        self.assertIn("bold", kinds)
        self.assertIn("italic", kinds)
        self.assertIn("code", kinds)

    def test_bold_with_italic_inside(self):
        blocks = parse("**bold and *italic* inside**\n")
        kinds = [s[0] for s in blocks[0][1]]
        self.assertIn("bolditalic", kinds)

    def test_unmatched_delimiter_left_literal(self):
        blocks = parse("a * b\n")
        joined = "".join(s[1] for s in blocks[0][1])
        self.assertIn("*", joined)

    def test_code_not_rescanned(self):
        blocks = parse("`a **b** c`\n")
        self.assertEqual([(s[0], s[1]) for s in blocks[0][1]],
                         [("code", "a **b** c")])

    def test_link_and_image(self):
        blocks = parse("[Text](https://example.com) ![Alt](img.png)\n")
        spans = blocks[0][1]
        self.assertEqual(spans[0], ("link", "Text", "https://example.com"))
        self.assertIn("image", [s[0] for s in spans])  # after the " " span

    def test_lists_and_nesting(self):
        blocks = parse("- a\n- b\n  - nested\n1. one\n2. two\n")
        self.assertEqual(blocks[0][0], "ul")
        # nested list is a subblock of the second item
        self.assertEqual(blocks[0][1][1][1][0][0], "ul")
        self.assertEqual(blocks[1][0], "ol")

    def test_fenced_code_language_ignored(self):
        blocks = parse("```python\nx = 1\n```\n")
        self.assertEqual(blocks, [("code", "x = 1")])

    def test_quote_hr_paragraphs(self):
        blocks = parse("one\n\ntwo\n\n> quoted\n\n---\n")
        kinds = [b[0] for b in blocks]
        self.assertEqual(kinds, ["para", "para", "quote", "hr"])

    def test_snake_case_not_italic(self):
        blocks = parse("my_variable_name here\n")
        kinds = [s[0] for s in blocks[0][1]]
        self.assertNotIn("italic", kinds)


class TestHtml(unittest.TestCase):
    def test_elements_and_escaping(self):
        blocks = parse(SAMPLE)
        out = render_html(blocks, Style())
        for needle in ("<h1>", "<strong>", "<em>", "<code>",
                       '<a href="https://example.com">', "<ul>", "<ol>",
                       "<li>", "<pre>", "<blockquote>", "<hr>"):
            self.assertIn(needle, out)
        out2 = render_html(parse("a < b & c\n"), Style())
        self.assertIn("a &lt; b &amp; c", out2)

    def test_style_flags_reflected(self):
        out = render_html(parse("# Hi\n"), Style(bg=(1, 0, 0), fg=(0, 0, 1),
                                              font_size=20))
        self.assertIn("background: #ff0000", out)
        self.assertIn("color: #0000ff", out)
        self.assertIn("font-size: 20", out)


class TestPdf(unittest.TestCase):
    def test_structure_header_xref_eof(self):
        pdf = render_pdf(parse(SAMPLE), Style())
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        # xref offsets must point at real object headers
        m = re.search(rb"startxref\n(\d+)\n", pdf)
        xref_pos = int(m.group(1))
        self.assertEqual(pdf[xref_pos:xref_pos + 4], b"xref")
        header = pdf[xref_pos:].split(b"\n")
        offsets = [int(line.split()[0]) for line in header[2:]
                   if line.strip().endswith(b"n")]
        for off in offsets:
            self.assertRegex(pdf[off:off + 20], rb"\d+ 0 obj")

    def test_sample_text_extractable(self):
        pdf = render_pdf(parse(SAMPLE), Style())
        for needle in ("Hello World", "bold", "italic", "apples",
                       "ripe ones", "first", "hi", "wise quote",
                       "Image: Alt text"):
            assert_text_contains(self, pdf, needle)

    def test_page_sizes(self):
        a4 = render_pdf(parse("# Hi\n"), Style(page="a4"))
        letter = render_pdf(parse("# Hi\n"), Style(page="letter"))
        self.assertIn(b"/MediaBox [0 0 595 842]", a4)
        self.assertIn(b"/MediaBox [0 0 612 792]", letter)

    def test_background_fill_present(self):
        pdf = render_pdf(parse("# Hi\n"), Style(bg=(1, 0, 0)))
        self.assertIn(b"1.000 0.000 0.000 rg 0 0 595 842 re f", pdf)

    def test_larger_font_size_larger_operators(self):
        small = render_pdf(parse("# Hi\n"), Style(font_size=12))
        big = render_pdf(parse("# Hi\n"), Style(font_size=20))
        self.assertIn(b"24.0 Tf", small)  # H1 = 12 * 2.0
        self.assertIn(b"40.0 Tf", big)   # H1 = 20 * 2.0

    def test_long_document_paginates(self):
        doc = "\n\n".join(f"Paragraph number {i} with some words in it."
                          for i in range(200))
        pdf = render_pdf(parse(doc), Style())
        pages = re.findall(rb"/Type /Page[^s]", pdf)
        self.assertGreater(len(pages), 1)

    def test_empty_document_is_valid_pdf(self):
        pdf = render_pdf(parse(""), Style())
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))


class TestCli(unittest.TestCase):
    def run_cli(self, *argv):
        return md2pdf.main(list(argv))

    def test_convert_and_preview_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "doc.md")
            with open(src, "w") as fh:
                fh.write(SAMPLE)
            out = os.path.join(tmp, "doc.pdf")
            prev = os.path.join(tmp, "doc.html")
            self.assertEqual(self.run_cli("convert", src, "-o", out,
                                          "--preview", prev), 0)
            self.assertTrue(os.path.exists(out))
            self.assertTrue(os.path.exists(prev))
            with open(out, "rb") as fh:
                pdf = fh.read()
            assert_text_contains(self, pdf, "Hello World")
            with open(prev) as fh:
                self.assertIn("<h1>", fh.read())

    def test_convert_default_output_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "doc.md")
            with open(src, "w") as fh:
                fh.write("# Hi\n")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertEqual(self.run_cli("convert", src), 0)
                self.assertTrue(os.path.exists(os.path.join(tmp, "doc.pdf")))
            finally:
                os.chdir(cwd)

    def test_missing_file_and_bad_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o.pdf")
            self.assertNotEqual(self.run_cli("convert", "/nonexistent/x.md",
                                             "-o", out), 0)
            self.assertFalse(os.path.exists(out))
            src = os.path.join(tmp, "d.md")
            with open(src, "w") as fh:
                fh.write("# Hi\n")
            self.assertNotEqual(self.run_cli("convert", src, "-o", out,
                                             "--bg", "zzz"), 0)
            self.assertNotEqual(self.run_cli("convert", src, "-o", out,
                                             "--font", "comic"), 0)
            self.assertNotEqual(self.run_cli("convert", src, "-o", out,
                                             "--page", "huge"), 0)
            self.assertNotEqual(self.run_cli("convert", src, "-o", out,
                                             "--font-size", "0"), 0)
            self.assertFalse(os.path.exists(out))

    def test_preview_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "d.md")
            with open(src, "w") as fh:
                fh.write("# Hi\n")
            out = os.path.join(tmp, "p.html")
            self.assertEqual(self.run_cli("preview", src, "-o", out), 0)
            with open(out) as fh:
                self.assertIn("Hi", fh.read())


class TestEditLoop(unittest.TestCase):
    def drive(self, lines, script):
        out = io.StringIO()
        pdf_calls = []
        final = edit_loop(lines, io.StringIO(script), out,
                          on_pdf=pdf_calls.append)
        return final, out.getvalue(), pdf_calls

    def test_append_insert_replace_delete_print(self):
        final, out, _ = self.drive(
            ["# Title", "old"],
            "print\nappend\nnew line\n.\ninsert 2\nmid\n.\n"
            "replace 3\nreplaced\n.\ndelete 1\nquit\n")
        self.assertEqual(final, ["mid", "replaced", "new line"])
        self.assertIn("1: # Title", out)

    def test_pdf_callback_and_unknown_command(self):
        final, out, calls = self.drive(
            ["# Hi"], "bogus\npdf\nquit\n")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], ["# Hi"])
        self.assertIn("Unknown command: bogus", out)
        self.assertIn("PDF written.", out)

    def test_out_of_range_does_not_crash(self):
        final, out, _ = self.drive(["a"], "delete 9\nquit\n")
        self.assertEqual(final, ["a"])
        self.assertIn("out of range", out)

    def test_file_changed_helper(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write("x")
            path = fh.name
        try:
            mtime = os.path.getmtime(path)
            changed, _ = _file_changed(path, mtime)
            self.assertFalse(changed)
            os.utime(path, (mtime + 5, mtime + 5))
            changed, _ = _file_changed(path, mtime)
            self.assertTrue(changed)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

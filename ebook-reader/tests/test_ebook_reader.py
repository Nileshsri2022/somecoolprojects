import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader import (AnnotationStore, Book, EpubError, Library,
                          Reader, Theme, THEMES, load_theme, lookup_word,
                          paginate, parse_epub, render_page, save_theme,
                          search_in_book, wikipedia_summary, xhtml_to_text)

CH1 = """<html><head><title>Chapter One</title></head><body>
<h1>Chapter One</h1><p>The brave reader opened the book and began a long journey.</p>
<p>It was a story of an ancient kingdom and a dragon.</p>
<script>var secret = 1;</script><style>p { color: red; }</style>
<ul><li>first item</li><li>second item</li></ul></body></html>"""
CH2 = """<html><body><h1>Chapter Two</h1>
<p>The journey continued across the ocean to a quiet island.</p>
<p>There the reader found treasure and a mystery.</p></body></html>"""
CH3 = """<html><body><h1>Chapter Three</h1>
<p>A different tale, with a garden and a letter about memory.</p></body></html>"""


def make_epub2(path: Path) -> Path:
    """EPUB 2 with NCX TOC; manifest order deliberately differs from spine."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
   media-type="application/oebps-package+xml"/></rootfiles></container>""")
        zf.writestr("OEBPS/content.opf", """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>The Test Book</dc:title><dc:creator>Jane Tester</dc:creator>
    <dc:language>en</dc:language><dc:identifier>test-1</dc:identifier>
  </metadata>
  <manifest>
    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>
    <item id="css" href="style.css" media-type="text/css"/>
  </manifest>
  <spine toc="ncx"><itemref idref="ch1"/><itemref idref="ch2"/></spine>
</package>""")
        zf.writestr("OEBPS/toc.ncx", """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
 <navMap>
  <navPoint id="n1"><navLabel><text>Chapter One</text></navLabel>
   <content src="ch1.xhtml"/></navPoint>
  <navPoint id="n2"><navLabel><text>Chapter Two</text></navLabel>
   <content src="ch2.xhtml"/></navPoint>
 </navMap></ncx>""")
        zf.writestr("OEBPS/ch1.xhtml", CH1)
        zf.writestr("OEBPS/ch2.xhtml", CH2)
        zf.writestr("OEBPS/cover.jpg", b"\x00\x01")
        zf.writestr("OEBPS/style.css", "p { color: black; }")
    return path


def make_epub3(path: Path) -> Path:
    """EPUB 3 with nav-document TOC and no author/language."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf"
   media-type="application/oebps-package+xml"/></rootfiles></container>""")
        zf.writestr("content.opf", """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Second Book</dc:title>
  </metadata>
  <manifest>
    <item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>""")
        zf.writestr("nav.xhtml", """<html xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol>
 <li><a href="c1.xhtml">Chapter Three</a></li>
</ol></nav></body></html>""")
        zf.writestr("c1.xhtml", CH3)
    return path


class EpubParsingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.epub2 = make_epub2(self.dir / "test-book.epub")
        self.epub3 = make_epub3(self.dir / "second.epub")

    def tearDown(self):
        self.tmp.cleanup()

    def test_epub2_metadata_and_spine_order(self):
        book = parse_epub(self.epub2)
        self.assertEqual(book.title, "The Test Book")
        self.assertEqual(book.author, "Jane Tester")
        self.assertEqual(book.language, "en")
        self.assertEqual(book.identifier, "test-1")
        # Spine order wins over manifest order.
        self.assertEqual([c.title for c in book.chapters],
                         ["Chapter One", "Chapter Two"])

    def test_epub2_text_extraction(self):
        book = parse_epub(self.epub2)
        text = book.chapters[0].text
        self.assertIn("brave reader opened the book", text)
        self.assertIn("- first item", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("color: red", text)

    def test_epub2_ncx_toc_and_cover(self):
        book = parse_epub(self.epub2)
        self.assertEqual([e.title for e in book.toc],
                         ["Chapter One", "Chapter Two"])
        self.assertEqual(book.toc[0].chapter_id, "ch1")
        self.assertEqual(book.cover_href, "cover.jpg")
        self.assertIn("style.css", book.stylesheets)

    def test_epub3_nav_toc_and_missing_metadata(self):
        book = parse_epub(self.epub3)
        self.assertEqual(book.title, "Second Book")
        self.assertEqual(book.author, "")
        self.assertEqual(book.language, "")
        self.assertEqual([e.title for e in book.toc], ["Chapter Three"])
        self.assertEqual(book.toc[0].chapter_id, "c1")

    def test_corrupt_zip_raises(self):
        bad = self.dir / "bad.epub"
        bad.write_bytes(b"this is not a zip")
        with self.assertRaises(EpubError):
            parse_epub(bad)

    def test_missing_spine_file_raises(self):
        path = self.dir / "broken.epub"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("META-INF/container.xml",
                        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                        '<rootfiles><rootfile full-path="content.opf"/></rootfiles></container>')
            zf.writestr("content.opf",
                        '<package xmlns="http://www.idpf.org/2007/opf"><metadata/>'
                        '<manifest><item id="a" href="gone.xhtml" media-type="application/xhtml+xml"/></manifest>'
                        '<spine><itemref idref="a"/></spine></package>')
        with self.assertRaises(EpubError):
            parse_epub(path)

    def test_missing_file_raises(self):
        with self.assertRaises(EpubError):
            parse_epub(self.dir / "nope.epub")


class PaginationReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = parse_epub(make_epub2(Path(self.tmp.name) / "b.epub"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reflow_preserves_text(self):
        text = self.book.chapters[0].text
        narrow = paginate(text, 40, 3)
        wide = paginate(text, 80, 3)
        self.assertGreater(len(narrow), len(wide))
        joined = lambda pages: "\n".join(l for p in pages for l in p if l)
        # Paragraph text survives rewrapping (line breaks differ only).
        self.assertEqual(" ".join(joined(narrow).split()),
                         " ".join(joined(wide).split()))

    def test_paginate_empty(self):
        self.assertEqual(paginate("", 80, 10), [])
        self.assertEqual(paginate("hello world", 80, 2), [["hello world"]])

    def test_reader_navigation_and_progress(self):
        reader = Reader(self.book, width=80, lines_per_page=2)
        self.assertEqual(reader.progress, 0.0)
        self.assertTrue(reader.next_chapter())
        self.assertEqual(reader.chapter_index, 1)
        self.assertGreater(reader.progress, 0.0)
        self.assertTrue(reader.goto_toc("Chapter One"))
        self.assertEqual(reader.chapter_index, 0)
        self.assertFalse(reader.goto_toc("No Such Chapter"))
        self.assertFalse(reader.prev_chapter())
        # Walk to the end; next_page eventually returns False.
        steps = 0
        while reader.next_page() and steps < 500:
            steps += 1
        self.assertLessEqual(reader.progress, 1.0)

    def test_search_in_book(self):
        results = search_in_book(self.book, "dragon")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chapter_title, "Chapter One")
        self.assertIn("dragon", results[0].snippet)
        self.assertEqual(search_in_book(self.book, "absentword"), [])
        self.assertEqual(search_in_book(self.book, "  "), [])


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.lib = Library()
        self.lib.import_epub(make_epub2(self.dir / "a.epub"))
        self.lib.import_epub(make_epub3(self.dir / "b.epub"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_sort_and_filter(self):
        self.assertEqual([b.title for b in self.lib.list_books("title")],
                         ["Second Book", "The Test Book"])
        self.assertEqual([b.title for b in self.lib.list_books("author")],
                         ["Second Book", "The Test Book"])  # "" sorts first
        self.assertEqual(len(self.lib.filter_books(author="Jane")), 1)
        self.assertEqual(len(self.lib.filter_books(language="en")), 1)
        self.assertEqual(len(self.lib.filter_books(query="second")), 1)
        self.assertEqual(self.lib.filter_books(query="zzz"), [])

    def test_search_all_one_and_many_books(self):
        one = self.lib.search_all("dragon")
        self.assertEqual(len(one), 1)
        self.assertEqual(one[0].book_title, "The Test Book")
        # "and" appears in both books' text.
        both = self.lib.search_all("and")
        self.assertGreaterEqual(len({r.book_title for r in both}), 2)
        self.assertEqual(self.lib.search_all("absentword"), [])
        self.assertEqual(self.lib.search_all(""), [])

    def test_text_import_convenience(self):
        txt = self.dir / "notes.txt"
        txt.write_text("Hello plain text world.", encoding="utf-8")
        book = self.lib.import_text(txt)
        self.assertEqual(len(book.chapters), 1)
        self.assertIn("Hello plain text", book.chapters[0].text)

    def test_unsupported_import(self):
        with self.assertRaises(EpubError):
            self.lib.import_file(self.dir / "x.pdf")


class ThemeTests(unittest.TestCase):
    def test_presets_differ(self):
        self.assertNotEqual(THEMES["dark"].foreground, THEMES["light"].foreground)

    def test_font_size_narrows_width(self):
        small = Theme(font_size=12)
        large = Theme(font_size=24)
        self.assertGreater(small.effective_width(80), large.effective_width(80))
        self.assertGreaterEqual(large.effective_width(80), 20)

    def test_line_spacing(self):
        theme = Theme(line_spacing=1)
        self.assertEqual(render_page(["a", "b"], theme, use_ansi=False),
                         "a\n\nb")
        self.assertEqual(render_page(["a", "b"], Theme(), use_ansi=False),
                         "a\nb")

    def test_settings_round_trip_and_corrupt_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d)
            theme = Theme(name="dark", font_size=20, margins=4)
            save_theme(data, theme)
            loaded = load_theme(data)
            self.assertEqual(loaded.name, "dark")
            self.assertEqual(loaded.font_size, 20)
            (data / "settings.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(load_theme(data).name, "light")


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.book = parse_epub(make_epub2(self.dir / "b.epub"))
        self.store = AnnotationStore(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        ch = self.book.chapters[0]
        idx = ch.text.find("brave reader")
        self.store.add_bookmark(self.book, ch.id, idx, label="start")
        self.store.add_highlight(self.book, ch.id, idx, idx + 12,
                                 colour="green", note="great line")
        self.store.save()
        reloaded = AnnotationStore(self.dir)
        self.assertEqual(len(reloaded.bookmarks(self.book)), 1)
        hls = reloaded.highlights(self.book)
        self.assertEqual(len(hls), 1)
        self.assertEqual(hls[0]["note"], "great line")
        self.assertEqual(AnnotationStore.resolve_highlight(self.book, hls[0]),
                         (idx, idx + 12))

    def test_highlight_survives_repaginating(self):
        ch = self.book.chapters[0]
        idx = ch.text.find("dragon")
        hl = self.store.add_highlight(self.book, ch.id, idx, idx + 6)
        # Repagination changes lines only, never chapter text/offsets.
        for width in (80, 40, 30):
            pages = paginate(ch.text, width, 5)
            self.assertTrue(pages)
            self.assertEqual(AnnotationStore.resolve_highlight(self.book, hl),
                             (idx, idx + 6))

    def test_highlight_resolves_after_text_moves(self):
        ch = self.book.chapters[0]
        hl = {"chapter_id": ch.id, "start": 0, "end": 5,
              "text": "brave reader", "colour": "yellow", "note": ""}
        span = AnnotationStore.resolve_highlight(self.book, hl)
        self.assertIsNotNone(span)
        self.assertEqual(self.book.chapters[0].text[span[0]:span[1]],
                         "brave reader")

    def test_deleted_text_resolves_to_none(self):
        hl = {"chapter_id": self.book.chapters[0].id, "start": 0, "end": 5,
              "text": "this phrase is nowhere", "colour": "yellow", "note": ""}
        self.assertIsNone(AnnotationStore.resolve_highlight(self.book, hl))

    def test_listing_is_per_book(self):
        other = Book(path="/tmp/other.epub", title="Other")
        self.store.add_bookmark(self.book, self.book.chapters[0].id, 0)
        self.assertEqual(self.store.bookmarks(other), [])


class DictionaryWikipediaTests(unittest.TestCase):
    def test_known_and_unknown(self):
        self.assertIn("luck", lookup_word("serendipity"))
        self.assertIn("luck", lookup_word("Serendipity!"))
        self.assertIsNone(lookup_word("flibbertygibbet"))

    def test_lookup_does_not_move_reader(self):
        with tempfile.TemporaryDirectory() as d:
            book = parse_epub(make_epub2(Path(d) / "b.epub"))
            reader = Reader(book)
            reader.next_chapter()
            before = (reader.chapter_index, reader.page_index)
            lookup_word("dragon")
            self.assertEqual((reader.chapter_index, reader.page_index), before)

    def test_wikipedia_injected_opener(self):
        class FakeResp:
            def read(self):
                return json.dumps(
                    {"extract": "Jane Austen was an English novelist."}).encode()
        self.assertEqual(
            wikipedia_summary("Jane Austen", opener=lambda url: FakeResp()),
            "Jane Austen was an English novelist.")

    def test_wikipedia_failure_returns_none(self):
        def boom(url):
            raise IOError("no network")
        self.assertIsNone(wikipedia_summary("Anything", opener=boom))
        self.assertIsNone(wikipedia_summary("   "))


class CliTests(unittest.TestCase):
    def test_help_exits_zero(self):
        proc = subprocess.run([sys.executable, "ebook_reader.py", "--help"],
                              cwd=Path(__file__).resolve().parent.parent,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Terminal EPUB reader", proc.stdout)

    def test_list_empty_data_dir(self):
        with tempfile.TemporaryDirectory() as d:
            proc = subprocess.run(
                [sys.executable, "ebook_reader.py", "--data-dir", d, "list"],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()

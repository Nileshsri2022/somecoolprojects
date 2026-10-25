import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mdslides
from mdslides import (parse_deck, render_markdown, split_slides,
                      write_pdf, load_project, render_deck, main,
                      make_handler)
from http.server import ThreadingHTTPServer

DECK = "# Hello\n\n- one\n- two\n\n---\n\n## Second\n\nSome *italic* text.\n\n---\n\n# Third\n\n```python\nprint(1)\n```\n"


class TestSplitSlides(unittest.TestCase):
    def test_splits_in_order(self):
        self.assertEqual(split_slides("a\n---\nb\n---\nc"), ["a", "b", "c"])

    def test_no_separator_is_one_slide(self):
        self.assertEqual(split_slides("# Only"), ["# Only"])

    def test_leading_trailing_separators_dropped(self):
        self.assertEqual(split_slides("---\na\n---"), ["a"])

    def test_interior_empty_slide_dropped(self):
        self.assertEqual(split_slides("a\n---\n---\nb"), ["a", "b"])

    def test_whitespace_around_separator(self):
        self.assertEqual(split_slides("a\n  ---  \nb"), ["a", "b"])

    def test_longer_dashes_do_not_split(self):
        self.assertEqual(split_slides("a\n----\nb"), ["a\n----\nb"])
        self.assertEqual(split_slides("a\n--\nb"), ["a\n--\nb"])


class TestRenderMarkdown(unittest.TestCase):
    def test_headings(self):
        out = render_markdown("# Title\n## Sub\n###### Tiny")
        self.assertIn("<h1>Title</h1>", out)
        self.assertIn("<h2>Sub</h2>", out)
        self.assertIn("<h6>Tiny</h6>", out)

    def test_paragraph_and_escaping(self):
        out = render_markdown("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_unordered_and_ordered_lists_grouped(self):
        out = render_markdown("- a\n- b\n\n1. x\n2. y")
        self.assertIn("<ul><li>a</li><li>b</li></ul>", out)
        self.assertIn("<ol><li>x</li><li>y</li></ol>", out)

    def test_star_bullets(self):
        self.assertIn("<li>a</li>", render_markdown("* a"))

    def test_code_fence_with_language_and_escaping(self):
        out = render_markdown("```python\nx < y\n```")
        self.assertIn('class="language-python"', out)
        self.assertIn("x &lt; y", out)

    def test_blockquote(self):
        out = render_markdown("> quoted words")
        self.assertIn("<blockquote><p>quoted words</p></blockquote>", out)

    def test_inline_markup(self):
        out = render_markdown("**bold** and *ital* and `code` and "
                              "[text](https://example.com) and "
                              "![alt](pic.png)")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>ital</em>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn('<a href="https://example.com">text</a>', out)
        self.assertIn('<img alt="alt" src="pic.png">', out)

    def test_markup_inside_code_span_not_reinterpreted(self):
        out = render_markdown("`**not bold**`")
        self.assertIn("<code>**not bold**</code>", out)
        self.assertNotIn("<strong>", out)

    def test_slide_titles(self):
        slides = parse_deck(DECK)
        self.assertEqual([s.title for s in slides],
                         ["Hello", "Second", "Third"])

    def test_title_fallback(self):
        slides = parse_deck("just text\n---\nmore text")
        self.assertEqual(slides[0].title, "Slide 1")
        self.assertEqual(slides[1].title, "Slide 2")


class TestTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _project(self):
        (self.tmp / "slides").mkdir()
        (self.tmp / "slides" / "slides.md").write_text(DECK)
        (self.tmp / "template").mkdir()
        return self.tmp

    def test_default_deck_renders_all_slides(self):
        proj = self._project()
        _src, title, tdir, slides, _t = load_project(proj)
        out = render_deck(slides, title, tdir)
        self.assertEqual(out.count('<section class="slide">'), 3)
        self.assertIn("Hello", out)
        self.assertNotIn("/__version__", out)

    def test_user_template_overrides_shell_only(self):
        proj = self._project()
        (self.tmp / "template" / "template.html").write_text(
            "<html><head><style>{{style}}</style></head>"
            "<body>CUSTOM{{slides}}</body></html>")
        _src, title, tdir, slides, _t = load_project(proj)
        out = render_deck(slides, title, tdir)
        self.assertIn("CUSTOM", out)
        self.assertIn("background", out)  # default CSS still used

    def test_user_css_overrides_default(self):
        proj = self._project()
        (self.tmp / "template" / "style.css").write_text("body{color:pink}")
        _src, title, tdir, slides, _t = load_project(proj)
        out = render_deck(slides, title, tdir)
        self.assertIn("color:pink", out)
        self.assertNotIn("background: #111827", out)

    def test_per_piece_fallback_after_deleting_template(self):
        proj = self._project()
        (self.tmp / "template" / "template.html").write_text("CUSTOM{{slides}}")
        (self.tmp / "template" / "template.html").unlink()
        _src, title, tdir, slides, _t = load_project(proj)
        out = render_deck(slides, title, tdir)
        self.assertNotIn("CUSTOM", out)
        self.assertIn("<nav>", out)


class TestNewProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_layout(self):
        dest = self.tmp / "talk"
        self.assertEqual(main(["new", str(dest), "--title", "My Talk"]), 0)
        for rel in ("config.json", "slides/slides.md",
                    "template/template.html", "template/style.css",
                    "README.md"):
            self.assertTrue((dest / rel).is_file(), rel)
        self.assertTrue((dest / "images").is_dir())
        if shutil.which("git"):
            self.assertTrue((dest / ".git").is_dir())
        config = json.loads((dest / "config.json").read_text())
        self.assertEqual(config["title"], "My Talk")
        self.assertEqual(len(split_slides(
            (dest / "slides" / "slides.md").read_text())), 3)

    def test_refuses_nonempty_without_force(self):
        dest = self.tmp / "talk"
        dest.mkdir()
        (dest / "keep.txt").write_text("keep")
        self.assertEqual(main(["new", str(dest)]), 2)
        self.assertTrue((dest / "keep.txt").is_file())


class TestServe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.assertEqual(main(["new", str(self.tmp / "talk")]), 0)
        self.proj = self.tmp / "talk"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(str(self.proj), False))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.raw_server = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self.raw_server is not None:
            self.raw_server.shutdown()
            self.raw_server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, path, server=None):
        port = (server or self.server).server_address[1]
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (port, path)) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_root_returns_rendered_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<h1>Welcome</h1>", body)

    def test_unknown_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_version_endpoint(self):
        status, body = self._get("/__version__")
        self.assertEqual(status, 200)
        self.assertIn("version", json.loads(body))

    def test_live_reload_without_restart(self):
        _s, before = self._get("/")
        _s, v1 = self._get("/__version__")
        src = self.proj / "slides" / "slides.md"
        src.write_text(src.read_text() + "\n\n# Edited Slide Title\n")
        _s, after = self._get("/")
        _s, v2 = self._get("/__version__")
        self.assertIn("Edited Slide Title", after)
        self.assertNotEqual(json.loads(v1)["version"],
                            json.loads(v2)["version"])

    def test_raw_mode(self):
        self.raw_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(str(self.proj), True))
        threading.Thread(target=self.raw_server.serve_forever,
                         daemon=True).start()
        _s, body = self._get("/", server=self.raw_server)
        self.assertIn("<pre>", body)
        self.assertNotIn("<h1>Welcome</h1>", body)
        self.assertIn("# Welcome", body)


class TestExportPdf(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pdf_structure_and_page_count(self):
        slides = parse_deck(DECK)
        out = self.tmp / "deck.pdf"
        self.assertEqual(write_pdf(slides, out), 3)
        data = out.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Count 3", data)
        self.assertIn(b"Hello", data)
        self.assertIn(b"Second", data)

    def test_single_slide_pdf(self):
        out = self.tmp / "one.pdf"
        write_pdf(parse_deck("# Solo"), out)
        self.assertTrue(out.read_bytes().startswith(b"%PDF-"))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_build_export_end_to_end(self):
        proj = self.tmp / "talk"
        self.assertEqual(main(["new", str(proj)]), 0)
        html_out = self.tmp / "deck.html"
        self.assertEqual(main(["build", str(proj), "-o", str(html_out)]), 0)
        self.assertIn("Welcome", html_out.read_text())
        pdf_out = self.tmp / "deck.pdf"
        self.assertEqual(
            main(["export-pdf", str(proj), "-o", str(pdf_out)]), 0)
        self.assertTrue(pdf_out.read_bytes().startswith(b"%PDF-"))

    def test_missing_project_exits_nonzero(self):
        self.assertEqual(
            main(["build", str(self.tmp / "nope"), "-o",
                  str(self.tmp / "x.html")]), 2)

    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()

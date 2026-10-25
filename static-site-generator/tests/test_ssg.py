"""Tests for ssg.py — temp fixture sites, HTML output compared.

Run: python3 -m unittest discover -s tests -v
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ssg  # noqa: E402


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return ssg.main(list(args))

    def make_site(self, name="mysite"):
        self.assertEqual(self.cli("new", str(self.root / name)), 0)
        return self.root / name

    # -- site creation -------------------------------------------------

    def test_new_creates_content_index_only(self):
        site = self.make_site()
        self.assertTrue((site / "content" / "index.md").is_file())
        self.assertIn("# Welcome", (site / "content" / "index.md").read_text())
        self.assertFalse((site / "index.html").exists())

    def test_new_fails_if_exists(self):
        self.make_site()
        self.assertNotEqual(self.cli("new", str(self.root / "mysite")), 0)

    def test_new_theme_creates_template(self):
        site = self.make_site()
        self.assertEqual(
            self.cli("new", "theme", "cc", "--site", str(site)), 0)
        template = site / "themes" / "cc" / "index.html"
        self.assertTrue(template.is_file())
        self.assertIn("{{ Title }}", template.read_text())
        self.assertIn("{{ Content }}", template.read_text())
        self.assertNotEqual(
            self.cli("new", "theme", "cc", "--site", str(site)), 0)

    def test_new_page_and_nested_and_duplicates_and_unsafe(self):
        site = self.make_site()
        self.assertEqual(
            self.cli("new", "page", "about", "--site", str(site)), 0)
        self.assertTrue((site / "content" / "about.md").is_file())
        self.assertEqual(
            self.cli("new", "page", "blog/first-post",
                     "--site", str(site)), 0)
        self.assertTrue(
            (site / "content" / "blog" / "first-post.md").is_file())
        self.assertNotEqual(
            self.cli("new", "page", "about", "--site", str(site)), 0)
        self.assertNotEqual(
            self.cli("new", "page", "../evil", "--site", str(site)), 0)
        self.assertNotEqual(
            self.cli("new", "page", "/abs", "--site", str(site)), 0)

    def test_unknown_command_and_missing_args_fail(self):
        self.assertNotEqual(self.cli("frobnicate"), 0)
        self.assertNotEqual(self.cli("new"), 0)
        self.assertNotEqual(self.cli("build", "--bogus", "x"), 0)


class MarkdownCase(unittest.TestCase):
    def test_headings_and_paragraphs(self):
        out = ssg.markdown_to_html("# Hello\n\nSome text.\n\n## Sub\n")
        self.assertIn("<h1>Hello</h1>", out)
        self.assertIn("<p>Some text.</p>", out)
        self.assertIn("<h2>Sub</h2>", out)

    def test_inline_markup(self):
        out = ssg.markdown_to_html(
            "A **bold** and *italic* and `code` word.\n")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>italic</em>", out)
        self.assertIn("<code>code</code>", out)

    def test_links_and_images(self):
        out = ssg.markdown_to_html(
            "See [Docs](https://example.com) and ![Alt](pic.png).\n")
        self.assertIn('<a href="https://example.com">Docs</a>', out)
        self.assertIn('<img alt="Alt" src="pic.png">', out)

    def test_lists_code_block_quote_rule(self):
        out = ssg.markdown_to_html(
            "- one\n- two\n\n1. first\n2. second\n\n"
            "```\n<not html>\n```\n\n> quoted\n\n---\n")
        self.assertIn("<ul>", out)
        self.assertIn("<li>one</li>", out)
        self.assertIn("<ol>", out)
        self.assertIn("<li>first</li>", out)
        self.assertIn("<pre><code>&lt;not html&gt;</code></pre>", out)
        self.assertIn("<blockquote><p>quoted</p></blockquote>", out)
        self.assertIn("<hr>", out)

    def test_raw_html_is_escaped(self):
        out = ssg.markdown_to_html("A <b>bold</b> trick.\n")
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", out)
        self.assertNotIn("<b>bold</b>", out)

    def test_title_extraction(self):
        self.assertEqual(
            ssg.extract_title("# My Title\n\nBody\n", "Fallback"),
            "My Title")
        self.assertEqual(
            ssg.extract_title("## Not top\n\nBody\n", "Fallback"),
            "Fallback")
        self.assertEqual(ssg.title_from_name("about-us"), "About Us")

    def test_template_substitution(self):
        out = ssg.render_template("<title>{{Title}}</title>{{ Content }}",
                                  "T & C", "<p>hi</p>")
        self.assertIn("<title>T &amp; C</title>", out)
        self.assertIn("<p>hi</p>", out)
        self.assertIn("{{ Foo }}", ssg.render_template("{{ Foo }}", "T", "C"))


class BuildCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.site = self.root / "mysite"
        ssg.main(["new", str(self.site)])
        (self.site / "content" / "index.md").write_text(
            "# Home\n\nWelcome **home**.\n")
        (self.site / "content" / "about.md").write_text(
            "# About Us\n\nWe build things.\n")
        (self.site / "content" / "blog").mkdir()
        (self.site / "content" / "blog" / "post.md").write_text(
            "# First Post\n\nHello.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *extra):
        return ssg.main(["build", "--site", str(self.site), *extra])

    def test_end_to_end_with_theme(self):
        ssg.main(["new", "theme", "cc", "--site", str(self.site)])
        self.assertEqual(self.build(), 0)
        index = (self.site / "public" / "index.html").read_text()
        self.assertIn("<title>Home</title>", index)
        self.assertIn("<strong>home</strong>", index)
        about = (self.site / "public" / "about.html").read_text()
        self.assertIn("<title>About Us</title>", about)
        self.assertIn("We build things.", about)
        post = (self.site / "public" / "blog" / "post.html").read_text()
        self.assertIn("<title>First Post</title>", post)

    def test_no_theme_uses_builtin_template(self):
        self.assertEqual(self.build(), 0)
        self.assertIn("<title>Home</title>",
                      (self.site / "public" / "index.html").read_text())

    def test_theme_selection_rules(self):
        ssg.main(["new", "theme", "one", "--site", str(self.site)])
        ssg.main(["new", "theme", "two", "--site", str(self.site)])
        # Ambiguous without --theme.
        self.assertNotEqual(self.build(), 0)
        self.assertEqual(self.build("--theme", "two"), 0)
        self.assertNotEqual(self.build("--theme", "nope"), 0)

    def test_title_fallback_to_filename(self):
        (self.site / "content" / "plain.md").write_text("No heading.\n")
        self.assertEqual(self.build(), 0)
        self.assertIn("<title>Plain</title>",
                      (self.site / "public" / "plain.html").read_text())

    def test_rebuild_wipes_stale_output(self):
        self.assertEqual(self.build(), 0)
        self.assertTrue((self.site / "public" / "about.html").exists())
        (self.site / "content" / "about.md").unlink()
        self.assertEqual(self.build(), 0)
        self.assertFalse((self.site / "public" / "about.html").exists())

    def test_static_copied_and_missing_content_fails(self):
        (self.site / "static").mkdir()
        (self.site / "static" / "style.css").write_text("body {}\n")
        self.assertEqual(self.build(), 0)
        self.assertEqual(
            (self.site / "public" / "style.css").read_text(), "body {}\n")
        empty = self.root / "empty"
        empty.mkdir()
        self.assertNotEqual(ssg.main(["build", "--site", str(empty)]), 0)


class ServeCase(unittest.TestCase):
    def test_serve_and_rebuild_on_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "mysite"
            ssg.main(["new", str(site)])
            (site / "content" / "index.md").write_text(
                "# Home\n\nVersion one.\n")
            port = free_port()
            proc = subprocess.Popen(
                [sys.executable, str(Path(ssg.__file__).resolve()),
                 "serve", "--site", str(site), "--port", str(port)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True)
            try:
                base = "http://127.0.0.1:%d/" % port
                body = None
                for _ in range(100):
                    try:
                        body = urllib.request.urlopen(base, timeout=2).read()
                        break
                    except Exception:
                        time.sleep(0.1)
                self.assertIsNotNone(body, "server did not start")
                self.assertIn(b"Version one", body)
                (site / "content" / "index.md").write_text(
                    "# Home\n\nVersion two.\n")
                updated = None
                for _ in range(100):
                    try:
                        updated = urllib.request.urlopen(
                            base, timeout=2).read()
                    except Exception:
                        pass
                    if updated and b"Version two" in updated:
                        break
                    time.sleep(0.1)
                self.assertIn(b"Version two", updated)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

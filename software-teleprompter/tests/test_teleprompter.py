#!/usr/bin/env python3
"""Headless unittest suite for the software teleprompter core."""

import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from teleprompter import (Player, Script, TeleprompterSettings, render_lines)


def settings(**overrides):
    base = dict(font_face="monospace", font_size=24, left_margin=0,
                right_margin=0, line_spacing=0, mirror="none", wpm=150)
    base.update(overrides)
    return TeleprompterSettings(**base)


class TestScriptLoading(unittest.TestCase):
    def test_load_text(self):
        script = Script.load_text("hello world")
        self.assertEqual(script.text, "hello world")
        self.assertEqual(script.markdown_lines(), ["hello world"])

    def test_empty_script(self):
        script = Script.load_text("")
        self.assertEqual(script.markdown_lines(), [])
        self.assertEqual(render_lines(script, settings(), 80), [])

    def test_newlines_and_paragraph_breaks_preserved(self):
        script = Script.load_text("first para\n\nsecond para")
        lines = render_lines(script, settings(), 80)
        self.assertIn("first para", lines)
        self.assertIn("second para", lines)
        self.assertIn("", lines)  # paragraph break survives

    def test_load_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("from file\n")
            path = fh.name
        try:
            self.assertEqual(Script.load_file(path).text, "from file\n")
        finally:
            os.unlink(path)

    def test_load_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            Script.load_file("/nonexistent/teleprompter-script.txt")


class TestMarkdown(unittest.TestCase):
    def test_markdown_heading(self):
        script = Script.load_text("# Welcome Here")
        self.assertEqual(script.markdown_lines(), ["WELCOME HERE"])

    def test_markdown_emphasis_stripped(self):
        script = Script.load_text("a **bold** and *italic* and `code` word")
        self.assertEqual(script.markdown_lines(),
                         ["a bold and italic and code word"])

    def test_markdown_link_kept_as_text(self):
        script = Script.load_text("see [the guide](https://example.com) now")
        self.assertEqual(script.markdown_lines(), ["see the guide now"])


class TestFormatting(unittest.TestCase):
    def test_left_margin_prefix(self):
        lines = render_lines(Script.load_text("hi"), settings(left_margin=4), 80)
        self.assertEqual(lines, ["    hi"])

    def test_right_margin_narrows_lines(self):
        text = "one two three four five six seven eight nine ten"
        narrow = render_lines(Script.load_text(text), settings(right_margin=60), 80)
        wide = render_lines(Script.load_text(text), settings(right_margin=0), 80)
        self.assertGreater(len(narrow), len(wide))

    def test_negative_margin_rejected(self):
        with self.assertRaises(ValueError):
            settings(left_margin=-1)

    def test_line_spacing_inserts_blanks(self):
        lines = render_lines(Script.load_text("a\nb"), settings(line_spacing=1), 80)
        self.assertEqual(lines, ["a", "", "b"])

    def test_line_spacing_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            settings(line_spacing=4)

    def test_font_face_stored(self):
        self.assertEqual(settings(font_face="DejaVu Sans").font_face, "DejaVu Sans")
        with self.assertRaises(ValueError):
            settings(font_face="   ")

    def test_font_size_scales_wrap_width(self):
        text = "one two three four five six seven eight nine ten eleven twelve"
        small = render_lines(Script.load_text(text), settings(font_size=12), 80)
        large = render_lines(Script.load_text(text), settings(font_size=48), 80)
        self.assertGreater(len(large), len(small))

    def test_font_size_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            settings(font_size=7)
        with self.assertRaises(ValueError):
            settings(font_size=73)

    def test_render_respects_width_and_margins(self):
        lines = render_lines(Script.load_text("hello world foo bar"),
                             settings(left_margin=2, right_margin=2), 20)
        for line in lines:
            self.assertLessEqual(len(line), 20)
            self.assertTrue(line.startswith("  "))


class TestPlayback(unittest.TestCase):
    def _player(self, wpm=120):
        # 6 words per line -> 20 lines/sec at 120 WPM
        lines = ["a b c d e f"] * 10
        return Player(lines, wpm=wpm)

    def test_wpm_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            Player(["x"], wpm=5)
        with self.assertRaises(ValueError):
            settings(wpm=601)

    def test_lines_per_second_from_wpm(self):
        player = self._player(wpm=120)
        self.assertAlmostEqual(player.lines_per_second, 20.0)

    def test_set_wpm_changes_rate(self):
        player = self._player(wpm=120)
        player.set_wpm(60)
        self.assertAlmostEqual(player.lines_per_second, 10.0)
        with self.assertRaises(ValueError):
            player.set_wpm(0)

    def test_step_advances_while_playing(self):
        player = self._player()
        player.start()
        player.step(0.5)  # 20 lines/s * 0.5 = 10 lines -> clamped at last line (9)
        self.assertEqual(player.offset, 9.0)

    def test_step_does_not_advance_when_paused(self):
        player = self._player()
        player.step(1.0)
        self.assertEqual(player.offset, 0.0)

    def test_toggle_pause_resume(self):
        player = self._player()
        self.assertFalse(player.playing)
        player.toggle()
        self.assertTrue(player.playing)
        player.toggle()
        self.assertFalse(player.playing)

    def test_pause_keeps_offset(self):
        player = self._player()
        player.start()
        player.step(0.1)
        offset = player.offset
        player.stop()
        player.step(5.0)
        self.assertEqual(player.offset, offset)

    def test_clamps_at_end(self):
        player = self._player()
        player.start()
        player.step(100.0)
        self.assertTrue(player.at_end())
        self.assertFalse(player.playing)  # stops at the end
        self.assertEqual(player.offset, 9.0)

    def test_reset_returns_to_top(self):
        player = self._player()
        player.start()
        player.step(0.2)
        player.reset()
        self.assertEqual(player.offset, 0.0)
        self.assertFalse(player.playing)

    def test_seek_clamps(self):
        player = self._player()
        player.seek(100)
        self.assertEqual(player.offset, 9.0)
        player.seek(-5)
        self.assertEqual(player.offset, 0.0)

    def test_progress_fraction(self):
        player = self._player()
        self.assertEqual(player.progress(), 0.0)
        player.seek(9)
        self.assertEqual(player.progress(), 1.0)

    def test_visible_lines_window(self):
        player = Player([f"line {i}" for i in range(10)], wpm=150)
        player.seek(3)
        self.assertEqual(player.visible_lines(3), ["line 3", "line 4", "line 5"])


class TestMirroring(unittest.TestCase):
    def test_mirror_horizontal(self):
        lines = render_lines(Script.load_text("abc"), settings(mirror="horizontal"), 80)
        self.assertEqual(lines, ["cba"])

    def test_mirror_vertical(self):
        lines = render_lines(Script.load_text("one\ntwo\nthree"),
                             settings(mirror="vertical"), 80)
        self.assertEqual(lines, ["three", "two", "one"])

    def test_mirror_both(self):
        lines = render_lines(Script.load_text("ab\ncd"),
                             settings(mirror="both"), 80)
        self.assertEqual(lines, ["dc", "ba"])

    def test_mirror_invalid_rejected(self):
        with self.assertRaises(ValueError):
            settings(mirror="diagonal")

    def test_scrolling_works_when_mirrored(self):
        lines = render_lines(Script.load_text("one\ntwo\nthree"),
                             settings(mirror="vertical"), 80)
        player = Player(lines, wpm=150)
        self.assertEqual(player.visible_lines(2), ["three", "two"])
        player.start()
        player.step(100.0)
        self.assertTrue(player.at_end())
        self.assertEqual(player.visible_lines(1), ["one"])


class TestUrlImport(unittest.TestCase):
    BODY = "# Hello\n\nImported **script** here.\n"

    def setUp(self):
        body = self.BODY.encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_load_url_local_server(self):
        script = Script.load_url(f"http://127.0.0.1:{self.port}/script.md")
        self.assertEqual(script.markdown_lines(), ["HELLO", "", "Imported script here."])

    def test_load_url_failure_raises_import_error(self):
        with self.assertRaises(ImportError):
            Script.load_url("http://127.0.0.1:1/nope.md")


if __name__ == "__main__":
    unittest.main()

"""Headless tests for the pure Buffer core and parse_command in ccvim.py.

The curses UI is deliberately NOT tested here (it needs a real terminal);
see docs/TEST_PLAN.md.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ccvim import Buffer, display_col, expand_tabs, parse_command


def buf_with(text):
    return Buffer(lines=text.split("\n"))


class TestConstruction(unittest.TestCase):
    def test_empty_buffer(self):
        b = Buffer()
        self.assertEqual(b.lines, [""])
        self.assertEqual((b.row, b.col), (0, 0))
        self.assertFalse(b.dirty)

    def test_none_lines_becomes_empty(self):
        self.assertEqual(Buffer(lines=[]).lines, [""])


class TestMovement(unittest.TestCase):
    def setUp(self):
        self.b = buf_with("hello\nxy\nlonger line")

    def test_hjkl_basic(self):
        self.b.move_right(); self.b.move_right()
        self.assertEqual(self.b.col, 2)
        self.b.move_down()
        self.assertEqual((self.b.row, self.b.col), (1, 2))
        self.b.move_left()
        self.assertEqual(self.b.col, 1)
        self.b.move_up()
        self.assertEqual((self.b.row, self.b.col), (0, 1))

    def test_bounds_clamped(self):
        self.b.move_left(); self.b.move_up()
        self.assertEqual((self.b.row, self.b.col), (0, 0))
        for _ in range(20):
            self.b.move_right()
        self.assertEqual(self.b.col, 5)  # len("hello")
        for _ in range(20):
            self.b.move_down()
        self.assertEqual(self.b.row, 2)

    def test_column_clamps_to_shorter_line(self):
        for _ in range(5):
            self.b.move_right()
        self.b.move_down()
        self.assertEqual(self.b.col, 2)  # len("xy")

    def test_goto_line_clamps(self):
        self.b.goto_line(99)
        self.assertEqual(self.b.row, 2)
        self.b.goto_line(0)
        self.assertEqual(self.b.row, 0)
        self.b.goto_line(2)
        self.assertEqual(self.b.row, 1)

    def test_first_last_line(self):
        self.b.goto_last_line()
        self.assertEqual(self.b.row, 2)
        self.b.goto_first_line()
        self.assertEqual(self.b.row, 0)


class TestEditing(unittest.TestCase):
    def test_insert_middle(self):
        b = buf_with("ac")
        b.col = 1
        b.insert_char("b")
        self.assertEqual(b.lines, ["abc"])
        self.assertEqual(b.col, 2)
        self.assertTrue(b.dirty)

    def test_insert_newline_splits(self):
        b = buf_with("hello")
        b.col = 2
        b.insert_newline()
        self.assertEqual(b.lines, ["he", "llo"])
        self.assertEqual((b.row, b.col), (1, 0))

    def test_backspace_midline(self):
        b = buf_with("abc")
        b.col = 2
        b.backspace()
        self.assertEqual(b.lines, ["ac"])
        self.assertEqual(b.col, 1)

    def test_backspace_at_col0_joins(self):
        b = buf_with("foo\nbar")
        b.row, b.col = 1, 0
        b.backspace()
        self.assertEqual(b.lines, ["foobar"])
        self.assertEqual((b.row, b.col), (0, 3))

    def test_backspace_at_origin_noop(self):
        b = buf_with("abc")
        b.backspace()
        self.assertEqual(b.lines, ["abc"])
        self.assertFalse(b.dirty)

    def test_delete_char_midline(self):
        b = buf_with("abc")
        b.col = 1
        b.delete_char()
        self.assertEqual(b.lines, ["ac"])

    def test_delete_char_at_eol_noop(self):
        b = buf_with("abc")
        b.col = 3
        b.delete_char()
        self.assertEqual(b.lines, ["abc"])
        self.assertFalse(b.dirty)

    def test_delete_line_middle(self):
        b = buf_with("a\nb\nc")
        b.row = 1
        b.delete_line()
        self.assertEqual(b.lines, ["a", "c"])
        self.assertEqual(b.row, 1)

    def test_delete_line_last(self):
        b = buf_with("a\nb")
        b.row = 1
        b.delete_line()
        self.assertEqual(b.lines, ["a"])
        self.assertEqual(b.row, 0)

    def test_delete_sole_line(self):
        b = buf_with("only")
        b.delete_line()
        self.assertEqual(b.lines, [""])

    def test_open_line_below(self):
        b = buf_with("a\nb")
        b.open_line_below()
        self.assertEqual(b.lines, ["a", "", "b"])
        self.assertEqual((b.row, b.col), (1, 0))

    def test_tab_insert_and_expand(self):
        b = buf_with("a")
        b.col = 1
        b.insert_char("\t")
        self.assertEqual(b.lines, ["a\t"])
        self.assertEqual(expand_tabs("a\t"), "a   ")
        self.assertEqual(expand_tabs("\t"), "    ")
        self.assertEqual(expand_tabs("ab\tc"), "ab  c")

    def test_movement_does_not_dirty(self):
        b = buf_with("a\nb")
        b.move_down()
        self.assertFalse(b.dirty)


class TestUndo(unittest.TestCase):
    def test_undo_insert(self):
        b = buf_with("ac")
        b.col = 1
        b.insert_char("b")
        self.assertTrue(b.undo())
        self.assertEqual(b.lines, ["ac"])
        self.assertEqual(b.col, 1)

    def test_undo_newline(self):
        b = buf_with("hello")
        b.col = 2
        b.insert_newline()
        b.undo()
        self.assertEqual(b.lines, ["hello"])
        self.assertEqual((b.row, b.col), (0, 2))

    def test_undo_delete_line(self):
        b = buf_with("a\nb\nc")
        b.row = 1
        b.delete_line()
        b.undo()
        self.assertEqual(b.lines, ["a", "b", "c"])

    def test_undo_empty_history_noop(self):
        b = buf_with("x")
        self.assertFalse(b.undo())
        self.assertEqual(b.lines, ["x"])


class TestLoadSave(unittest.TestCase):
    def test_round_trip(self):
        b = buf_with("one\ntwo\nthree")
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as f:
            path = f.name
        try:
            b.save(path)
            c = Buffer()
            c.load(path)
            self.assertEqual(c.lines, ["one", "two", "three"])
            self.assertFalse(c.dirty)
            self.assertEqual(c.filename, path)
        finally:
            os.unlink(path)

    def test_empty_file_loads_as_one_empty_line(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as f:
            path = f.name
        try:
            c = Buffer()
            c.load(path)
            self.assertEqual(c.lines, [""])
        finally:
            os.unlink(path)

    def test_save_adds_trailing_newline(self):
        b = buf_with("a\nb")
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as f:
            path = f.name
        try:
            b.save(path)
            with open(path) as f:
                self.assertEqual(f.read(), "a\nb\n")
        finally:
            os.unlink(path)

    def test_save_clears_dirty_and_later_edit_sets_it(self):
        b = buf_with("x")
        b.insert_char("y")  # buf_with builds directly, so dirty it first
        self.assertTrue(b.dirty)
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as f:
            path = f.name
        try:
            b.save(path)
            self.assertFalse(b.dirty)
            b.insert_char("z")
            self.assertTrue(b.dirty)
        finally:
            os.unlink(path)

    def test_save_without_filename_raises(self):
        with self.assertRaises(ValueError):
            Buffer().save()

    def test_missing_file_keeps_filename(self):
        b = Buffer()
        b.filename = "/tmp/does-not-exist-ccvim-test.txt"
        self.assertEqual(b.lines, [""])


class TestSearchReplace(unittest.TestCase):
    def setUp(self):
        self.b = buf_with("foo bar\nbaz foo\nnothing")

    def test_find_next_forward(self):
        self.assertTrue(self.b.find_next("foo"))
        self.assertEqual((self.b.row, self.b.col), (1, 4))

    def test_find_next_wraps(self):
        self.b.row, self.b.col = 2, 0
        self.assertTrue(self.b.find_next("foo"))
        self.assertEqual((self.b.row, self.b.col), (0, 0))

    def test_find_next_no_match_leaves_cursor(self):
        self.assertFalse(self.b.find_next("zzz"))
        self.assertEqual((self.b.row, self.b.col), (0, 0))

    def test_find_next_empty_pattern_noop(self):
        self.assertFalse(self.b.find_next(""))
        self.assertEqual((self.b.row, self.b.col), (0, 0))

    def test_find_prev(self):
        self.b.row, self.b.col = 1, 7
        self.assertTrue(self.b.find_prev("foo"))
        self.assertEqual((self.b.row, self.b.col), (1, 4))
        self.assertTrue(self.b.find_prev("foo"))
        self.assertEqual((self.b.row, self.b.col), (0, 0))
        self.assertFalse(self.b.find_prev("foo"))

    def test_replace_current(self):
        self.assertTrue(self.b.replace_current("foo", "qux"))
        self.assertEqual(self.b.lines[0], "qux bar")

    def test_replace_current_no_match(self):
        self.b.row = 2
        self.assertFalse(self.b.replace_current("foo", "qux"))
        self.assertEqual(self.b.lines[2], "nothing")

    def test_replace_all_count(self):
        count = self.b.replace_all("foo", "qux")
        self.assertEqual(count, 2)
        self.assertEqual(self.b.lines, ["qux bar", "baz qux", "nothing"])

    def test_replace_all_no_match(self):
        self.assertEqual(self.b.replace_all("zzz", "qux"), 0)
        self.assertFalse(self.b.dirty)

    def test_replace_empty_pattern_noop(self):
        self.assertEqual(self.b.replace_all("", "x"), 0)
        self.assertFalse(self.b.replace_current("", "x"))


class TestViewportRender(unittest.TestCase):
    def test_render_tilde_past_eof(self):
        b = buf_with("a")
        rows = b.render_screen(3, 10)
        self.assertEqual(rows, ["a", "~", "~"])

    def test_render_exact_row_count(self):
        b = buf_with("a\nb\nc\nd")
        self.assertEqual(len(b.render_screen(2, 10)), 2)

    def test_render_truncates_width(self):
        b = buf_with("abcdefgh")
        self.assertEqual(b.render_screen(1, 4), ["abcd"])

    def test_render_expands_tabs(self):
        b = buf_with("a\tb")
        self.assertEqual(b.render_screen(1, 20), ["a   b"])

    def test_ensure_visible_scrolls_down_and_back(self):
        b = Buffer(lines=[f"line {i}" for i in range(20)])
        b.goto_line(15)  # 0-based row 14; window height 5
        b.ensure_visible(5, 20)
        self.assertEqual(b.row_offset, 10)
        b.goto_line(2)  # 0-based row 1
        b.ensure_visible(5, 20)
        self.assertEqual(b.row_offset, 1)

    def test_ensure_visible_column_scroll(self):
        b = buf_with("x" * 50)
        b.col = 40
        b.ensure_visible(5, 10)
        self.assertEqual(b.col_offset, 31)

    def test_display_col_with_tab(self):
        self.assertEqual(display_col("a\tb", 2), 4)
        self.assertEqual(display_col("ab", 1), 1)


class TestStatus(unittest.TestCase):
    def test_status_contains_position_and_mode(self):
        b = buf_with("a\nb")
        b.filename = "notes.txt"
        s = b.status("NORMAL")
        self.assertIn("notes.txt", s)
        self.assertIn("line 1/2", s)
        self.assertIn("NORMAL", s)

    def test_status_dirty_flag(self):
        b = buf_with("a")
        self.assertNotIn("[+]", b.status("NORMAL"))
        b.insert_char("x")
        self.assertIn("[+]", b.status("INSERT"))


class TestParseCommand(unittest.TestCase):
    def test_quit_variants(self):
        self.assertEqual(parse_command("q"), ("quit", None))
        self.assertEqual(parse_command("q!"), ("force_quit", None))

    def test_write_variants(self):
        self.assertEqual(parse_command("w", "a.txt"), ("write", "a.txt"))
        self.assertEqual(parse_command("w b.txt"), ("write", "b.txt"))
        self.assertEqual(parse_command("wq", "a.txt"),
                         ("write_quit", "a.txt"))
        self.assertEqual(parse_command("wq b.txt"),
                         ("write_quit", "b.txt"))

    def test_goto(self):
        self.assertEqual(parse_command("42"), ("goto", 42))

    def test_substitute(self):
        self.assertEqual(parse_command("s/foo/bar/"),
                         ("substitute", ("foo", "bar")))
        self.assertEqual(parse_command("s/foo/bar/g"),
                         ("substitute_all", ("foo", "bar")))

    def test_unknown_and_malformed(self):
        self.assertEqual(parse_command("xyz")[0], "unknown")
        self.assertEqual(parse_command("s/foo/bar")[0], "unknown")
        self.assertEqual(parse_command("")[0], "unknown")


if __name__ == "__main__":
    unittest.main()

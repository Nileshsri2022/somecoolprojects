"""Tests for ccut.py. Run from cut/:
python3 -m unittest discover -s tests -v

Function tests (parse + cut_line) and CLI tests where our
output is compared byte-for-byte with system cut on the
same fixtures. System cut is the oracle; if it is absent,
those tests are skipped.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ccut import CutError, cut_line, parse_field_list  # noqa: E402

TOOL = os.path.join(os.path.dirname(__file__), "..", "ccut.py")
SYSTEM_CUT = shutil.which("cut")

TSV = b"f0\tf1\n0\t1\n5\t6\n10\t11\n15\t16\n20\t21\n"
CSV = (b"Song title,Artist\n"
       b'"10000 Reasons (Bless the Lord)",Matt Redman\n'
       b'"20 Good Reasons",Thirsty Merc\n'
       b'"Adore You",Harry Styles\n')
EDGE = b"a\tb\tc\td\nx\np\tq\n\na,,c\n"


def run_tool(args, stdin=None):
    proc = subprocess.run(
        [sys.executable, TOOL, *args],
        input=stdin, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def run_system(args, stdin=None):
    proc = subprocess.run(
        [SYSTEM_CUT, *args], input=stdin, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


class TestParse(unittest.TestCase):
    def test_lists(self):
        self.assertEqual(parse_field_list("2"), ({2}, None))
        self.assertEqual(parse_field_list("1,2"), ({1, 2}, None))
        self.assertEqual(parse_field_list("1 2"), ({1, 2}, None))
        self.assertEqual(parse_field_list("2-4"), ({2, 3, 4}, None))
        self.assertEqual(parse_field_list("-2"), ({1, 2}, None))
        self.assertEqual(parse_field_list("3-"), (set(), 3))
        self.assertEqual(parse_field_list("1,3-4"), ({1, 3, 4}, None))

    def test_errors(self):
        for bad in ("0", "2-1", "a", "1,,2", "1-2-3", "-",
                    "1, 2", "1  2", ",1", "1,", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(CutError):
                    parse_field_list(bad)


class TestCutLine(unittest.TestCase):
    def test_no_delimiter_line_unchanged(self):
        selected, open_from = parse_field_list("2")
        self.assertEqual(cut_line(b"x", b"\t", selected, open_from), b"x")
        self.assertEqual(cut_line(b"abc", b",", selected, open_from), b"abc")

    def test_out_of_order_and_duplicates(self):
        selected, open_from = parse_field_list("3,1")
        self.assertEqual(
            cut_line(b"a\tb\tc\td", b"\t", selected, open_from), b"a\tc")
        selected, open_from = parse_field_list("2,2")
        self.assertEqual(
            cut_line(b"a\tb\tc", b"\t", selected, open_from), b"b")

    def test_out_of_range_gives_empty(self):
        selected, open_from = parse_field_list("5")
        self.assertEqual(
            cut_line(b"p\tq", b"\t", selected, open_from), b"")


@unittest.skipUnless(SYSTEM_CUT, "system cut not available")
class TestCliVsSystem(unittest.TestCase):
    def assert_same(self, args, data, stdin_mode=False):
        """Run both tools on the same input, assert same output."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.txt")
            with open(path, "wb") as f:
                f.write(data)
            if stdin_mode:
                ours = run_tool(args, stdin=data)
                theirs = run_system(args, stdin=data)
            else:
                ours = run_tool([*args, path])
                theirs = run_system([*args, path])
            self.assertEqual(ours[0], 0)
            self.assertEqual(theirs[0], 0)
            self.assertEqual(ours[1], theirs[1])

    def test_challenge_steps(self):
        self.assert_same(["-f2"], TSV)
        self.assert_same(["-f1", "-d,"], CSV)
        self.assert_same(["-f1,2"], TSV)
        self.assert_same(["-d,", "-f1 2"], CSV)

    def test_ranges_and_order(self):
        for args in (["-f2-3"], ["-f3-"], ["-f-2"],
                     ["-f3,1"], ["-f2,2"], ["-f5"],
                     ["-f1,3-4"], ["-f2-"]):
            with self.subTest(args=args):
                self.assert_same(args, EDGE)

    def test_comma_edges(self):
        self.assert_same(["-d,", "-f1,3"], b"a,,c\n")
        self.assert_same(["-d,", "-f2"], b"abc\nx,y\n")

    def test_stdin_and_dash(self):
        self.assert_same(["-f2"], TSV, stdin_mode=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.txt")
            with open(path, "wb") as f:
                f.write(TSV)
            ours = run_tool(["-f2", "-"], stdin=TSV)
            self.assertEqual(ours[0], 0)
            self.assertEqual(ours[1], b"f1\n1\n6\n11\n16\n21\n")

    def test_multi_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "a.tsv")
            p2 = os.path.join(tmp, "b.tsv")
            with open(p1, "wb") as f:
                f.write(b"a\tb\n")
            with open(p2, "wb") as f:
                f.write(b"c\td\n")
            ours = run_tool(["-f1", p1, p2])
            theirs = run_system(["-f1", p1, p2])
            self.assertEqual(ours[1], theirs[1])

    def test_no_trailing_newline(self):
        self.assert_same(["-f1"], b"a\tb")
        self.assert_same(["-f2"], b"a\tb")


class TestCliErrors(unittest.TestCase):
    def test_errors_exit_nonzero(self):
        for args in ([], ["-d,", "-f0", "x"], ["-d,", "-f2-1", "x"],
                     ["-d", "ab", "-f1", "x"], ["-f", "a", "x"]):
            with self.subTest(args=args):
                code, _, err = run_tool(args)
                self.assertNotEqual(code, 0)
                self.assertTrue(err)

    def test_missing_file_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.tsv")
            with open(good, "wb") as f:
                f.write(b"a\tb\n")
            code, out, err = run_tool(
                ["-f1", "/nonexistent-xyz", good])
            self.assertEqual(code, 1)
            self.assertEqual(out, b"a\n")
            self.assertIn(b"nonexistent-xyz", err)


if __name__ == "__main__":
    unittest.main()

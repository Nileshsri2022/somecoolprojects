"""Tests for grep.py (Coding Challenges #9).

Page examples are asserted exactly; everything else is compared
byte-for-byte (stdout) and exit-code-for-exit-code against system
`grep -E` on the same fixtures (Python `re` is ERE-like).
Recursive comparisons sort output lines first: GNU walks in readdir
order, grep.py in sorted name order.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
GREP = os.path.join(PROJECT, "grep.py")
FIX = os.path.join(HERE, "fixtures")
ROCK = os.path.join(FIX, "rockbands.txt")
BFS = os.path.join(FIX, "test-subdir", "BFS1985.txt")
SYMBOLS = os.path.join(FIX, "symbols.txt")
TESTTXT = os.path.join(FIX, "test.txt")
NONL = os.path.join(FIX, "no-newline.txt")


def run_mine(args, stdin=None, cwd=PROJECT):
    return subprocess.run(
        [sys.executable, GREP] + args,
        input=stdin, capture_output=True, cwd=cwd)


def run_gnu(args, stdin=None, cwd=PROJECT):
    # -E: Python re is ERE-like; GNU default is BRE.
    return subprocess.run(
        ["grep", "-E"] + args,
        input=stdin, capture_output=True, cwd=cwd)


def sorted_lines(data):
    return sorted(data.split(b"\n"))


class TestPageExamples(unittest.TestCase):
    def test_step1_empty_pattern_prints_whole_file(self):
        proc = run_mine(["", TESTTXT])
        self.assertEqual(proc.returncode, 0)
        with open(TESTTXT, "rb") as fh:
            self.assertEqual(proc.stdout, fh.read())

    def test_step2_single_letter_and_exit_code(self):
        proc = run_mine(["J", ROCK])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"Judas Priest\nBon Jovi\nJunkyard\n")

    def test_step3_recursive(self):
        proc = run_mine(["-r", "Nirvana", "tests/fixtures"])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, (
            b"tests/fixtures/rockbands.txt:Nirvana\n"
            b"tests/fixtures/test-subdir/BFS1985.txt:"
            b"Since Bruce Springsteen, Madonna, way before Nirvana\n"
            b"tests/fixtures/test-subdir/BFS1985.txt:"
            b"On the radio was Springsteen, Madonna, way before Nirvana\n"
            b"tests/fixtures/test-subdir/BFS1985.txt:"
            b"And bring back Springsteen, Madonna, way before Nirvana\n"
            b"tests/fixtures/test-subdir/BFS1985.txt:"
            b"Bruce Springsteen, Madonna, way before Nirvana\n"))

    def test_step4_invert_piped(self):
        first = run_mine(["-r", "Nirvana", "tests/fixtures"])
        second = run_mine(["-v", "Madonna"], stdin=first.stdout)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(
            second.stdout, b"tests/fixtures/rockbands.txt:Nirvana\n")

    def test_step5_digit_and_word_classes(self):
        proc = run_mine([r"\d", BFS])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, (
            b"Her dreams went out the door when she turned 24\n"
            b"There was U2 and Blondie, and music still on MTV\n"
            b"'Cause she's still preoccupied with 19, 19, 1985, 1985\n"
            b"There was U2 and Blondie, and music still on MTV\n"
            b"'Cause she's still preoccupied with 19, 19, 1985\n"
            b"There was U2 and Blondie, and music still on MTV\n"
            b"'Cause she's still preoccupied with 1985\n"
            b"There was U2 and Blondie, and music still on MTV\n"
            b"'Cause she's still preoccupied with 19, 19, 1985\n"))
        proc = run_mine([r"\w", SYMBOLS])
        self.assertEqual(proc.stdout, b"pound\ndollar\n")

    def test_step6_anchors(self):
        proc = run_mine(["^A", ROCK])
        self.assertEqual(proc.stdout,
                         b"AC/DC\nAerosmith\nAccept\nApril Wine\nAutograph\n")
        proc = run_mine(["na$", ROCK])
        self.assertEqual(proc.stdout, b"Nirvana\n")

    def test_final_step_case_insensitive_widens(self):
        sensitive = run_mine(["A", ROCK])
        insensitive = run_mine(["-i", "A", ROCK])
        self.assertEqual(insensitive.returncode, 0)
        self.assertTrue(len(insensitive.stdout) > len(sensitive.stdout))
        self.assertIn(b"Nirvana\n", insensitive.stdout)
        self.assertNotIn(b"Nirvana\n", sensitive.stdout)


class TestAgainstSystemGrep(unittest.TestCase):
    def assert_matches_gnu(self, args, stdin=None, sort=False):
        mine = run_mine(args, stdin=stdin)
        gnu = run_gnu(args, stdin=stdin)
        if sort:
            self.assertEqual(sorted_lines(mine.stdout), sorted_lines(gnu.stdout))
        else:
            self.assertEqual(mine.stdout, gnu.stdout)
        self.assertEqual(mine.returncode, gnu.returncode)

    def test_matrix_single_and_multi_file(self):
        cases = [
            ["", TESTTXT],
            ["J", ROCK],
            ["^A", ROCK],
            ["na$", ROCK],
            # NOTE: \d is NOT compared against GNU grep: GNU -E treats
            # \d as literal 'd' (verified: same 14 lines as pattern
            # 'd'), while the challenge page defines \d as a digit.
            # \d is covered exactly by test_step5_digit_and_word_classes.
            [r"\w", SYMBOLS],
            ["-i", "A", ROCK],
            ["-v", "Madonna", BFS],
            ["-i", "-v", "nirvana", ROCK],
            ["line", TESTTXT, ROCK],
            ["foo", NONL],
            ["bar", NONL],
            ["Nirvana", ROCK, BFS],
            ["-r", "Nirvana", FIX],
            ["-ri", "nirvana", FIX],
            ["-r", "foo", NONL],
            ["-v", "line", TESTTXT],
            ["--", "-v", ROCK],
        ]
        for args in cases:
            with self.subTest(args=args):
                recursive = any(
                    a.startswith("-") and a != "-" and "r" in a[1:]
                    for a in args)
                self.assert_matches_gnu(args, sort=recursive)

    def test_stdin_no_operands(self):
        self.assert_matches_gnu(["Nirvana"], stdin=b"foo\nNirvana\nbar\n")
        self.assert_matches_gnu(["-v", "x"], stdin=b"a\nxb\nc\n")

    def test_stdin_dash_operand_with_prefix(self):
        self.assert_matches_gnu(["foo", NONL, "-"], stdin=b"foo\n")

    def test_no_trailing_newline_gets_newline(self):
        mine = run_mine(["bar", NONL])
        gnu = run_gnu(["bar", NONL])
        self.assertEqual(mine.stdout, gnu.stdout)
        self.assertEqual(mine.stdout, b"bar\n")

    def test_recursive_no_operands_searches_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.txt"), "w") as fh:
                fh.write("foo\nbar\n")
            os.mkdir(os.path.join(tmp, "sub"))
            with open(os.path.join(tmp, "sub", "b.txt"), "w") as fh:
                fh.write("foo again\n")
            mine = run_mine(["-r", "foo"], cwd=tmp)
            gnu = run_gnu(["-r", "foo"], cwd=tmp)
            self.assertEqual(sorted_lines(mine.stdout),
                             sorted_lines(gnu.stdout))
            self.assertEqual(mine.returncode, gnu.returncode)

    def test_recursive_single_file_dir_prefixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "only"))
            with open(os.path.join(tmp, "only", "one.txt"), "w") as fh:
                fh.write("foo\n")
            mine = run_mine(["-r", "foo", "only"], cwd=tmp)
            gnu = run_gnu(["-r", "foo", "only"], cwd=tmp)
            self.assertEqual(mine.stdout, gnu.stdout)
            self.assertEqual(mine.stdout, b"only/one.txt:foo\n")


class TestExitCodesAndErrors(unittest.TestCase):
    def test_no_match_exit_1(self):
        proc = run_mine(["ZZZnope", ROCK])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, b"")

    def test_missing_file_exit_2(self):
        mine = run_mine(["foo", os.path.join(FIX, "does-not-exist.txt")])
        gnu = run_gnu(["foo", os.path.join(FIX, "does-not-exist.txt")])
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(gnu.returncode, 2)
        self.assertEqual(mine.stdout, b"")
        self.assertTrue(mine.stderr)

    def test_match_plus_error_still_exit_2(self):
        mine = run_mine(["line", TESTTXT, os.path.join(FIX, "missing.txt")])
        gnu = run_gnu(["line", TESTTXT, os.path.join(FIX, "missing.txt")])
        self.assertEqual(mine.stdout, gnu.stdout)
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(gnu.returncode, 2)

    def test_directory_without_r_exit_2(self):
        mine = run_mine(["foo", FIX])
        gnu = run_gnu(["foo", FIX])
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(gnu.returncode, 2)
        self.assertTrue(mine.stderr)

    def test_invalid_regex_exit_2(self):
        mine = run_mine(["[", ROCK])
        gnu = run_gnu(["[", ROCK])
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(gnu.returncode, 2)
        self.assertTrue(mine.stderr)

    def test_no_pattern_exit_2(self):
        self.assertEqual(run_mine([]).returncode, 2)
        self.assertEqual(run_mine(["-r"]).returncode, 2)
        self.assertTrue(run_mine([]).stderr)

    def test_unknown_option_exit_2(self):
        # --bogus-option is invalid for both tools (-x is NOT used:
        # it is GNU's valid --line-regexp, while this tool, per the
        # challenge page, supports only -r, -v, -i).
        mine = run_mine(["--bogus-option", "foo", ROCK])
        gnu = run_gnu(["--bogus-option", "foo", ROCK])
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(gnu.returncode, 2)
        self.assertTrue(mine.stderr)

    def test_dash_v_after_double_dash_is_pattern(self):
        # Without --, -v is the invert flag, not the pattern.
        proc = run_mine(["--", "-v", ROCK])
        self.assertEqual(proc.returncode, 1)  # no line is literally "-v"
        proc = run_mine(["-v", "Madonna", BFS])
        gnu = run_gnu(["-v", "Madonna", BFS])
        self.assertEqual(proc.stdout, gnu.stdout)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for cat.py. Run from the cat/ directory:

    python3 -m unittest discover -s tests -v

Output is compared byte-for-byte against system cat on the same
fixtures wherever the behaviour is meant to match it. The one
deliberate non-match is the stderr program-name prefix (ccat:
vs cat:), so error cases check our own format instead.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(HERE, "..", "cat.py")


def run_ccat(args, stdin=b""):
    return subprocess.run(
        [sys.executable, CAT] + args,
        input=stdin, capture_output=True, check=False,
    )


def run_system_cat(args, stdin=b""):
    return subprocess.run(
        ["cat"] + args, input=stdin, capture_output=True, check=False,
    )


class CatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.one = self._write("one.txt", b"alpha\nbeta\ngamma\n")
        self.two = self._write("two.txt", b"delta\nepsilon\n")
        self.blank = self._write(
            "blank.txt", b"a\n\nb\n \n\nc\n")
        self.nonewline = self._write("nonewline.txt", b"first\nsecond")
        self.empty = self._write("empty.txt", b"")
        self.binary = self._write(
            "binary.bin", bytes(range(256)) + b"\x00\xff\xfe\nlast")
        self.dash_n = self._write("-n", b"dash-n-file\n")
        os.mkdir(os.path.join(d, "adir"))

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def assert_matches_system(self, args, stdin=b""):
        """ccat stdout and exit status match system cat on same args."""
        got = run_ccat(args, stdin)
        want = run_system_cat(args, stdin)
        self.assertEqual(got.stdout, want.stdout,
                         f"stdout differs for args={args}")
        self.assertEqual(got.returncode, want.returncode,
                         f"exit status differs for args={args}")

    def test_step1_single_file(self):
        self.assert_matches_system([self.one])

    def test_step2_stdin_no_operands(self):
        self.assert_matches_system([], stdin=b"hello\nworld\n")

    def test_step2_stdin_dash_operand(self):
        self.assert_matches_system(["-"], stdin=b"hello\nworld\n")

    def test_step3_concatenate_two_files(self):
        self.assert_matches_system([self.one, self.two])

    def test_step3_concatenate_three_files(self):
        self.assert_matches_system([self.one, self.two, self.one])

    def test_step3_file_stdin_file(self):
        self.assert_matches_system(
            [self.one, "-", self.two], stdin=b"middle\n")

    def test_step4_number_all_lines(self):
        self.assert_matches_system(["-n", self.blank])

    def test_step4_number_stdin(self):
        self.assert_matches_system(["-n", "-"], stdin=b"x\n\ny\n")

    def test_step4_number_no_trailing_newline(self):
        self.assert_matches_system(["-n", self.nonewline])

    def test_step5_number_nonblank_lines(self):
        self.assert_matches_system(["-b", self.blank])

    def test_step5_blank_only_file(self):
        self.assert_matches_system(["-b", "-"], stdin=b"\n\n\n")

    def test_b_overrides_n_both_orders(self):
        self.assert_matches_system(["-n", "-b", self.blank])
        self.assert_matches_system(["-b", "-n", self.blank])

    def test_combined_nb_flag(self):
        self.assert_matches_system(["-nb", self.blank])

    def test_numbering_continues_across_files(self):
        self.assert_matches_system(["-n", self.one, self.two])
        self.assert_matches_system(["-b", self.blank, self.one])

    def test_empty_file_and_empty_stdin(self):
        self.assert_matches_system([self.empty])
        self.assert_matches_system([], stdin=b"")
        self.assert_matches_system(["-n", self.empty])
        self.assert_matches_system(["-b", "-"], stdin=b"")

    def test_binary_file(self):
        self.assert_matches_system([self.binary])
        self.assert_matches_system(["-n", self.binary])
        self.assert_matches_system(["-b", self.binary])

    def test_no_trailing_newline_preserved(self):
        for args in ([self.nonewline], ["-n", self.nonewline],
                     ["-b", self.nonewline]):
            got = run_ccat(args)
            self.assertFalse(got.stdout.endswith(b"\n"))
            self.assert_matches_system(args)

    def test_missing_file_continues_and_exits_1(self):
        missing = os.path.join(self.tmp.name, "nope.txt")
        got = run_ccat([missing, self.one])
        self.assertEqual(got.stdout, b"alpha\nbeta\ngamma\n")
        self.assertEqual(got.returncode, 1)
        self.assertEqual(
            got.stderr,
            f"ccat: {missing}: No such file or directory\n".encode())

    def test_directory_operand(self):
        adir = os.path.join(self.tmp.name, "adir")
        got = run_ccat([adir, self.one])
        self.assertEqual(got.stdout, b"alpha\nbeta\ngamma\n")
        self.assertEqual(got.returncode, 1)
        self.assertEqual(
            got.stderr, f"ccat: {adir}: Is a directory\n".encode())

    def test_unknown_option(self):
        got = run_ccat(["-x", self.one])
        self.assertEqual(got.stdout, b"")
        self.assertEqual(got.returncode, 1)
        self.assertEqual(got.stderr, b"ccat: invalid option -- 'x'\n")

    def test_double_dash_ends_options(self):
        # File literally named "-n" must be printed, not parsed.
        # Run in the fixture dir so "-n" resolves there.
        got = subprocess.run(
            [sys.executable, CAT, "--", "-n"],
            cwd=self.tmp.name, capture_output=True, check=False)
        self.assertEqual(got.stdout, b"dash-n-file\n")
        self.assertEqual(got.returncode, 0)


if __name__ == "__main__":
    unittest.main()

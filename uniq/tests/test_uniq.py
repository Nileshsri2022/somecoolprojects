#!/usr/bin/env python3
"""Tests for uniq.py: byte-for-byte comparison against system uniq,
plus I/O modes, combinations, byte fidelity, and error cases."""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "uniq.py")

sys.path.insert(0, ROOT)
import uniq as uniq_mod  # noqa: E402

PAGE_EXAMPLE = b"line1\nline2\nline2\nline3\nline4\n"
ALL_SAME = b"a\na\na\na\n"
NON_ADJACENT = b"a\nb\na\nb\n"
BLANKS = b"\n\nx\n\n\n"
NO_TRAILING_NL = b"a\na\nb"
CRLF = b"a\r\nb\r\nb\n"
NON_UTF8 = b"\xff\xfe\n\xff\xfe\nabc\n"
EMPTY = b""


def run_ours(args, data=None):
    """Run uniq.py as a subprocess; return (exit, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout, proc.stderr


def run_system(args, data=None):
    proc = subprocess.run(
        ["uniq"] + args, input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout, proc.stderr


def compare(testcase, args, data):
    """Ours must match system uniq byte-for-byte on stdout+exit."""
    ours = run_ours(args, data)
    system = run_system(args, data)
    testcase.assertEqual(ours[0], system[0], f"exit differs for {args}")
    testcase.assertEqual(ours[1], system[1], f"stdout differs for {args}")


class TestAgainstSystem(unittest.TestCase):
    def test_page_example_default(self):
        compare(self, [], PAGE_EXAMPLE)

    def test_empty(self):
        compare(self, [], EMPTY)

    def test_single_line(self):
        compare(self, [], b"only\n")

    def test_all_same(self):
        compare(self, [], ALL_SAME)

    def test_no_repeats(self):
        compare(self, [], b"a\nb\nc\n")

    def test_non_adjacent_repeats_survive(self):
        compare(self, [], NON_ADJACENT)

    def test_blank_lines(self):
        compare(self, [], BLANKS)

    def test_no_trailing_newline(self):
        compare(self, [], NO_TRAILING_NL)

    def test_crlf_distinct_from_lf(self):
        compare(self, [], CRLF)

    def test_non_utf8_round_trips(self):
        compare(self, [], NON_UTF8)

    def test_count(self):
        compare(self, ["-c"], PAGE_EXAMPLE)
        compare(self, ["--count"], ALL_SAME)
        compare(self, ["-c"], EMPTY)

    def test_repeated(self):
        compare(self, ["-d"], PAGE_EXAMPLE)
        compare(self, ["--repeated"], b"a\nb\nc\n")
        compare(self, ["-d"], ALL_SAME)

    def test_unique(self):
        compare(self, ["-u"], PAGE_EXAMPLE)
        compare(self, ["--unique"], ALL_SAME)

    def test_combinations(self):
        for args in (["-c", "-d"], ["-cd"], ["-c", "-u"],
                     ["-d", "-u"], ["--count", "--repeated"]):
            with self.subTest(args=args):
                compare(self, args, PAGE_EXAMPLE)
                compare(self, args, ALL_SAME)


class TestIOModes(unittest.TestCase):
    def test_stdin_dash(self):
        compare(self, ["-"], PAGE_EXAMPLE)

    def test_stdin_no_arg(self):
        compare(self, [], PAGE_EXAMPLE)

    def test_file_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "in.txt")
            with open(path, "wb") as f:
                f.write(PAGE_EXAMPLE)
            ours = run_ours([path])
            system = run_system([path])
            self.assertEqual(ours[1], system[1])
            self.assertEqual(ours[0], 0)

    def test_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.txt")
            out_path = os.path.join(tmp, "out.txt")
            with open(in_path, "wb") as f:
                f.write(PAGE_EXAMPLE)
            code, _, _ = run_ours([in_path, out_path])
            self.assertEqual(code, 0)
            with open(out_path, "rb") as f:
                content = f.read()
            self.assertEqual(content, b"line1\nline2\nline3\nline4\n")

    def test_stdin_to_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.txt")
            code, stdout, _ = run_ours(["-", out_path], PAGE_EXAMPLE)
            self.assertEqual(code, 0)
            self.assertEqual(stdout, b"")
            with open(out_path, "rb") as f:
                self.assertEqual(f.read(), b"line1\nline2\nline3\nline4\n")


class TestErrors(unittest.TestCase):
    def test_missing_input(self):
        code, _, err = run_ours(["/nonexistent-uniq-test.txt"])
        self.assertEqual(code, 1)
        self.assertIn(b"No such file or directory", err)
        self.assertIn(b"/nonexistent-uniq-test.txt", err)

    def test_extra_operand(self):
        code, _, err = run_ours(["a", "b", "c"])
        self.assertEqual(code, 1)
        self.assertIn(b"extra operand", err)
        self.assertIn(b"'c'", err)

    def test_unknown_option(self):
        code, _, _ = run_ours(["--bogus"])
        self.assertEqual(code, 2)

    def test_missing_input_does_not_clobber_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.txt")
            with open(out_path, "wb") as f:
                f.write(b"keep me\n")
            code, _, _ = run_ours(["/nonexistent-uniq-test.txt", out_path])
            self.assertEqual(code, 1)
            with open(out_path, "rb") as f:
                self.assertEqual(f.read(), b"keep me\n")


class TestKeepRun(unittest.TestCase):
    def test_default_keeps_all(self):
        self.assertTrue(uniq_mod.keep_run(1, False, False))
        self.assertTrue(uniq_mod.keep_run(2, False, False))

    def test_repeated_only(self):
        self.assertFalse(uniq_mod.keep_run(1, True, False))
        self.assertTrue(uniq_mod.keep_run(2, True, False))

    def test_unique_only(self):
        self.assertTrue(uniq_mod.keep_run(1, False, True))
        self.assertFalse(uniq_mod.keep_run(2, False, True))

    def test_repeated_and_unique_keeps_nothing(self):
        self.assertFalse(uniq_mod.keep_run(1, True, True))
        self.assertFalse(uniq_mod.keep_run(2, True, True))


if __name__ == "__main__":
    unittest.main()

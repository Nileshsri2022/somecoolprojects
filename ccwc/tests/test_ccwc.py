"""Tests for ccwc.py. Run from ccwc/: python3 -m unittest discover -s tests -v

ccwc.py is run as a subprocess, exactly as a user would run it.
-c, -l, -w, default, stdin and multi-file cases are compared
against system wc. -m is compared against hand-computed UTF-8
code-point counts, because system wc -m in a C locale equals -c
(see docs/SPEC.md).
"""

import os
import subprocess
import sys
import tempfile
import unittest

CCWC = os.path.join(os.path.dirname(__file__), "..", "ccwc.py")
FIXTURES = {
    "sample.txt": b"hello world\nhello again\n",      # 24B 2L 4W 24C
    "no_nl.txt": b"hello world\nhello again",         # 23B 1L 4W 23C
    "empty.txt": b"",                                  # 0  0  0  0
    "utf8.txt": "café 中文\n".encode("utf-8"),        # 13B 1L 2W 8C
}


def run_ccwc(args, stdin_data=None):
    proc = subprocess.run(
        [sys.executable, CCWC, *args],
        input=stdin_data, capture_output=True)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def run_wc(args, stdin_data=None):
    proc = subprocess.run(
        ["wc", *args], input=stdin_data, capture_output=True)
    return proc.stdout.decode()


class TestCcwc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = {}
        for name, data in FIXTURES.items():
            path = os.path.join(self.tmp.name, name)
            with open(path, "wb") as f:
                f.write(data)
            self.paths[name] = path

    def tearDown(self):
        self.tmp.cleanup()

    def assert_matches_wc(self, ccwc_args, wc_args):
        code, out, _ = run_ccwc(ccwc_args)
        self.assertEqual(code, 0)
        self.assertEqual(out, run_wc(wc_args))

    def test_single_options_match_wc(self):
        for flag in ("-c", "-l", "-w"):
            with self.subTest(flag=flag):
                path = self.paths["sample.txt"]
                self.assert_matches_wc([flag, path], [flag, path])

    def test_m_counts_code_points(self):
        code, out, _ = run_ccwc(["-m", self.paths["utf8.txt"]])
        self.assertEqual(code, 0)
        self.assertEqual(out, f"8 {self.paths['utf8.txt']}\n")

    def test_default_matches_wc(self):
        path = self.paths["sample.txt"]
        self.assert_matches_wc([path], [path])

    def test_no_trailing_newline_line_count(self):
        code, out, _ = run_ccwc(["-l", self.paths["no_nl.txt"]])
        self.assertEqual(out, f"1 {self.paths['no_nl.txt']}\n")

    def test_empty_file(self):
        path = self.paths["empty.txt"]
        self.assert_matches_wc([path], [path])
        code, out, _ = run_ccwc(["-c", "-l", "-w", "-m", path])
        self.assertEqual(out, "0 0 0 0 " + path + "\n")

    def test_stdin_single_count_no_filename(self):
        code, out, _ = run_ccwc(["-l"], stdin_data=FIXTURES["sample.txt"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "2\n")

    def test_stdin_default_matches_wc(self):
        code, out, _ = run_ccwc([], stdin_data=FIXTURES["sample.txt"])
        self.assertEqual(code, 0)
        self.assertEqual(out, run_wc([], stdin_data=FIXTURES["sample.txt"]))

    def test_multiple_files_and_total_match_wc(self):
        a, b = self.paths["sample.txt"], self.paths["no_nl.txt"]
        self.assert_matches_wc(["-l", "-w", a, b], ["-l", "-w", a, b])

    def test_unknown_option_fails(self):
        code, _, err = run_ccwc(["-z", self.paths["sample.txt"]])
        self.assertNotEqual(code, 0)
        self.assertIn("invalid option", err)

    def test_missing_file_fails(self):
        code, out, err = run_ccwc([os.path.join(self.tmp.name, "nope.txt")])
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("nope.txt", err)


if __name__ == "__main__":
    unittest.main()

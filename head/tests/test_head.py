"""Tests for head.py: byte-for-byte vs system head, plus error cases."""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HEAD_PY = os.path.join(ROOT, "head.py")
PY = sys.executable

LINES20 = "".join(f"line {i}\n" for i in range(1, 21)).encode()
LINES5 = b"l1\nl2\nl3\nl4\nl5\n"
BINARY = bytes(range(256)) * 4  # 1024 bytes, incl. NULs and non-UTF-8
GUTENBERG_FIRST = b"The Project Gutenberg eBook of The Art of War\n"


def run_mine(args, stdin=b"", cwd=None):
    proc = subprocess.run([PY, HEAD_PY] + args, input=stdin,
                          capture_output=True, cwd=cwd)
    return proc.returncode, proc.stdout, proc.stderr


def run_system(args, stdin=b"", cwd=None):
    proc = subprocess.run(["head"] + args, input=stdin,
                          capture_output=True, cwd=cwd)
    return proc.returncode, proc.stdout, proc.stderr


class HeadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.f20 = self._write("f20.txt", LINES20)
        self.f5 = self._write("f5.txt", LINES5)
        self.fbin = self._write("bin.dat", BINARY)
        self.fempty = self._write("empty.txt", b"")
        self.fnonl = self._write("nonl.txt", b"no-newline")
        self.fgut = self._write("gut.txt", GUTENBERG_FIRST + b"rest\nmore\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data):
        path = os.path.join(self.d, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def assert_matches_system(self, args, stdin=b""):
        """Mine and system head must agree on stdout, stderr, exit."""
        mine = run_mine(args, stdin=stdin, cwd=self.d)
        system = run_system(args, stdin=stdin, cwd=self.d)
        self.assertEqual(mine, system,
                         f"args={args!r}\nmine={mine!r}\nsystem={system!r}")

    # Step 1: default 10 lines
    def test_default_one_file(self):
        self.assert_matches_system(["f20.txt"])

    def test_default_stdin(self):
        self.assert_matches_system([], stdin=LINES20)

    def test_default_short_file(self):
        self.assert_matches_system(["f5.txt"])

    def test_default_empty_file(self):
        self.assert_matches_system(["empty.txt"])

    # Step 2: -n
    def test_n_variants(self):
        for args in (["-n1", "f20.txt"], ["-n", "1", "f20.txt"],
                     ["-n3", "f5.txt"], ["-n", "10", "f5.txt"],
                     ["-n0", "f20.txt"], ["-n100", "f5.txt"],
                     ["-n2", "nonl.txt"], ["--lines=3", "f20.txt"],
                     ["--lines", "3", "f20.txt"], ["-2", "f20.txt"]):
            with self.subTest(args=args):
                self.assert_matches_system(args)

    def test_n_negative(self):
        for args in (["-n", "-2", "f5.txt"], ["-n-2", "f5.txt"],
                     ["-n", "-100", "f5.txt"], ["-n", "-0", "f5.txt"],
                     ["-n", "-1", "nonl.txt"]):
            with self.subTest(args=args):
                self.assert_matches_system(args)

    def test_n_stdin(self):
        self.assert_matches_system(["-n3"], stdin=LINES20)
        self.assert_matches_system(["-n", "-2"], stdin=LINES5)

    # Step 3: -c
    def test_c_variants(self):
        for args in (["-c", "31", "gut.txt"], ["-c31", "gut.txt"],
                     ["-c0", "f20.txt"], ["-c10000", "f5.txt"],
                     ["-c", "5", "nonl.txt"], ["--bytes=7", "f5.txt"],
                     ["-c", "100", "bin.dat"], ["-c", "1024", "bin.dat"]):
            with self.subTest(args=args):
                self.assert_matches_system(args)

    def test_c_negative(self):
        for args in (["-c", "-3", "f5.txt"], ["-c-3", "f5.txt"],
                     ["-c", "-100", "f5.txt"], ["-c", "-0", "f5.txt"]):
            with self.subTest(args=args):
                self.assert_matches_system(args)

    def test_c_binary_exact(self):
        # 31 bytes of the Gutenberg first line. Note the page's
        # Step 3 display shows 'The Project Gutenberg eBook'
        # but the 31st byte is the space after 'of': the true
        # first 31 bytes are 'The Project Gutenberg eBook of '.
        rc, out, _ = run_mine(["-c", "31", "gut.txt"], cwd=self.d)
        self.assertEqual(rc, 0)
        self.assertEqual(out, b"The Project Gutenberg eBook of ")
        self.assertEqual(len(out), 31)

    # Step 4: multi-file headers
    def test_multi_file(self):
        self.assert_matches_system(["-n", "10", "f5.txt", "f20.txt"])
        self.assert_matches_system(["f5.txt", "f20.txt", "nonl.txt"])
        self.assert_matches_system(["-c", "4", "f5.txt", "f20.txt"])
        self.assert_matches_system(["-q", "f5.txt", "f20.txt"])
        self.assert_matches_system(["-v", "f5.txt"])
        self.assert_matches_system(["--quiet", "f5.txt", "f20.txt"])
        self.assert_matches_system(["--verbose", "f5.txt"])
        self.assert_matches_system(["-n1", "f5.txt", "-", "f20.txt"],
                                   stdin=LINES5)
        self.assert_matches_system(["-v", "-n1"], stdin=LINES5)
        self.assert_matches_system(["-v", "-"], stdin=LINES5)

    def test_last_wins(self):
        self.assert_matches_system(["-n1", "-c2", "f5.txt"])
        self.assert_matches_system(["-c2", "-n1", "f5.txt"])

    # Page examples
    def test_page_n1(self):
        rc, out, _ = run_mine(["-n1", "gut.txt"], cwd=self.d)
        self.assertEqual(out, GUTENBERG_FIRST)

    # Errors (messages are ours; checked literally, not vs system,
    # except missing-file/dir cases where GNU wording matches)
    def test_missing_file_continues(self):
        self.assert_matches_system(["missing_xyz", "f5.txt"])
        rc, out, err = run_mine(["missing_xyz"], cwd=self.d)
        self.assertEqual(rc, 1)
        self.assertEqual(out, b"")
        self.assertIn(b"cannot open 'missing_xyz' for reading", err)

    def test_directory(self):
        self.assert_matches_system(["f5.txt", self.d])
        self.assert_matches_system([self.d])
        rc, _, err = run_mine([self.d], cwd=self.d)
        self.assertEqual(rc, 1)
        self.assertIn(b"error reading", err)

    def test_invalid_count(self):
        for args in (["-n", "x", "f5.txt"], ["-c", "1K", "f5.txt"],
                     ["-n", "", "f5.txt"], ["-n=4", "f5.txt"]):
            with self.subTest(args=args):
                rc, _, err = run_mine(args, cwd=self.d)
                self.assertEqual(rc, 1)
                self.assertIn(b"invalid number of", err)

    def test_unknown_option(self):
        for args in (["--bogus", "f5.txt"], ["-z", "f5.txt"],
                     ["--version", "f5.txt"]):
            with self.subTest(args=args):
                rc, _, err = run_mine(args, cwd=self.d)
                self.assertEqual(rc, 1)
                self.assertTrue(err.startswith(b"head: "))

    def test_missing_value(self):
        rc, _, err = run_mine(["-n"], cwd=self.d)
        self.assertEqual(rc, 1)
        self.assertIn(b"option requires an argument", err)

    def test_dashdash_stops_options(self):
        # A file literally named '-n' is read, not parsed as option.
        self._write("-n", b"dashfile\n")
        self.assert_matches_system(["--", "-n"])

    def test_help(self):
        proc = subprocess.run([PY, HEAD_PY, "--help"],
                              capture_output=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn(b"Usage: head", proc.stdout)


if __name__ == "__main__":
    unittest.main()

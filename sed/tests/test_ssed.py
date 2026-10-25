#!/usr/bin/env python3
"""Tests for ssed.py. Run from the project directory:

    python3 -m unittest discover -s tests -v

All tests run the real CLI as a subprocess. The VsSystemSed class
compares stdout byte-for-byte against GNU sed on patterns valid
in both regex dialects (see README.md for dialect divergences:
GNU BRE groups are \\(...\\), Python groups are (...), so group
tests live in TestSsedOnly, using Python syntax).
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SSED = os.path.join(ROOT, "ssed.py")
QUOTES = os.path.join(HERE, "fixtures", "quotes.txt")


def run_ssed(args, inp=None, cwd=None):
    return subprocess.run(
        [sys.executable, SSED] + args, input=inp, capture_output=True,
        cwd=cwd or ROOT)


def run_sed(args, inp=None):
    return subprocess.run(
        ["sed"] + args, input=inp, capture_output=True)


def quotes_text():
    with open(QUOTES, "rb") as fh:
        return fh.read()


class TestSteps(unittest.TestCase):
    """The challenge page's Steps 1-6, verbatim."""

    def test_step1_strip_quotes(self):
        out = run_ssed(["s/\"//g", QUOTES])
        self.assertEqual(out.returncode, 0)
        self.assertNotIn(b'"', out.stdout)
        self.assertTrue(out.stdout.startswith(
            b"Life isn\xe2\x80\x99t about getting"))

    def test_step2_line_range(self):
        out = run_ssed(["-n", "2,4p", QUOTES])
        lines = out.stdout.decode().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Whatever the mind", lines[0])
        self.assertIn("Two roads diverged", lines[2])

    def test_step3_regex_address(self):
        out = run_ssed(["-n", "/roads/p", QUOTES])
        self.assertEqual(out.stdout.decode().count("\n"), 1)
        self.assertIn("Two roads diverged", out.stdout.decode())

    def test_step4_double_space(self):
        out = run_ssed(["G", QUOTES])
        self.assertEqual(out.stdout, quotes_text().replace(b"\n", b"\n\n"))

    def test_step5_delete_blank(self):
        inp = b"a\n\nb\n\n\nc\n"
        out = run_ssed(["/^$/d"], inp=inp)
        self.assertEqual(out.stdout, b"a\nb\nc\n")

    def test_step6_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "unquoted.txt")
            with open(path, "wb") as fh:
                fh.write(quotes_text())
            out = run_ssed(["-i", "s/Life/Code/g", path])
            self.assertEqual(out.returncode, 0)
            with open(path, "rb") as fh:
                data = fh.read()
            self.assertTrue(data.startswith(b'"Code isn'))
            self.assertNotIn(b'"Life', data)


class TestSubstitution(unittest.TestCase):
    def test_first_only_vs_global(self):
        self.assertEqual(run_ssed(["s/a/X/"], inp=b"aaa\n").stdout, b"Xaa\n")
        self.assertEqual(run_ssed(["s/a/X/g"], inp=b"aaa\n").stdout, b"XXX\n")

    def test_alternate_delimiters(self):
        self.assertEqual(run_ssed(["s|a|b|g"], inp=b"a/a\n").stdout, b"b/b\n")
        self.assertEqual(run_ssed(["s#a#b#"], inp=b"a a\n").stdout, b"b a\n")

    def test_escaped_delimiter(self):
        self.assertEqual(run_ssed(["s/\\//X/g"], inp=b"a/b\n").stdout,
                         b"aXb\n")

    def test_ampersand_and_groups(self):
        self.assertEqual(run_ssed(["s/a/&-&/"], inp=b"a\n").stdout, b"a-a\n")
        self.assertEqual(run_ssed(["s/(a)(b)/\\2\\1/"], inp=b"ab\n").stdout,
                         b"ba\n")
        # Unmatched group expands to empty.
        self.assertEqual(
            run_ssed(["s/(a)|(z)/[\\1][\\2]/"], inp=b"a\n").stdout, b"[a][]\n")

    def test_nth_occurrence(self):
        self.assertEqual(run_ssed(["s/a/X/2"], inp=b"aaa\n").stdout, b"aXa\n")

    def test_case_insensitive_flag(self):
        self.assertEqual(run_ssed(["s/a/X/gi"], inp=b"AaA\n").stdout, b"XXX\n")

    def test_p_flag_with_and_without_n(self):
        self.assertEqual(run_ssed(["s/a/X/p"], inp=b"a\nb\n").stdout,
                         b"X\nX\nb\n")
        self.assertEqual(run_ssed(["-n", "s/a/X/p"], inp=b"a\nb\n").stdout,
                         b"X\n")

    def test_w_flag(self):
        with tempfile.TemporaryDirectory() as td:
            w = os.path.join(td, "w.txt")
            out = run_ssed(["s/a/X/w " + w], inp=b"a\nb\na\n")
            self.assertEqual(out.stdout, b"X\nb\nX\n")
            with open(w, "rb") as fh:
                self.assertEqual(fh.read(), b"X\nX\n")

    def test_empty_pattern_reuses_last(self):
        # Last regex is the address regex /b/; s// then reuses it.
        out = run_ssed(["-e", "/b/p", "-e", "s//X/"], inp=b"abc\n")
        # -e scripts run in order for every line: p prints abc (via
        # address match), then s replaces b -> aXc, auto-printed.
        self.assertEqual(out.stdout, b"abc\naXc\n")

    def test_semicolon_separated(self):
        self.assertEqual(run_ssed(["s/a/X/;p"], inp=b"a\n").stdout,
                         b"X\nX\n")

    def test_multiple_e(self):
        out = run_ssed(["-e", "s/a/X/", "-e", "/^$/d"], inp=b"a\n\nb\n")
        self.assertEqual(out.stdout, b"X\nb\n")

    def test_f_script(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "s.sed")
            with open(script, "w") as fh:
                fh.write("s/a/X/g\n")
            out = run_ssed(["-f", script], inp=b"aaa\n")
            self.assertEqual(out.stdout, b"XXX\n")


class TestAddresses(unittest.TestCase):
    LINES = b"one\ntwo\nthree\nfour\nfive\n"

    def test_single_line_and_last(self):
        self.assertEqual(run_ssed(["-n", "3p"], inp=self.LINES).stdout,
                         b"three\n")
        self.assertEqual(run_ssed(["-n", "$p"], inp=self.LINES).stdout,
                         b"five\n")

    def test_range_line_line(self):
        self.assertEqual(run_ssed(["-n", "2,4p"], inp=self.LINES).stdout,
                         b"two\nthree\nfour\n")

    def test_range_regex_regex(self):
        self.assertEqual(
            run_ssed(["-n", "/two/,/four/p"], inp=self.LINES).stdout,
            b"two\nthree\nfour\n")

    def test_range_line_to_regex(self):
        self.assertEqual(
            run_ssed(["-n", "1,/three/p"], inp=self.LINES).stdout,
            b"one\ntwo\nthree\n")

    def test_range_regex_to_last(self):
        self.assertEqual(
            run_ssed(["-n", "/three/,$p"], inp=self.LINES).stdout,
            b"three\nfour\nfive\n")

    def test_range_end_below_start_is_single_line(self):
        self.assertEqual(run_ssed(["-n", "2,1p"], inp=self.LINES).stdout,
                         b"two\n")

    def test_range_end_regex_not_tested_on_start_line(self):
        # 'ab' contains both /a/ and /b/; the range must not close
        # on the start line, so it runs to EOF.
        self.assertEqual(
            run_ssed(["-n", "/a/,/b/p"], inp=b"ab\nc\n").stdout, b"ab\nc\n")

    def test_address_case_insensitive_I(self):
        self.assertEqual(
            run_ssed(["-n", "/TWO/Ip"], inp=self.LINES).stdout, b"two\n")

    def test_address_on_s_and_d(self):
        self.assertEqual(
            run_ssed(["2s/t/T/"], inp=self.LINES).stdout,
            b"one\nTwo\nthree\nfour\nfive\n")
        self.assertEqual(run_ssed(["2,3d"], inp=self.LINES).stdout,
                         b"one\nfour\nfive\n")

    def test_alternate_address_delimiter(self):
        self.assertEqual(
            run_ssed(["-n", "\\|two|p"], inp=self.LINES).stdout, b"two\n")


class TestCommandsAndInput(unittest.TestCase):
    def test_delete(self):
        self.assertEqual(run_ssed(["2d"], inp=b"a\nb\nc\n").stdout, b"a\nc\n")

    def test_quit(self):
        self.assertEqual(run_ssed(["2q"], inp=b"a\nb\nc\n").stdout, b"a\nb\n")
        # q obeys -n: nothing is auto-printed.
        self.assertEqual(run_ssed(["-n", "2q"], inp=b"a\nb\nc\n").stdout, b"")

    def test_stdin_no_file_and_dash(self):
        self.assertEqual(run_ssed(["s/a/X/"], inp=b"a\n").stdout, b"X\n")
        self.assertEqual(run_ssed(["s/a/X/", "-"], inp=b"a\n").stdout, b"X\n")

    def test_multiple_files_line_numbers_reset(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "f1"); f2 = os.path.join(td, "f2")
            for p, data in ((f1, b"a\nb\n"), (f2, b"c\nd\n")):
                with open(p, "wb") as fh:
                    fh.write(data)
            out = run_ssed(["-n", "1p", f1, f2])
            self.assertEqual(out.stdout, b"a\nc\n")

    def test_final_line_without_newline(self):
        self.assertEqual(run_ssed(["s/a/A/"], inp=b"a").stdout, b"A")
        self.assertEqual(run_ssed(["s/a/A/"], inp=b"a\nb").stdout, b"A\nb")
        self.assertEqual(run_ssed(["G"], inp=b"a").stdout, b"a\n\n")
        # p print + auto print; only the last chunk loses its newline.
        self.assertEqual(run_ssed(["p"], inp=b"a").stdout, b"a\na")
        self.assertEqual(run_ssed(["-n", "p"], inp=b"a\nb").stdout, b"a\nb")

    def test_multi_file_unterminated_gains_newline(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "f1"); f2 = os.path.join(td, "f2")
            with open(f1, "wb") as fh:
                fh.write(b"a")
            with open(f2, "wb") as fh:
                fh.write(b"b\n")
            out = run_ssed(["p", f1, f2])
            self.assertEqual(out.stdout, b"a\na\nb\nb\n")

    def test_empty_input(self):
        self.assertEqual(run_ssed(["s/a/X/g"], inp=b"").stdout, b"")

    def test_in_place_backup(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "f.txt")
            with open(path, "wb") as fh:
                fh.write(b"hello\n")
            out = run_ssed(["-i.bak", "s/hello/goodbye/", path])
            self.assertEqual(out.returncode, 0)
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"goodbye\n")
            with open(path + ".bak", "rb") as fh:
                self.assertEqual(fh.read(), b"hello\n")

    def test_in_place_stdin_passthrough(self):
        out = run_ssed(["-i", "s/a/X/"], inp=b"a\n")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, b"a\n")

    def test_in_place_multiple_files(self):
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for name, data in (("a", b"x\n"), ("b", b"y\n")):
                p = os.path.join(td, name)
                with open(p, "wb") as fh:
                    fh.write(data)
                paths.append(p)
            run_ssed(["-i", "s/x/X/;s/y/Y/"] + paths)
            with open(paths[0], "rb") as fh:
                self.assertEqual(fh.read(), b"X\n")
            with open(paths[1], "rb") as fh:
                self.assertEqual(fh.read(), b"Y\n")

    def test_hash_n_enables_quiet(self):
        out = run_ssed(["#n\np"], inp=b"a\n")
        self.assertEqual(out.stdout, b"a\n")


class TestErrors(unittest.TestCase):
    def test_unterminated_s(self):
        out = run_ssed(["s/a"], inp=b"a\n")
        self.assertEqual(out.returncode, 1)
        self.assertIn(b"ssed:", out.stderr)

    def test_unknown_command(self):
        out = run_ssed(["x"], inp=b"a\n")
        self.assertEqual(out.returncode, 1)

    def test_g_plus_number_conflict(self):
        out = run_ssed(["s/a/X/g2"], inp=b"a\n")
        self.assertEqual(out.returncode, 1)

    def test_address_zero(self):
        out = run_ssed(["0p"], inp=b"a\n")
        self.assertEqual(out.returncode, 1)

    def test_missing_file_continues(self):
        with tempfile.TemporaryDirectory() as td:
            good = os.path.join(td, "good")
            with open(good, "wb") as fh:
                fh.write(b"ok\n")
            missing = os.path.join(td, "missing")
            out = run_ssed(["p", missing, good])
            self.assertEqual(out.returncode, 2)
            self.assertIn(b"ok\n", out.stdout)
            self.assertIn(b"can't read", out.stderr)

    def test_no_script(self):
        out = run_ssed([])
        self.assertEqual(out.returncode, 1)

    def test_unknown_option(self):
        out = run_ssed(["-z", "p"], inp=b"a\n")
        self.assertEqual(out.returncode, 1)


class VsSystemSed(unittest.TestCase):
    """Byte-for-byte stdout equality with GNU sed, on patterns
    valid in both dialects. Exit codes compared too."""

    CASES = [
        (["s/a/X/g"], b"aaa\nbab\n"),
        (["s/a/X/2"], b"aaa\n"),
        (["s/a/&-&/"], b"a a\n"),
        (["s/a/X/gi"], b"AaA\n"),
        (["s|/|X|g"], b"a/b/c\n"),
        (["s#a#b#"], b"a a\n"),
        (["s/\\//X/g"], b"a/b\n"),
        (["s/a/X/p"], b"a\nb\n"),
        (["-n", "s/a/X/p"], b"a\nb\n"),
        (["s/a/X/;p"], b"a\n"),
        (["-n", "2,4p"], b"1\n2\n3\n4\n5\n"),
        (["-n", "/b/,/d/p"], b"a\nb\nc\nd\ne\n"),
        (["-n", "/a/,/b/p"], b"ab\nc\nd\n"),
        (["-n", "2,$p"], b"a\nb\nc\n"),
        (["-n", "1,/c/p"], b"a\nb\nc\nd\n"),
        (["-n", "2,1p"], b"a\nb\nc\n"),
        (["-n", "3p"], b"a\nb\nc\n"),
        (["-n", "$p"], b"a\nb\nc\n"),
        (["-n", "/A/Ip"], b"aA\nb\n"),
        (["G"], b"x\ny\n"),
        (["G"], b"x"),
        (["/^$/d"], b"a\n\nb\n\n"),
        (["2d"], b"a\nb\nc\n"),
        (["2,3d"], b"a\nb\nc\nd\n"),
        (["q"], b"a\nb\nc\n"),
        (["-n", "2q"], b"a\nb\nc\n"),
        (["-e", "s/a/X/", "-e", "/^$/d"], b"a\n\nb\n"),
        (["s/a/A/"], b"a"),
        (["s/a/A/"], b"a\nb"),
        (["p"], b"a"),
        (["-n", "p"], b"a\nb"),
        (["s/a/A/p"], b"a"),
        (["-n", "s/a/A/p"], b"a"),
        (["G;p"], b"a"),
        (["s/a/x\\ny/"], b"a"),
        (["s/a/X/g"], b""),
        (["s/a/X/g"], b"\n\n"),
    ]

    def test_vs_system_sed(self):
        for args, inp in self.CASES:
            with self.subTest(args=args, inp=inp):
                g = run_sed(args, inp)
                m = run_ssed(args, inp)
                self.assertEqual(m.stdout, g.stdout)
                self.assertEqual(m.returncode, g.returncode)

    def test_vs_system_sed_quotes_fixture(self):
        for args in (["s/\"//g"], ["-n", "2,4p"], ["-n", "/roads/p"],
                     ["G"], ["/^$/d"]):
            with self.subTest(args=args):
                g = run_sed(args + [QUOTES])
                m = run_ssed(args + [QUOTES])
                self.assertEqual(m.stdout, g.stdout)
                self.assertEqual(m.returncode, g.returncode)

    def test_vs_system_sed_multi_file(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "f1"); f2 = os.path.join(td, "f2")
            with open(f1, "wb") as fh:
                fh.write(b"a")
            with open(f2, "wb") as fh:
                fh.write(b"b\n")
            g = run_sed(["p", f1, f2])
            m = run_ssed(["p", f1, f2])
            self.assertEqual(m.stdout, g.stdout)


if __name__ == "__main__":
    unittest.main()

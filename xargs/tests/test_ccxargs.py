#!/usr/bin/env python3
"""Tests for ccxargs. Harmless commands only (echo/true/cat/sed/sh/sleep)."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CCXARGS = os.path.join(HERE, "ccxargs.py")
SYS_XARGS = shutil.which("xargs")


def run_cc(args, inp, cwd=None):
    """Run ccxargs; inp is bytes. Returns (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, CCXARGS] + args,
        input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def run_sys(args, inp):
    proc = subprocess.run(
        ["xargs"] + args,
        input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def oracle(testcase, args, inp):
    """Compare ccxargs against system xargs on identical input."""
    if SYS_XARGS is None:
        testcase.skipTest("system xargs not available")
    ours = run_cc(args, inp)
    theirs = run_sys(args, inp)
    testcase.assertEqual(ours[0], theirs[0], "exit code differs: %r vs %r" % (ours, theirs))
    testcase.assertEqual(ours[1], theirs[1], "stdout differs: %r vs %r" % (ours, theirs))


class TestBasic(unittest.TestCase):
    def test_default_utility_is_echo(self):
        rc, out, _ = run_cc([], b"hello world\n")
        self.assertEqual((rc, out), (0, "hello world\n"))

    def test_page_cat_example(self):
        with tempfile.TemporaryDirectory() as d:
            for i in (1, 2, 3):
                with open(os.path.join(d, "test-%d.txt" % i), "w") as fh:
                    fh.write("This is file %d\n" % i)
            names = b"test-1.txt test-2.txt test-3.txt"
            rc, out, _ = run_cc(["cat"], names, cwd=d)
            self.assertEqual(rc, 0)
            self.assertEqual(out, "This is file 1\nThis is file 2\nThis is file 3\n")

    def test_page_sed_example(self):
        with tempfile.TemporaryDirectory() as d:
            for i in (1, 2, 3):
                with open(os.path.join(d, "test-%d.txt" % i), "w") as fh:
                    fh.write("This is file %d\n" % i)
            rc, out, _ = run_cc(["sed", "s/file/test/g"],
                                b"test-1.txt test-2.txt test-3.txt", cwd=d)
            self.assertEqual(rc, 0)
            self.assertEqual(out, "This is test 1\nThis is test 2\nThis is test 3\n")

    def test_two_plus_initial_args(self):
        rc, out, _ = run_cc(["echo", "pre", "mid"], b"a b\n")
        self.assertEqual((rc, out), (0, "pre mid a b\n"))

    def test_initial_args_repeat_per_invocation(self):
        rc, out, _ = run_cc(["-n", "1", "echo", "pre"], b"a b\n")
        self.assertEqual((rc, out), (0, "pre a\npre b\n"))

    def test_utility_after_double_dash(self):
        rc, out, _ = run_cc(["--", "echo"], b"x\n")
        self.assertEqual((rc, out), (0, "x\n"))

    def test_empty_input_runs_once_without_r(self):
        rc, out, _ = run_cc(["echo", "EMPTY"], b"")
        self.assertEqual((rc, out), (0, "EMPTY\n"))

    def test_empty_input_runs_nothing_with_r(self):
        rc, out, _ = run_cc(["-r", "echo", "NOPE"], b"")
        self.assertEqual((rc, out), (0, ""))

    def test_whitespace_only_input_with_r(self):
        rc, out, _ = run_cc(["-r", "echo", "NOPE"], b"  \n\t\n")
        self.assertEqual((rc, out), (0, ""))

    def test_no_items_no_utility(self):
        rc, out, _ = run_cc([], b"")
        self.assertEqual((rc, out), (0, "\n"))


class TestMaxArgs(unittest.TestCase):
    def test_n1(self):
        rc, out, _ = run_cc(["-n", "1", "echo"], b"a b c\n")
        self.assertEqual((rc, out), (0, "a\nb\nc\n"))

    def test_n2(self):
        rc, out, _ = run_cc(["-n", "2", "echo"], b"a b c d e\n")
        self.assertEqual((rc, out), (0, "a b\nc d\ne\n"))

    def test_n_attached_and_long(self):
        rc, out, _ = run_cc(["-n2", "echo"], b"a b c\n")
        self.assertEqual(out, "a b\nc\n")
        rc, out, _ = run_cc(["--max-args=2", "echo"], b"a b c\n")
        self.assertEqual(out, "a b\nc\n")

    def test_n0_is_error(self):
        rc, out, err = run_cc(["-n", "0", "echo"], b"a\n")
        self.assertEqual(rc, 1)
        self.assertIn("ccxargs", err)

    def test_n_non_numeric_is_error(self):
        rc, _, _ = run_cc(["-n", "abc", "echo"], b"a\n")
        self.assertEqual(rc, 1)


class TestMaxProcs(unittest.TestCase):
    def test_p2_runs_everything(self):
        rc, out, _ = run_cc(["-n", "1", "-P", "2", "echo"], b"a b c d\n")
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(out.splitlines()), ["a", "b", "c", "d"])

    def test_p0_runs_everything(self):
        rc, out, _ = run_cc(["-n", "1", "-P", "0", "echo"], b"a b c\n")
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(out.splitlines()), ["a", "b", "c"])

    def test_p_negative_is_error(self):
        rc, _, _ = run_cc(["-P", "-1", "echo"], b"a\n")
        self.assertEqual(rc, 1)

    def test_parallel_is_faster(self):
        # 4 x 0.2 s sequential = ~0.8 s; parallel (-P 4) must be < 0.7 s.
        inp = b"0.2 0.2 0.2 0.2\n"
        start = time.monotonic()
        rc, out, _ = run_cc(["-n", "1", "-P", "4", "sh", "-c",
                             "sleep \"$1\"; echo done", "sh"], inp)
        elapsed = time.monotonic() - start
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("done"), 4)
        self.assertLess(elapsed, 0.7)

    def test_p_with_true(self):
        rc, out, _ = run_cc(["-n", "1", "-P", "3", "true"], b"a b c\n")
        self.assertEqual((rc, out), (0, ""))


class TestNullAndDelimiter(unittest.TestCase):
    def test_null_basic(self):
        rc, out, _ = run_cc(["-0", "echo"], b"a b\x00c\x00")
        self.assertEqual((rc, out), (0, "a b c\n"))

    def test_null_quotes_literal(self):
        rc, out, _ = run_cc(["-0", "echo"], b"'a b'\x00")
        self.assertEqual((rc, out), (0, "'a b'\n"))

    def test_null_empty_items_kept(self):
        rc, out, _ = run_cc(["-0", "-n", "1", "echo"], b"a\x00\x00b\x00")
        self.assertEqual((rc, out), (0, "a\n\nb\n"))

    def test_delimiter(self):
        rc, out, _ = run_cc(["-d", ",", "echo"], b"a,b c,d")
        self.assertEqual((rc, out), (0, "a b c d\n"))

    def test_delimiter_escape(self):
        rc, out, _ = run_cc(["-d", "\\n", "-n", "1", "echo"], b"a\nb\n")
        self.assertEqual((rc, out), (0, "a\nb\n"))

    def test_null_and_delimiter_conflict(self):
        rc, _, _ = run_cc(["-0", "-d", ",", "echo"], b"a\n")
        self.assertEqual(rc, 1)


class TestReplace(unittest.TestCase):
    def test_replace_middle(self):
        rc, out, _ = run_cc(["-I{}", "echo", "pre-{}-post"], b"a\n")
        self.assertEqual((rc, out), (0, "pre-a-post\n"))

    def test_replace_custom_string(self):
        rc, out, _ = run_cc(["-I", "XX", "echo", "XX!"], b"hi\n")
        self.assertEqual((rc, out), (0, "hi!\n"))

    def test_replace_implies_one_line(self):
        rc, out, _ = run_cc(["-I{}", "echo", "{}"], b"a\nb\nc\n")
        self.assertEqual((rc, out), (0, "a\nb\nc\n"))

    def test_replace_multi_token_line_is_one_arg(self):
        rc, out, _ = run_cc(["-I{}", "echo", "X{}Y"], b"a b\n")
        self.assertEqual((rc, out), (0, "Xa bY\n"))

    def test_replace_no_occurrence_no_append(self):
        # Matches GNU: line is not appended when replstr is absent.
        rc, out, _ = run_cc(["-I{}", "echo", "noplace"], b"a\n")
        self.assertEqual((rc, out), (0, "noplace\n"))

    def test_replace_no_initial_args(self):
        rc, out, _ = run_cc(["-I{}", "echo"], b"a b\n")
        self.assertEqual((rc, out), (0, "a b\n"))

    def test_replace_skips_blank_lines(self):
        rc, out, _ = run_cc(["-I{}", "echo", "{}"], b"a\n\nb\n")
        self.assertEqual((rc, out), (0, "a\nb\n"))

    def test_replace_multiple_occurrences(self):
        rc, out, _ = run_cc(["-I{}", "echo", "{}-{}"], b"z\n")
        self.assertEqual((rc, out), (0, "z-z\n"))

    def test_replace_empty_string_is_error(self):
        rc, _, _ = run_cc(["-I", "", "echo"], b"a\n")
        self.assertEqual(rc, 1)


class TestMaxLines(unittest.TestCase):
    def test_L1(self):
        rc, out, _ = run_cc(["-L", "1", "echo"], b"a b\nc d\n")
        self.assertEqual((rc, out), (0, "a b\nc d\n"))

    def test_L2(self):
        rc, out, _ = run_cc(["-L", "2", "echo"], b"a\nb\nc\n")
        self.assertEqual((rc, out), (0, "a b\nc\n"))

    def test_L_blank_lines_not_counted(self):
        rc, out, _ = run_cc(["-L", "2", "echo"], b"a\n\nb\n")
        self.assertEqual((rc, out), (0, "a b\n"))

    def test_L0_is_error(self):
        rc, _, _ = run_cc(["-L", "0", "echo"], b"a\n")
        self.assertEqual(rc, 1)


class TestEof(unittest.TestCase):
    def test_eof_stops(self):
        rc, out, _ = run_cc(["-E", "STOP", "echo"], b"a STOP b\n")
        self.assertEqual((rc, out), (0, "a\n"))

    def test_eof_exact_item_only(self):
        rc, out, _ = run_cc(["-E", "STOP", "echo"], b"a STOPPER b\n")
        self.assertEqual((rc, out), (0, "a STOPPER b\n"))

    def test_no_default_eof_string(self):
        rc, out, _ = run_cc(["echo"], b"_\nfoo\n")
        self.assertEqual((rc, out), (0, "_ foo\n"))

    def test_eof_ignored_in_null_mode(self):
        rc, out, _ = run_cc(["-0", "-E", "STOP", "echo"], b"a\x00STOP\x00b\x00")
        self.assertEqual((rc, out), (0, "a STOP b\n"))


class TestVerboseInteractive(unittest.TestCase):
    def test_verbose_traces_to_stderr(self):
        rc, out, err = run_cc(["-t", "echo"], b"a b\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "a b\n")
        self.assertIn("echo a b", err)

    def test_interactive_no_tty_skips(self):
        # No controlling terminal in the test harness: prompt is printed
        # and the invocation is skipped (documented fallback).
        rc, out, err = run_cc(["-p", "echo"], b"a\n")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("?..." , err)


class TestSize(unittest.TestCase):
    def test_s_splits_batches(self):
        rc, out, _ = run_cc(["-s", "4", "echo"], b"aa bb cc\n")
        self.assertEqual((rc, out), (0, "aa\nbb\ncc\n"))

    def test_s_single_oversized_item_errors(self):
        rc, _, err = run_cc(["-s", "2", "echo"], b"toolong\n")
        self.assertEqual(rc, 1)
        self.assertIn("argument line too long", err)

    def test_x_errors_on_forced_short_batch(self):
        rc, _, err = run_cc(["-x", "-n", "3", "-s", "4", "echo"],
                            b"aa bb cc\n")
        self.assertEqual(rc, 1)
        self.assertIn("argument line too long", err)


class TestQuoting(unittest.TestCase):
    def test_single_quotes(self):
        rc, out, _ = run_cc(["-n", "1", "echo"], b"'a b' c\n")
        self.assertEqual((rc, out), (0, "a b\nc\n"))

    def test_double_quotes(self):
        rc, out, _ = run_cc(["-n", "1", "echo"], b'"a b" c\n')
        self.assertEqual((rc, out), (0, "a b\nc\n"))

    def test_backslash_escape(self):
        rc, out, _ = run_cc(["-n", "1", "echo"], b"a\\ b c\n")
        self.assertEqual((rc, out), (0, "a b\nc\n"))

    def test_backslash_newline_continuation(self):
        rc, out, _ = run_cc(["echo"], b"a\\\nb\n")
        self.assertEqual((rc, out), (0, "ab\n"))

    def test_unmatched_single_quote_errors(self):
        rc, _, err = run_cc(["echo"], b"'abc\n")
        self.assertEqual(rc, 1)
        self.assertIn("unmatched", err)

    def test_unmatched_double_quote_errors(self):
        rc, _, err = run_cc(["echo"], b'"abc\n')
        self.assertEqual(rc, 1)
        self.assertIn("unmatched", err)

    def test_shell_metachars_are_data(self):
        rc, out, _ = run_cc(["echo"], b"$(echo HACKED) ; rm x\n")
        self.assertEqual((rc, out), (0, "$(echo HACKED) ; rm x\n"))


class TestExitCodes(unittest.TestCase):
    def test_child_exit_42_maps_to_123(self):
        rc, _, _ = run_cc(["-n", "1", "sh", "-c", "exit 42", "sh"], b"a\n")
        self.assertEqual(rc, 123)

    def test_child_exit_255_maps_to_124_and_aborts(self):
        rc, out, _ = run_cc(["-n", "1", "sh", "-c",
                             "echo ran; exit 255", "sh"], b"a b c\n")
        self.assertEqual(rc, 124)
        self.assertEqual(out, "ran\n")  # later invocations skipped

    def test_child_killed_by_signal_maps_to_125(self):
        rc, _, _ = run_cc(["-n", "1", "sh", "-c", "kill -TERM $$", "sh"],
                          b"a\n")
        self.assertEqual(rc, 125)

    def test_missing_utility_maps_to_127(self):
        rc, _, err = run_cc(["nonexistent-cmd-xyz-123"], b"a\n")
        self.assertEqual(rc, 127)
        self.assertIn("No such file", err)

    def test_mixed_failures(self):
        rc, _, _ = run_cc(["-n", "1", "sh", "-c",
                           "if [ \"$1\" = bad ]; then exit 3; fi", "sh"],
                          b"ok bad\n")
        self.assertEqual(rc, 123)


class TestHelpVersionErrors(unittest.TestCase):
    def test_help(self):
        rc, out, _ = run_cc(["--help"], b"")
        self.assertEqual(rc, 0)
        self.assertIn("usage", out)

    def test_version(self):
        rc, out, _ = run_cc(["--version"], b"")
        self.assertEqual(rc, 0)
        self.assertIn("ccxargs", out)

    def test_unknown_option(self):
        rc, _, err = run_cc(["--bogus", "echo"], b"a\n")
        self.assertEqual(rc, 1)
        self.assertIn("unknown option", err)

    def test_missing_option_value(self):
        rc, _, _ = run_cc(["-n"], b"a\n")
        self.assertEqual(rc, 1)


class TestOracle(unittest.TestCase):
    def test_oracle_basic(self):
        oracle(self, ["echo"], b"a b c\n")

    def test_oracle_n(self):
        oracle(self, ["-n", "2", "echo"], b"a b c d e\n")

    def test_oracle_replace(self):
        oracle(self, ["-I{}", "echo", "pre-{}-post"], b"a b\nc\n")

    def test_oracle_lines(self):
        oracle(self, ["-L", "2", "echo"], b"a\nb\nc\n")

    def test_oracle_r(self):
        oracle(self, ["-r", "echo", "X"], b"")

    def test_oracle_quoting(self):
        oracle(self, ["-n", "1", "echo"], b"a\\ b \"c d\" 'e f' g\n")

    def test_oracle_null(self):
        oracle(self, ["-0", "echo"], b"a b\x00c\x00")

    def test_oracle_eof(self):
        oracle(self, ["-E", "STOP", "echo"], b"a STOP b\n")

    def test_oracle_no_default_eof(self):
        oracle(self, ["echo"], b"_\nfoo\n")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for which.py. Controlled PATHs only — never the real PATH alone."""

import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from which import main  # noqa: E402

SYSTEM_WHICH = "/usr/bin/which"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_main(args, path=None, cwd=None):
    """Run main() in-process with a controlled PATH; return (code, out, err)."""
    environ = {"PATH": path} if path is not None else {}
    out, err = io.StringIO(), io.StringIO()
    old_cwd = os.getcwd()
    try:
        if cwd:
            os.chdir(cwd)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args, environ)
    finally:
        os.chdir(old_cwd)
    return code, out.getvalue(), err.getvalue()


def make_file(directory, name, mode=0o755, content="x"):
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    return path


class TestWhich(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d1 = os.path.join(self.tmp.name, "d1")
        self.d2 = os.path.join(self.tmp.name, "d2")
        os.mkdir(self.d1)
        os.mkdir(self.d2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_found_in_path_first_dir(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["prog"], path=self.d1)
        self.assertEqual((code, out), (0, self.d1 + "/prog\n"))

    def test_first_match_wins_without_a(self):
        make_file(self.d1, "prog")
        make_file(self.d2, "prog")
        code, out, _ = run_main(["prog"], path=self.d1 + ":" + self.d2)
        self.assertEqual((code, out), (0, self.d1 + "/prog\n"))

    def test_all_matches_with_a_in_path_order(self):
        make_file(self.d1, "prog")
        make_file(self.d2, "prog")
        code, out, _ = run_main(["-a", "prog"], path=self.d2 + ":" + self.d1)
        self.assertEqual((code, out), (0, self.d2 + "/prog\n" + self.d1 + "/prog\n"))

    def test_duplicate_dir_printed_twice_with_a(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["-a", "prog"], path=self.d1 + ":" + self.d1)
        self.assertEqual((code, out), (0, self.d1 + "/prog\n" + self.d1 + "/prog\n"))

    def test_non_executable_skipped(self):
        make_file(self.d1, "prog", mode=0o644)
        make_file(self.d2, "prog")
        code, out, _ = run_main(["prog"], path=self.d1 + ":" + self.d2)
        self.assertEqual((code, out), (0, self.d2 + "/prog\n"))

    def test_non_executable_only_is_not_found(self):
        make_file(self.d1, "prog", mode=0o644)
        code, out, _ = run_main(["prog"], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_directory_with_name_skipped(self):
        os.mkdir(os.path.join(self.d1, "prog"))
        make_file(self.d2, "prog")
        code, out, _ = run_main(["prog"], path=self.d1 + ":" + self.d2)
        self.assertEqual((code, out), (0, self.d2 + "/prog\n"))

    def test_not_found(self):
        code, out, _ = run_main(["nope"], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_mixed_found_and_missing(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["prog", "nope"], path=self.d1)
        self.assertEqual((code, out), (1, self.d1 + "/prog\n"))
        code, out, _ = run_main(["nope", "prog"], path=self.d1)
        self.assertEqual((code, out), (1, self.d1 + "/prog\n"))

    def test_multiple_programs_in_order(self):
        make_file(self.d1, "aaa")
        make_file(self.d2, "bbb")
        path = self.d1 + ":" + self.d2
        code, out, _ = run_main(["aaa", "bbb"], path=path)
        self.assertEqual((code, out), (0, self.d1 + "/aaa\n" + self.d2 + "/bbb\n"))

    def test_absolute_path_operand(self):
        target = make_file(self.d1, "prog")
        code, out, _ = run_main([target], path=self.d2)
        self.assertEqual((code, out), (0, target + "\n"))
        code, out, _ = run_main([os.path.join(self.d1, "missing")], path=self.d1)
        self.assertEqual((code, out), (1, ""))
        plain = make_file(self.d1, "plain", mode=0o644)
        code, out, _ = run_main([plain], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_relative_slash_operand(self):
        make_file(self.d1, "prog")
        make_file(self.d1, "plain", mode=0o644)
        os.mkdir(os.path.join(self.d1, "adir"))
        code, out, _ = run_main(["./prog"], path=self.d1, cwd=self.d1)
        self.assertEqual((code, out), (0, "./prog\n"))
        code, out, _ = run_main(["./plain"], path=self.d1, cwd=self.d1)
        self.assertEqual((code, out), (1, ""))
        code, out, _ = run_main(["./adir"], path=self.d1, cwd=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_empty_path_element_means_cwd(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["prog"], path=":" + self.d2, cwd=self.d1)
        self.assertEqual((code, out), (0, "./prog\n"))

    def test_path_unset(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["prog"], path=None, cwd=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_silent_flag(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["-s", "prog"], path=self.d1)
        self.assertEqual((code, out), (0, ""))
        code, out, _ = run_main(["-s", "nope"], path=self.d1)
        self.assertEqual((code, out), (1, ""))
        code, out, _ = run_main(["-as", "prog"], path=self.d1 + ":" + self.d1)
        # -s wins over -a for output; exit still 0
        self.assertEqual((code, out), (0, ""))

    def test_double_dash_ends_flag_parsing(self):
        code, out, _ = run_main(["--", "-a"], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_flag_after_operand_is_operand(self):
        make_file(self.d1, "prog")
        code, out, _ = run_main(["prog", "-a"], path=self.d1)
        self.assertEqual((code, out), (1, self.d1 + "/prog\n"))

    def test_unknown_option(self):
        code, out, err = run_main(["-x", "prog"], path=self.d1)
        self.assertEqual(code, 2)
        self.assertIn("[-as] args", out)
        self.assertEqual(err, "Illegal option -x\n")
        code, out, err = run_main(["-ax", "prog"], path=self.d1)
        self.assertEqual(code, 2)
        self.assertEqual(err, "Illegal option -x\n")

    def test_no_operands(self):
        code, out, _ = run_main([], path=self.d1)
        self.assertEqual((code, out), (1, ""))
        code, out, _ = run_main(["-a"], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_lone_dash_and_empty_operand(self):
        code, out, _ = run_main(["-"], path=self.d1)
        self.assertEqual((code, out), (1, ""))
        code, out, _ = run_main([""], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_symlinks(self):
        target = make_file(self.d1, "real")
        os.symlink(target, os.path.join(self.d1, "link"))
        code, out, _ = run_main(["link"], path=self.d1)
        self.assertEqual((code, out), (0, self.d1 + "/link\n"))
        os.symlink(os.path.join(self.d1, "missing"), os.path.join(self.d1, "dangling"))
        code, out, _ = run_main(["dangling"], path=self.d1)
        self.assertEqual((code, out), (1, ""))
        os.symlink(self.d2, os.path.join(self.d1, "dirlink"))
        code, out, _ = run_main(["dirlink"], path=self.d1)
        self.assertEqual((code, out), (1, ""))

    def test_matches_system_which_under_controlled_path(self):
        if not os.path.exists(SYSTEM_WHICH):
            self.skipTest("system which not installed")
        make_file(self.d1, "prog")
        make_file(self.d2, "prog")
        make_file(self.d1, "plain", mode=0o644)
        path = self.d1 + ":" + self.d2
        for args in (["prog"], ["-a", "prog"], ["nope"],
                     ["prog", "nope"], ["plain"], ["-s", "prog"]):
            env = {"PATH": path}
            sys_r = subprocess.run([SYSTEM_WHICH] + args, capture_output=True,
                                   text=True, env=env)
            code, out, _ = run_main(args, path=path)
            self.assertEqual(code, sys_r.returncode, args)
            self.assertEqual(out, sys_r.stdout, args)

    def test_subprocess_entry_point(self):
        make_file(self.d1, "prog")
        env = {"PATH": self.d1, "PYTHONPATH": HERE}
        r = subprocess.run([sys.executable, os.path.join(HERE, "which.py"), "prog"],
                           capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout), (0, self.d1 + "/prog\n"))
        r = subprocess.run([sys.executable, os.path.join(HERE, "which.py"), "nope"],
                           capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout), (1, ""))


if __name__ == "__main__":
    unittest.main()

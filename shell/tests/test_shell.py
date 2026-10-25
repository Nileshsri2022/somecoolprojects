"""Tests for shell.py (ccsh), driven non-interactively via pipes.

No interactive terminal is needed. Every run points CCSH_HISTORY_FILE
at a scratch file in a temp dir, so the real ~/.ccsh_history is never
touched. See docs/TEST_PLAN.md for the case list.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SHELL = Path(__file__).resolve().parent.parent / "shell.py"


def clean(out):
    """Strip prompts: piped input is not echoed, so a command's output
    lands on the same line as the prompt that preceded it."""
    return out.replace("ccsh> ", "")


def run_shell(input_text, cwd, history_file, extra_env=None):
    """Run the shell on input_text, return (stdout, stderr, returncode)."""
    env = dict(os.environ)
    env["CCSH_HISTORY_FILE"] = str(history_file)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(SHELL)],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )
    return proc.stdout, proc.stderr, proc.returncode


class TestShell(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.hist = self.dir / "hist.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def run_sh(self, input_text, extra_env=None):
        return run_shell(input_text, self.dir, self.hist, extra_env)

    def test_prompt_and_single_command(self):
        out, _, code = self.run_sh("echo hello\nexit\n")
        self.assertIn("ccsh> ", out)
        self.assertIn("hello", out)
        self.assertEqual(code, 0)

    def test_multiple_commands_loop(self):
        out, _, code = self.run_sh("echo one\necho two\nexit\n")
        self.assertIn("one", out)
        self.assertIn("two", out)
        self.assertGreaterEqual(out.count("ccsh> "), 3)
        self.assertEqual(code, 0)

    def test_exit_terminates_and_later_input_ignored(self):
        out, _, code = self.run_sh("exit\necho should-not-run\n")
        self.assertNotIn("should-not-run", out)
        self.assertEqual(code, 0)

    def test_eof_terminates(self):
        out, _, code = self.run_sh("echo hi\n")
        self.assertIn("hi", out)
        self.assertEqual(code, 0)

    def test_unknown_command_does_not_crash(self):
        out, err, code = self.run_sh("fubar-no-such-cmd-xyz\necho after\nexit\n")
        self.assertIn("No such file or directory", out + err)
        self.assertIn("after", out)
        self.assertEqual(code, 0)

    def test_command_with_arguments_and_cat_file(self):
        (self.dir / "data.txt").write_text("alpha\nbeta\n")
        out, _, code = self.run_sh("echo a b c\ncat data.txt\nexit\n")
        self.assertIn("a b c", out)
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        self.assertEqual(code, 0)

    def test_quoted_arguments(self):
        out, _, _ = self.run_sh('echo "hello world"\nexit\n')
        self.assertIn("hello world", out)

    def test_ls_lists_external_command_output(self):
        (self.dir / "known-file.txt").write_text("x\n")
        out, _, _ = self.run_sh("ls\nexit\n")
        self.assertIn("known-file.txt", out)

    def test_cd_and_pwd(self):
        sub = self.dir / "subdir"
        sub.mkdir()
        out, _, code = self.run_sh("pwd\ncd subdir\npwd\ncd ..\npwd\nexit\n")
        lines = [ln.strip() for ln in clean(out).splitlines()
                 if ln.strip().startswith(str(self.dir))]
        self.assertEqual(lines[0], str(self.dir))
        self.assertEqual(lines[1], str(sub))
        self.assertEqual(lines[2], str(self.dir))
        self.assertEqual(code, 0)

    def test_cd_no_arg_goes_home(self):
        home = self.dir / "fakehome"
        home.mkdir()
        out, _, _ = self.run_sh("cd\npwd\nexit\n",
                             extra_env={"HOME": str(home)})
        self.assertIn(str(home), out)

    def test_cd_nonexistent_does_not_crash_and_keeps_dir(self):
        out, err, code = self.run_sh(
            "cd no-such-dir-xyz\npwd\nexit\n")
        self.assertIn("No such file or directory", out + err)
        self.assertIn(str(self.dir), out)
        self.assertEqual(code, 0)

    def test_pipeline_two_stages(self):
        (self.dir / "lines.txt").write_text("one\ntwo\nthree\n")
        out, _, code = self.run_sh("cat lines.txt | wc -l\nexit\n")
        counts = [ln.strip() for ln in clean(out).splitlines() if ln.strip() == "3"]
        self.assertEqual(counts, ["3"])
        self.assertEqual(code, 0)

    def test_pipeline_three_stages(self):
        (self.dir / "lines.txt").write_text(
            "apple pie\nbanana split\napple tart\n")
        out, _, _ = self.run_sh("cat lines.txt | grep apple | wc -l\nexit\n")
        counts = [ln.strip() for ln in clean(out).splitlines() if ln.strip() == "2"]
        self.assertEqual(counts, ["2"])

    def test_pipeline_word_count(self):
        out, _, _ = self.run_sh("echo a b c | wc -w\nexit\n")
        counts = [ln.strip() for ln in clean(out).splitlines() if ln.strip() == "3"]
        self.assertEqual(counts, ["3"])

    def test_quoted_pipe_is_not_a_pipe(self):
        out, _, _ = self.run_sh('echo "a|b" | cat\nexit\n')
        self.assertIn("a|b", out)

    def test_empty_pipeline_segment_is_syntax_error(self):
        out, err, code = self.run_sh("ls |\necho after\nexit\n")
        self.assertIn("syntax error", out + err)
        self.assertIn("after", out)
        self.assertEqual(code, 0)

    def test_history_builtin(self):
        out, _, _ = self.run_sh("echo one\necho two\nhistory\nexit\n")
        self.assertIn("echo one\necho two", out)
        lines = out.splitlines()
        self.assertNotIn("history", lines)

    def test_history_persisted_and_reloaded(self):
        self.run_sh("echo one\necho two\nexit\n")
        self.assertTrue(self.hist.exists())
        saved = self.hist.read_text()
        self.assertIn("echo one", saved)
        self.assertIn("echo two", saved)
        out, _, _ = self.run_sh("history\nexit\n")
        self.assertIn("echo one", out)
        self.assertIn("echo two", out)

    def test_empty_lines_ignored(self):
        out, _, code = self.run_sh("\n\necho hi\n\nexit\n")
        self.assertIn("hi", out)
        self.assertEqual(code, 0)

    def test_sigint_does_not_kill_shell(self):
        env = dict(os.environ)
        env["CCSH_HISTORY_FILE"] = str(self.hist)
        proc = subprocess.Popen(
            [sys.executable, str(SHELL)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=str(self.dir), env=env)
        try:
            time.sleep(0.3)
            proc.send_signal(signal.SIGINT)
            time.sleep(0.3)
            self.assertIsNone(proc.poll(), "shell died on SIGINT")
            out, _ = proc.communicate("echo alive\nexit\n", timeout=10)
            self.assertIn("alive", out)
            self.assertEqual(proc.returncode, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()

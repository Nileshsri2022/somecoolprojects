"""Tests for the brainfuck interpreter — library API and CLI.

Run from the project directory:
    python3 -m unittest discover -s tests -v
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brainfuck import BrainfuckError, compile_program, run  # noqa: E402

HELLO_WORLD = ("++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]"
               ">>.>---.+++++++..+++.>>.<-.<.+++.------.--------.>>+.>++.")
HELLO_BANG = ("++++++++++[>+>+++>+++++++>++++++++++<<<<-]"
              ">>>++.>+.+++++++..+++.<<+++.")
PAGE_STEP2 = """This is a test Brainf*ck script written
for Coding Challenges!
++++++++++[>+>+++>+++++++>++++++++++<<<
<-]>>>++.>+.+++++++..+++.<<++++++++++++
++.------------.>-----.>.-----------.++
+++.+++++.-------.<<.>.>+.-------.+++++
++++++..-------.+++++++++.-------.--.++
++++++++++++. What does it do?"""

MAIN = Path(__file__).resolve().parent.parent / "brainfuck.py"


class TestPageAndClassicPrograms(unittest.TestCase):
    def test_page_step2_program(self):
        self.assertEqual(run(PAGE_STEP2), b"Hello, Coding Challenges")

    def test_page_hello_bang(self):
        self.assertEqual(run(HELLO_BANG), b"Hello!")

    def test_classic_hello_world(self):
        self.assertEqual(run(HELLO_WORLD), b"Hello World!\n")


class TestCommands(unittest.TestCase):
    def test_increment_output(self):
        self.assertEqual(run("+" * 65 + "."), b"A")

    def test_decrement(self):
        self.assertEqual(run("+" * 65 + "--."), b"?")  # 63 -> '?'

    def test_pointer_move(self):
        self.assertEqual(run("+>++>+++<<.>.>."), b"\x01\x02\x03")

    def test_cell_wraps_at_256(self):
        self.assertEqual(run("+" * 256 + "."), b"\x00")

    def test_cell_wraps_below_zero(self):
        self.assertEqual(run("-."), b"\xff")

    def test_loop_skipped_when_cell_zero(self):
        self.assertEqual(run("[.]"), b"")

    def test_loop_repeats_while_nonzero(self):
        self.assertEqual(run("++[>++<-]>."), b"\x04")  # 2 * 2

    def test_nested_loops(self):
        # 3 * (2 * 5) = 30, computed with a nested loop.
        self.assertEqual(run("+++[>++[>+++++<-]<-]>>."), b"\x1e")

    def test_comments_ignored(self):
        self.assertEqual(run("hello +++++ world +++++ . bye"), b"\n")
        self.assertEqual(run("no commands here"), b"")

    def test_input_reads_one_byte(self):
        self.assertEqual(run(",.", b"A"), b"A")

    def test_input_consumed_in_order(self):
        self.assertEqual(run(",.,.,.", b"abc"), b"abc")

    def test_eof_on_input_stores_zero(self):
        self.assertEqual(run(",."), b"\x00")

    def test_echo_loop_stops_at_eof(self):
        self.assertEqual(run(",[.,]", b"Hi!"), b"Hi!")


class TestErrors(unittest.TestCase):
    def test_unmatched_open_bracket(self):
        with self.assertRaises(BrainfuckError):
            run("[")

    def test_unmatched_close_bracket(self):
        with self.assertRaises(BrainfuckError):
            run("]")

    def test_unmatched_bracket_inside_program(self):
        with self.assertRaises(BrainfuckError):
            run("++[>++")

    def test_bracket_error_raised_before_output(self):
        # Compile runs before execution, so no partial output escapes
        # via the API (run raises instead of returning anything).
        with self.assertRaises(BrainfuckError):
            run("+." + "[")

    def test_pointer_before_start(self):
        with self.assertRaises(BrainfuckError):
            run("<")

    def test_pointer_past_end_of_tape(self):
        with self.assertRaises(BrainfuckError):
            run(">", tape_size=1)

    def test_small_tape_boundary(self):
        self.assertEqual(run(">" * 4 + "+" * 65 + ".", tape_size=5), b"A")
        with self.assertRaises(BrainfuckError):
            run(">" * 5, tape_size=5)

    def test_default_tape_is_30000(self):
        self.assertEqual(run(">" * 29999 + "+" * 65 + "."), b"A")


class TestCompilerOptimisations(unittest.TestCase):
    def test_run_collapsed(self):
        self.assertEqual(compile_program("+++"), [("ADD", 3)])
        self.assertEqual(compile_program(">>>"), [("RIGHT", 3)])
        self.assertEqual(compile_program("+++---"), [("ADD", 3), ("SUB", 3)])

    def test_clear_loop_compiled(self):
        self.assertEqual(compile_program("+++[-]"),
                         [("ADD", 3), ("CLEAR", 0)])
        self.assertEqual(compile_program("+++[+]"),
                         [("ADD", 3), ("CLEAR", 0)])

    def test_clear_loop_semantics(self):
        self.assertEqual(run("+++++[-]."), b"\x00")
        self.assertEqual(run("+++++[+]++."), b"\x02")

    def test_non_clear_loop_not_collapsed(self):
        # [-] with extra body is a real loop, not a CLEAR.
        prog = compile_program("++[->+<]")
        self.assertIn(("JUMP_IF_ZERO", 6), prog)
        self.assertEqual(run("++[->+<]>."), b"\x02")

    def test_jump_targets_resolved(self):
        prog = compile_program("[.]")
        self.assertEqual(prog, [("JUMP_IF_ZERO", 2), ("OUTPUT", 0),
                                ("JUMP_IF_NONZERO", 0)])


class TestCli(unittest.TestCase):
    def _run_cli(self, args, input_bytes=b""):
        return subprocess.run([sys.executable, str(MAIN), *args],
                              input=input_bytes, capture_output=True)

    def test_file_program(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".bf",
                                         delete=False) as fh:
            fh.write(HELLO_BANG)
            name = fh.name
        result = self._run_cli([name])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"Hello!")

    def test_stdin_program(self):
        result = self._run_cli(["-"], input_bytes=HELLO_BANG.encode())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"Hello!")

    def test_unmatched_bracket_file_fails(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".bf",
                                         delete=False) as fh:
            fh.write("++[")
            name = fh.name
        result = self._run_cli([name])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"unmatched", result.stderr)

    def test_missing_file_fails(self):
        result = self._run_cli(["/nonexistent/nope.bf"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_tape_size_flag(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".bf",
                                         delete=False) as fh:
            fh.write(">>.")
            name = fh.name
        self.assertEqual(self._run_cli([name]).returncode, 0)
        self.assertNotEqual(
            self._run_cli(["--tape-size", "2", name]).returncode, 0)


if __name__ == "__main__":
    unittest.main()

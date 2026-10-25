"""Tests for forth.py, mapped to the challenge steps (docs/TEST_PLAN.md)."""

import io
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forth import ForthError, Interpreter, StopExecution, repl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(source):
    interp = Interpreter()
    interp.run(source)
    return interp


def out_of(source):
    return run(source).output_text()


class TestArithmetic(unittest.TestCase):
    def test_add_chain(self):
        self.assertEqual(run("1 2 2 + +").stack, [5])

    def test_sub_order(self):
        self.assertEqual(run("10 3 -").stack, [7])

    def test_mul_div_mod(self):
        self.assertEqual(run("6 7 *").stack, [42])
        self.assertEqual(run("10 3 /").stack, [3])
        self.assertEqual(run("10 3 mod").stack, [1])

    def test_negative_literals_and_truncation(self):
        self.assertEqual(run("-7 2 /").stack, [-3])   # not -4 (floor)
        self.assertEqual(run("-7 2 mod").stack, [-1])  # not 1 (floor)
        self.assertEqual(run("7 -2 /").stack, [-3])
        self.assertEqual(run("-5").stack, [-5])

    def test_div_by_zero(self):
        for src in ("1 0 /", "1 0 mod"):
            with self.assertRaises(ForthError, msg=src):
                run(src)

    def test_underflow(self):
        for src in ("+", "1 +", "drop", "dup", "swap", "1 swap"):
            with self.assertRaises(ForthError, msg=src):
                run(src)


class TestStackWords(unittest.TestCase):
    def test_dup_drop(self):
        self.assertEqual(run("5 dup").stack, [5, 5])
        self.assertEqual(run("5 6 drop").stack, [5])

    def test_swap_over_rot(self):
        self.assertEqual(run("1 2 swap").stack, [2, 1])
        self.assertEqual(run("1 2 over").stack, [1, 2, 1])
        self.assertEqual(run("1 2 3 rot").stack, [2, 3, 1])


class TestIOWords(unittest.TestCase):
    def test_dot(self):
        self.assertEqual(out_of("5 ."), "5 ")
        self.assertEqual(run("5 .").stack, [])

    def test_emit_cr(self):
        self.assertEqual(out_of("78 72 79 74 emit emit emit emit cr"), "JOHN\n")

    def test_print_string(self):
        self.assertEqual(out_of('." Hello, Coding Challenges" cr'),
                         "Hello, Coding Challenges\n")

    def test_print_string_no_space_after_marker(self):
        self.assertEqual(out_of('."Hi"'), "Hi")


class TestDefinitions(unittest.TestCase):
    def test_define_and_call(self):
        self.assertEqual(out_of(': say-hi ." Hi, John" cr ; say-hi'),
                         "Hi, John\n")

    def test_word_calling_word(self):
        interp = run(": double dup + ; : quadruple double double ; 3 quadruple .")
        self.assertEqual(interp.output_text(), "12 ")
        self.assertEqual(interp.stack, [])

    def test_redefinition_replaces(self):
        self.assertEqual(out_of(": x 1 ; : x 2 ; x ."), "2 ")

    def test_comments(self):
        self.assertEqual(run("( this is a comment ) 5").stack, [5])
        self.assertEqual(
            out_of(": hi ( says hi ) .\" Hi!\" cr ; hi"), "Hi!\n")

    def test_unknown_word(self):
        interp = run("say-bye 5 .")
        self.assertEqual(interp.output_text(), "say-bye ?\n5 ")
        self.assertEqual(interp.stack, [])

    def test_unterminated_definition(self):
        with self.assertRaises(ForthError):
            run(": foo 1 2 +")

    def test_redefine_builtin_rejected(self):
        with self.assertRaises(ForthError):
            run(": + 1 ;")

    def test_definition_inside_definition_rejected(self):
        with self.assertRaises(ForthError):
            run(": outer : inner 1 ; ;")


class TestConditionals(unittest.TestCase):
    def test_comparisons(self):
        cases = {
            "3 5 <": [-1], "5 3 <": [0],
            "5 3 >": [-1], "3 5 >": [0],
            "4 4 =": [-1], "4 5 =": [0],
            "4 5 <>": [-1], "4 4 <>": [0],
        }
        for src, expected in cases.items():
            with self.subTest(src=src):
                self.assertEqual(run(src).stack, expected)

    def test_logic(self):
        self.assertEqual(run("-1 -1 and").stack, [-1])
        self.assertEqual(run("-1 0 and").stack, [0])
        self.assertEqual(run("0 -1 or").stack, [-1])
        self.assertEqual(run("0 0 or").stack, [0])
        self.assertEqual(run("0 invert").stack, [-1])
        self.assertEqual(run("-1 invert").stack, [0])

    def test_if_then(self):
        self.assertEqual(out_of('-1 if ." yes" then'), "yes")
        self.assertEqual(out_of('0 if ." yes" then'), "")

    def test_if_else_then(self):
        self.assertEqual(out_of('5 3 = if ." Equal" else ." Not Equal" then'),
                         "Not Equal")
        self.assertEqual(out_of('3 3 = if ." Equal" else ." Not Equal" then'),
                         "Equal")

    def test_nested_if(self):
        src = ('1 0 = if ." a" else 2 2 = if ." b" else ." c" then then')
        self.assertEqual(out_of(src), "b")

    def test_page_buzz_example(self):
        src = ': buzz 5 mod 0 = if ." Buzz" then ; 5 buzz 6 buzz'
        self.assertEqual(out_of(src), "Buzz")


class TestLoops(unittest.TestCase):
    def test_do_loop_count_and_i(self):
        self.assertEqual(out_of("5 0 do i . loop"), "0 1 2 3 4 ")

    def test_page_loop5(self):
        self.assertEqual(
            out_of(': loop5 5 0 do ." Test" cr loop ; loop5'),
            "Test\n" * 5)

    def test_empty_loop(self):
        self.assertEqual(out_of("3 3 do i . loop"), "")
        self.assertEqual(out_of("0 5 do i . loop"), "")

    def test_nested_loops(self):
        src = "2 0 do 3 0 do i . loop .\" |\" loop"
        self.assertEqual(out_of(src), "0 1 2 |0 1 2 |")

    def test_loop_inside_definition(self):
        self.assertEqual(out_of(": count 3 0 do i . loop ; count"), "0 1 2 ")

    def test_i_outside_loop(self):
        with self.assertRaises(ForthError):
            run("i")

    def test_unterminated_do_and_stray_closers(self):
        for src in ("5 0 do i .", "then", "loop", "else", ";", "5 0 do"):
            with self.assertRaises(ForthError, msg=src):
                run(src)

    def test_unterminated_comment_and_string(self):
        for src in ("( oops", '." oops'):
            with self.assertRaises(ForthError, msg=src):
                run(src)


class TestStep7Programs(unittest.TestCase):
    def _example(self, name):
        with open(os.path.join(ROOT, "examples", name)) as handle:
            return handle.read()

    def test_fibonacci(self):
        interp = run(self._example("fib.forth"))
        numbers = interp.output_text().split()
        self.assertEqual(numbers,
                         ["0", "1", "1", "2", "3", "5", "8", "13", "21",
                          "34", "55"])

    def test_fizzbuzz(self):
        interp = run(self._example("fizzbuzz.forth"))
        lines = [ln.strip() for ln in interp.output_text().splitlines()
                 if ln.strip()]
        expected = []
        for n in range(1, 25):  # 25 1 do: limit exclusive, so 1..24
            if n % 15 == 0:
                expected.append("FizzBuzz")
            elif n % 3 == 0:
                expected.append("Fizz")
            elif n % 5 == 0:
                expected.append("Buzz")
            else:
                expected.append(str(n))
        self.assertEqual(lines, expected)

    def test_cli_file_mode(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "forth.py"),
             os.path.join(ROOT, "examples", "fizzbuzz.forth")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[2], "Fizz")
        self.assertEqual(lines[14], "FizzBuzz")

    def test_cli_error_exit_code(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); "
             "from forth import Interpreter, ForthError; "
             "Interpreter().run('1 0 /')" % ROOT],
            capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)


class TestRepl(unittest.TestCase):
    def _repl(self, text):
        interp = Interpreter()
        out = io.StringIO()
        repl(interp, io.StringIO(text), out)
        return interp, out.getvalue()

    def test_bye_terminates(self):
        interp, output = self._repl("1 2\nbye\n99\n")
        self.assertEqual(interp.stack, [1, 2])
        self.assertNotIn("99", output)

    def test_stack_shown_before_prompt(self):
        _, output = self._repl("5\nbye\n")
        self.assertIn("5 ok> ", output)
        self.assertTrue(output.startswith("ok> "))

    def test_error_does_not_kill_repl(self):
        interp, output = self._repl("1 0 /\n7\nbye\n")
        self.assertIn("error: division by zero", output)
        self.assertEqual(interp.stack, [7])

    def test_eof_terminates(self):
        interp, _ = self._repl("3 4 +\n")
        self.assertEqual(interp.stack, [7])

    def test_bye_as_word_stops_script(self):
        interp = Interpreter()
        with self.assertRaises(StopExecution):
            interp.run("1 bye 2")


if __name__ == "__main__":
    unittest.main()

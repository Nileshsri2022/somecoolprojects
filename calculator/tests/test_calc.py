"""Tests for calc.py: challenge steps 1-3, unary signs, errors, CLI."""

import math
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc import CalcError, evaluate, infix_to_postfix, tokenize  # noqa: E402

CALC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "calc.py")


def run_cli(*args):
    return subprocess.run([sys.executable, CALC, *args],
                          capture_output=True, text=True)


def postfix_str(expr):
    """Render postfix tokens the way the challenge page shows them."""
    out = []
    for tok in infix_to_postfix(tokenize(expr)):
        out.append(str(int(tok)) if isinstance(tok, float)
                   and tok == int(tok) else str(tok))
    return " ".join(out)


class TestStep1(unittest.TestCase):
    def test_simple_expressions(self):
        for expr, want in [("1 + 2", "3"), ("2 - 1", "1"),
                           ("2 * 3", "6"), ("3 / 2", "1.5")]:
            with self.subTest(expr=expr):
                self.assertEqual(evaluate(expr), want)

    def test_int_vs_float_formatting(self):
        self.assertEqual(evaluate("10 / (6 - 1)"), "2")
        self.assertEqual(evaluate("1 / 3"), "0.3333333333333333")
        self.assertEqual(evaluate("2.5 * 2"), "5")
        self.assertEqual(evaluate("0.5 + 0.5"), "1")


class TestStep2(unittest.TestCase):
    def test_precedence_and_parentheses(self):
        for expr, want in [("1 + 1 * 5", "6"), ("(1 + 1) * 5", "10"),
                           ("2 * 3 + 4", "10"), ("10 / (6 - 1)", "2"),
                           ("((2 + 3) * 4) - 1", "19"),
                           ("1 + 2 * 3 - 4 / 2", "5")]:
            with self.subTest(expr=expr):
                self.assertEqual(evaluate(expr), want)

    def test_postfix_conversion_matches_challenge_example(self):
        self.assertEqual(postfix_str("(1 * 2) - (3 * 4)"),
                         "1 2 * 3 4 * -")
        self.assertEqual(postfix_str("1 + 1 * 5"), "1 1 5 * +")

    def test_whitespace_insignificant(self):
        self.assertEqual(evaluate("2*3"), "6")
        self.assertEqual(evaluate("  2  *  3  "), "6")


class TestStep3Functions(unittest.TestCase):
    def test_exact_trig_values(self):
        for expr, want in [("sin(0)", "0"), ("cos(0)", "1"),
                           ("tan(0)", "0")]:
            with self.subTest(expr=expr):
                self.assertEqual(evaluate(expr), want)

    def test_approximate_trig_values(self):
        for expr, want in [("sin(1)", math.sin(1)),
                           ("cos(1)", math.cos(1)),
                           ("tan(1)", math.tan(1)),
                           ("sin(1 + 2)", math.sin(3)),
                           ("sin(cos(0))", math.sin(1)),
                           ("2 * sin(0) + cos(0)", 1.0)]:
            with self.subTest(expr=expr):
                self.assertAlmostEqual(float(evaluate(expr)), want)

    def test_function_names_case_insensitive(self):
        self.assertEqual(evaluate("SIN(0)"), "0")
        self.assertEqual(evaluate("Cos(0)"), "1")


class TestUnarySigns(unittest.TestCase):
    def test_unary_minus_and_plus(self):
        for expr, want in [("-3 + 5", "2"), ("2 * -3", "-6"),
                           ("-(1 + 2)", "-3"), ("2 - -3", "5"),
                           ("+3 + 2", "5"), ("2 * -(1 + 1)", "-4")]:
            with self.subTest(expr=expr):
                self.assertEqual(evaluate(expr), want)


class TestErrors(unittest.TestCase):
    def test_division_by_zero(self):
        for expr in ["1 / 0", "1 / (2 - 2)"]:
            with self.subTest(expr=expr), self.assertRaises(CalcError):
                evaluate(expr)

    def test_mismatched_parentheses(self):
        for expr in ["(1 + 2", "1 + 2)", "((1)", "sin(1"]:
            with self.subTest(expr=expr), self.assertRaises(CalcError):
                evaluate(expr)

    def test_unknown_function(self):
        for expr in ["foo(1)", "sqrt(4)"]:
            with self.subTest(expr=expr), self.assertRaises(CalcError):
                evaluate(expr)

    def test_invalid_input(self):
        for expr in ["", "   ", "2 +", "2 3", "* 2", "2 * * 3",
                     "1.2.3", "2 & 3", "()", "(1 + )", "sin()"]:
            with self.subTest(expr=expr), self.assertRaises(CalcError):
                evaluate(expr)


class TestCLI(unittest.TestCase):
    def test_challenge_examples(self):
        for expr, want in [("2 * 3", "6\n"), ("10 / (6 - 1)", "2\n"),
                           ("1 + 1 * 5", "6\n"), ("(1 + 1) * 5", "10\n")]:
            with self.subTest(expr=expr):
                proc = run_cli(expr)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, want)
                self.assertEqual(proc.stderr, "")

    def test_cli_errors_go_to_stderr_with_nonzero_exit(self):
        for expr in ["1 / 0", "(1 + 2", "foo(1)", "2 +"]:
            with self.subTest(expr=expr):
                proc = run_cli(expr)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertIn("calc:", proc.stderr)

    def test_cli_usage_errors(self):
        for args in [[], ["1 + 1", "2 + 2"]]:
            with self.subTest(args=args):
                proc = run_cli(*args)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, "")
                self.assertIn("usage:", proc.stderr)

    def test_no_eval_call_in_source(self):
        with open(CALC) as f:
            source = f.read()
        self.assertNotIn("eval(", source)


if __name__ == "__main__":
    unittest.main()

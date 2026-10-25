"""Tests for lisp.py — programmatic evaluation first, CLI/REPL second."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lisp import (LispError, Symbol, eval_str, format_value, parse,
                  parse_all, run_script, standard_env, tokenize)

PAGE_SCRIPT = """
(defun hello ()
  (format t "Hello Coding Challenge World~%"))
(defun doublen (n)
  (* n 2))
(defun fib (n)
  (if (< n 2)
      n
      (+ (fib (- n 1))
         (fib (- n 2)))))
(defun fact (n)
  (if (<= n 1)
    1
    (* n (fact (- n 1)))))
(hello)
(format t "The double of 5 is ~D~%" (doublen 5))
(format t "Factorial of 5 is ~D~%" (fact 5))
(format t "The 7th number of the Fibonacci sequence is ~D~%" (fib 7))
"""

PAGE_EXPECTED = (
    "Hello Coding Challenge World\n"
    "The double of 5 is 10\n"
    "Factorial of 5 is 120\n"
    "The 7th number of the Fibonacci sequence is 13\n"
)


def run(source, env=None):
    """eval_str on a fresh env unless one is supplied."""
    if env is None:
        env = standard_env()
    return eval_str(source, env)


def run_seq(*sources):
    env = standard_env()
    result = None
    for source in sources:
        result = eval_str(source, env)
    return result


class TestTokenizer(unittest.TestCase):
    def test_atoms(self):
        self.assertEqual(tokenize("1"), ["1"])
        self.assertEqual(tokenize('"Hello, Coding Challenges"'),
                         ['"Hello, Coding Challenges"'])
        self.assertEqual(tokenize(":CC"), [":CC"])
        self.assertEqual(tokenize("-3.5"), ["-3.5"])

    def test_format_sexpr(self):
        self.assertEqual(
            tokenize('(format t "Hello, Coding Challenge World World")'),
            ["(", "format", "t", '"Hello, Coding Challenge World World"',
             ")"])

    def test_defun(self):
        self.assertEqual(
            tokenize('(defun hello () "Hello, Coding Challenge World")'),
            ["(", "defun", "hello", "(", ")", '"Hello, Coding Challenge World"',
             ")"])

    def test_comments_and_quote(self):
        self.assertEqual(tokenize("(+ 1 2) ; trailing"), ["(", "+", "1", "2", ")"])
        self.assertEqual(tokenize("; only a comment"), [])
        self.assertEqual(tokenize("'(1 2)"), ["'", "(", "1", "2", ")"])

    def test_unterminated_string(self):
        with self.assertRaises(LispError):
            tokenize('"oops')


class TestParser(unittest.TestCase):
    def test_simple_and_nested(self):
        self.assertEqual(parse("(+ 1 2)"), [Symbol("+"), 1, 2])
        self.assertEqual(parse("(* (+ 1 2) 3)"),
                         [Symbol("*"), [Symbol("+"), 1, 2], 3])

    def test_defun_ast(self):
        self.assertEqual(
            parse("(defun doublen (n) (* n 2))"),
            [Symbol("DEFUN"), Symbol("DOUBLEN"), [Symbol("N")],
             [Symbol("*"), Symbol("N"), 2]])

    def test_page_fib_and_fact_parse(self):
        fib = parse("(defun fib (n) (if (< n 2) n "
                    "(+ (fib (- n 1)) (fib (- n 2)))))")
        self.assertEqual(fib[1], Symbol("FIB"))
        self.assertEqual(fib[3][0], Symbol("IF"))
        fact = parse("(defun fact (n) (if (<= n 1) 1 (* n (fact (- n 1)))))")
        self.assertEqual(fact[3][0], Symbol("IF"))

    def test_empty_list_quote_and_symbols(self):
        self.assertIsNone(parse("()"))
        self.assertEqual(parse("'x"), [Symbol("QUOTE"), Symbol("X")])
        self.assertEqual(parse(":cc"), Symbol(":CC"))
        self.assertIs(parse("t"), True)
        self.assertIsNone(parse("nil"))

    def test_errors(self):
        with self.assertRaises(LispError):
            parse("(+ 1 2")
        with self.assertRaises(LispError):
            parse("(+ 1 2))")
        with self.assertRaises(LispError):
            parse("(+ 1 2) (+ 3 4)")
        with self.assertRaises(LispError):
            parse("")


class TestEvaluationBasics(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(run("(+ 1 2)"), 3)
        self.assertEqual(run("(* 2 3)"), 6)
        self.assertEqual(run("(* (+ 1 2) (- 10 4))"), 18)
        self.assertEqual(run("(+ 1 2 3 4)"), 10)
        self.assertEqual(run("(- 5)"), -5)
        self.assertEqual(run("(- 10 1 2)"), 7)
        self.assertEqual(run("(/ 6 2)"), 3)
        self.assertEqual(run("(/ 5 2)"), 2.5)
        self.assertEqual(run("(mod 10 3)"), 1)

    def test_comparisons(self):
        self.assertIs(run("(< 1 2)"), True)
        self.assertIs(run("(>= 3 3)"), True)
        self.assertIs(run("(< 1 2 3)"), True)
        self.assertIs(run("(= 1 1)"), True)
        self.assertIs(run("(< 3 2)"), False)
        self.assertIs(run("(<= 2 1)"), False)

    def test_if(self):
        self.assertEqual(run("(if (< 1 2) 10 20)"), 10)
        self.assertEqual(run("(if (> 1 2) 10 20)"), 20)
        self.assertIsNone(run("(if nil 10)"))
        self.assertEqual(run("(if 0 10 20)"), 10)  # 0 is truthy in Lisp
        self.assertEqual(run("(if nil 10 20)"), 20)


class TestDefinitionsClosuresRecursion(unittest.TestCase):
    def test_define_and_defun_page_example(self):
        result = run_seq("(define x 10)", "x")
        self.assertEqual(result, 10)
        env = standard_env()
        self.assertEqual(eval_str("(defun doublen (n) (* 2 n))", env),
                         Symbol("DOUBLEN"))
        self.assertEqual(eval_str("(doublen 4)", env), 8)

    def test_define_function_sugar(self):
        result = run_seq("(define (triple n) (* 3 n))", "(triple 7)")
        self.assertEqual(result, 21)

    def test_lambda(self):
        self.assertEqual(run("((lambda (x) (* x 2)) 21)"), 42)

    def test_closure_captures_env(self):
        result = run_seq(
            "(define make-adder (lambda (n) (lambda (m) (+ n m))))",
            "(define add10 (make-adder 10))",
            "((make-adder 10) 5)",
        )
        self.assertEqual(result, 15)
        # The captured binding survives independently per closure.
        env = standard_env()
        eval_str("(define make-adder (lambda (n) (lambda (m) (+ n m))))", env)
        eval_str("(define add10 (make-adder 10))", env)
        eval_str("(define add100 (make-adder 100))", env)
        self.assertEqual(eval_str("(add10 1)", env), 11)
        self.assertEqual(eval_str("(add100 1)", env), 101)

    def test_let_and_let_star(self):
        self.assertEqual(run("(let ((x 1) (y 2)) (+ x y))"), 3)
        # Plain let: bindings see the outer env, not each other.
        result = run_seq("(define x 100)",
                         "(let ((x 1) (y x)) y)")
        self.assertEqual(result, 100)
        # let*: later bindings see earlier ones.
        self.assertEqual(run("(let* ((x 1) (y (+ x 1))) y)"), 2)
        # Shadowing does not leak out.
        self.assertEqual(run_seq("(define x 5)",
                                 "(let ((x 99)) x)", "x"), 5)

    def test_set_and_begin(self):
        result = run_seq("(define x 1)", "(set! x 2)", "x")
        self.assertEqual(result, 2)
        self.assertEqual(run("(begin 1 2 3)"), 3)

    def test_recursion_fact_and_fib(self):
        result = run_seq(
            "(defun fact (n) (if (<= n 1) 1 (* n (fact (- n 1)))))",
            "(fact 5)")
        self.assertEqual(result, 120)
        result = run_seq(
            "(defun fib (n) (if (< n 2) n "
            "(+ (fib (- n 1)) (fib (- n 2)))))",
            "(fib 7)")
        self.assertEqual(result, 13)
        env = standard_env()
        eval_str("(defun fib (n) (if (< n 2) n "
                 "(+ (fib (- n 1)) (fib (- n 2)))))", env)
        self.assertEqual(eval_str("(fib 10)", env), 55)


class TestQuoteAndLists(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(run("(quote (1 2 3))"), [1, 2, 3])
        self.assertEqual(run("'(1 2 3)"), [1, 2, 3])
        self.assertEqual(run("(quote x)"), Symbol("X"))
        self.assertIsNone(run("(quote ())"))

    def test_list_ops(self):
        self.assertEqual(run("(list 1 2 3)"), [1, 2, 3])
        self.assertIsNone(run("(list)"))
        self.assertEqual(run("(cons 1 '(2 3))"), [1, 2, 3])
        self.assertEqual(run("(cons 1 nil)"), [1])
        self.assertEqual(run("(car '(1 2 3))"), 1)
        self.assertEqual(run("(cdr '(1 2 3))"), [2, 3])
        self.assertIsNone(run("(cdr '(1))"))
        self.assertIsNone(run("(car nil)"))
        self.assertEqual(run("(append '(1 2) '(3) nil)"), [1, 2, 3])
        self.assertEqual(run("(length '(1 2 3))"), 3)
        self.assertEqual(run("(length nil)"), 0)
        self.assertIs(run("(null? nil)"), True)
        self.assertIs(run("(null? '(1))"), False)
        self.assertIs(run("(number? 3)"), True)
        self.assertIs(run("(string? \"a\")"), True)
        self.assertIs(run("(symbol? 'x)"), True)
        self.assertIs(run("(list? '(1))"), True)
        self.assertIs(run("(atom? 3)"), True)
        self.assertIs(run("(not nil)"), True)
        self.assertIs(run("(not 1)"), False)


class TestFormat(unittest.TestCase):
    def test_format_nil_returns_string(self):
        self.assertEqual(run('(format nil "The double of ~D is ~D~%" 5 10)'),
                         "The double of 5 is 10\n")
        self.assertEqual(run('(format nil "~A and ~S and ~~" \'hi "x")'),
                         "HI and \"x\" and ~")

    def test_format_t_prints_and_returns_nil(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = run('(format t "Hello ~A~%" "World")')
        self.assertIsNone(result)
        self.assertEqual(out.getvalue(), "Hello World\n")


class TestErrors(unittest.TestCase):
    def test_unbound_and_bad_calls(self):
        with self.assertRaises(LispError):
            run("nosuchvar")
        with self.assertRaises(LispError):
            run("(1 2)")
        with self.assertRaises(LispError):
            run("((lambda (x) x) 1 2)")
        with self.assertRaises(LispError):
            run("(car 5)")
        with self.assertRaises(LispError):
            run('(+ 1 "a")')
        with self.assertRaises(LispError):
            run("(/ 1 0)")
        with self.assertRaises(LispError):
            run("(set! never-defined 1)")
        with self.assertRaises(LispError):
            run('(format nil "~Q" 1)')
        with self.assertRaises(LispError):
            run('(format nil "~D")')
        with self.assertRaises(LispError):
            run("(let ((x)) x)")
        with self.assertRaises(LispError):
            run("(cons 1 2)")


class TestFormatValue(unittest.TestCase):
    def test_printing(self):
        self.assertEqual(format_value([1, Symbol("A"), "s"]), '(1 A "s")')
        self.assertEqual(format_value(None), "NIL")
        self.assertEqual(format_value(True), "T")
        self.assertEqual(format_value(Symbol("DOUBLEN")), "DOUBLEN")


class TestEndToEnd(unittest.TestCase):
    def test_page_script_programmatic(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_script(PAGE_SCRIPT)
        self.assertEqual(out.getvalue(), PAGE_EXPECTED)

    def test_page_script_via_cli_file(self):
        project = os.path.join(os.path.dirname(__file__), "..")
        with tempfile.NamedTemporaryFile("w", suffix=".lisp",
                                         delete=False) as handle:
            handle.write(PAGE_SCRIPT)
            path = handle.name
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(project, "lisp.py"), path],
                capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, PAGE_EXPECTED)

    def test_cli_file_error_exits_nonzero(self):
        project = os.path.join(os.path.dirname(__file__), "..")
        with tempfile.NamedTemporaryFile("w", suffix=".lisp",
                                         delete=False) as handle:
            handle.write("(nosuchvar)\n")
            path = handle.name
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(project, "lisp.py"), path],
                capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unbound", proc.stderr)

    def test_repl_page_session(self):
        project = os.path.join(os.path.dirname(__file__), "..")
        session = ("(+ 1 2)\n(* 2 3)\n(defun doublen (n) (* 2 n))\n"
                   "(doublen 4)\nquit\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(project, "lisp.py"), "--repl"],
            input=session, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cclisp> ", proc.stdout)
        # In piped mode prompts share a line with each result, so
        # check the page's results as an ordered subsequence.
        pos = 0
        for expected in ["3", "6", "DOUBLEN", "8"]:
            found = proc.stdout.find(expected, pos)
            self.assertNotEqual(found, -1, expected)
            pos = found + len(expected)

    def test_repl_multiline_and_error_recovery(self):
        project = os.path.join(os.path.dirname(__file__), "..")
        session = ("(+ 1\n 2)\n(nosuchvar)\n(+ 2 2)\nquit\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(project, "lisp.py"), "--repl"],
            input=session, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("3", proc.stdout)
        self.assertIn("Error: unbound symbol", proc.stdout)
        self.assertIn("4", proc.stdout)

    def test_stdin_script_mode(self):
        project = os.path.join(os.path.dirname(__file__), "..")
        proc = subprocess.run(
            [sys.executable, os.path.join(project, "lisp.py"), "-"],
            input='(format t "hi~%")\n(+ 1 2)\n',
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "hi\n")  # results not echoed


if __name__ == "__main__":
    unittest.main()

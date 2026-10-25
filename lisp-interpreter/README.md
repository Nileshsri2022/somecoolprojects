# lisp-interpreter — Build Your Own Lisp Interpreter

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A small Lisp interpreter in Python 3 standard library only:
tokenizer, S-expression parser, evaluator with lexical
environments and closures, a `cclisp>` REPL, and file/stdin
script execution. Implements the challenge page's steps
(tokenise, parse, evaluate with `if`/`defun`/`format` and
comparisons, REPL, file scripts) plus `define`, `lambda`,
`quote`, `let`/`let*`, and list operations.

## Usage

```sh
python3 lisp.py                 # REPL if stdin is a tty, else stdin script
python3 lisp.py --repl          # force the REPL (also when piped)
python3 lisp.py script.lisp     # run a file, print only side effects
python3 lisp.py -               # run stdin as a script
```

REPL session (the page's Step 4 example):

```
cclisp> (+ 1 2)
3
cclisp> (* 2 3)
6
cclisp> (defun doublen (n) (* 2 n))
DOUBLEN
cclisp> (doublen 4)
8
```

Symbols are case-insensitive and print uppercase (Common Lisp
convention, hence `DOUBLEN`); string contents are untouched.
`quit`, `exit`, `(quit)`, or EOF leaves the REPL.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests drive evaluation programmatically (`eval_str`,
`evaluate`, `parse`, `tokenize`) and cover nested expressions,
closures, recursion (`fib`/`fact` from the page), list ops,
`format`, every error case, the page's Step 5 script output,
and the REPL/CLI end to end.

## Files

- `lisp.py` — tokenizer, parser, evaluator, builtins, REPL, CLI.
- `docs/SPEC.md` — challenge spec and supported syntax.
- `docs/DESIGN.md` — pipeline, assumptions, and divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_lisp.py` — the test suite.

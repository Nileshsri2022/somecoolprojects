# lisp-interpreter — TEST_PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests are in `tests/test_lisp.py` (unittest, stdlib only).
Tests drive evaluation programmatically through `eval_str` /
`evaluate` / `parse` / `tokenize` — the REPL and file CLI tests
are extra, via subprocess, and never the only coverage.

## Tokenizer (Step 1, page examples)

- `1` -> `['1']`; `"Hello, Coding Challenges"` -> one string token.
- `:CC` -> `[':CC']`; `(format t "Hello, Coding Challenge World World")`
  -> `(`, `format`, `t`, string token, `)`.
- `(defun hello () "Hello, Coding Challenge World")` tokenises
  with `()` as an adjacent pair.
- Comments: `(+ 1 2) ; trailing` drops the comment; a full-line
  comment yields no tokens. `'(1 2)` yields a leading `'` token.
- Errors: unterminated string raises `LispError`.

## Parser (Step 2, page examples)

- `(+ 1 2)` -> `[Symbol(+), 1, 2]`; nested `(* (+ 1 2) 3)`.
- `(defun doublen (n) (* n 2))` -> defun symbol, `DOUBLEN`,
  param list, body list (symbols uppercased).
- Page `fib` and `fact` definitions parse without error and
  their ASTs contain the expected nested `IF` / call structure.
- `()` -> `None`; `'x` -> `[QUOTE, X]`; `parse` rejects trailing
  tokens and unbalanced input with `LispError`.

## Evaluation — basics (Step 3)

- `(+ 1 2)` -> `3`; `(* 2 3)` -> `6`; nested
  `(* (+ 1 2) (- 10 4))` -> `18`; variadic `(+ 1 2 3 4)` -> `10`;
  unary `(- 5)` -> `-5`; `(/ 6 2)` -> `3` (int), `(/ 5 2)` -> `2.5`.
- Comparisons: `(< 1 2)` true, `(>= 3 3)` true, chained
  `(< 1 2 3)` true, `(= 1 1)` true, `(< 3 2)` false.
- `if`: true branch, false branch, missing else -> nil, `0`
  is truthy, `nil` is falsy.

## Evaluation — definitions, closures, recursion

- `(define x 10)` then `x` -> `10`; `define` function sugar
  and `defun` both define callable functions returning the
  name symbol (`DOUBLEN` for the page example).
- `(doublen 4)` -> `8` after the page's `defun`.
- Closures: `((lambda (x) (* x 2)) 21)` -> `42`; a
  make-adder closure (`(define make-adder (lambda (n) (lambda
  (m) (+ n m))))`, `((make-adder 10) 5)` -> `15`) proves the
  captured env survives after the outer call returns.
- `let` shadowing: outer `x` unchanged after a `let` that
  shadows it; `let*` sees earlier bindings, plain `let` does
  not (binding evaluated in the outer env).
- Recursion: page `fact` -> `(fact 5)` = `120`;
  page `fib` -> `(fib 7)` = `13`, `(fib 10)` = `55`.
- `quote` / list ops: `(quote (1 2 3))` and `'(1 2 3)` equal
  `[1, 2, 3]`; `car`/`cdr`/`cons`/`list`/`append`/`length`/
  `null?` including the nil edge cases (`(car nil)` -> nil,
  `(cdr '(1))` -> nil, `(list)` -> nil).
- `format`: `(format nil "The double of ~D is ~D~%" 5 10)`
  returns the formatted string; `(format t "...~%")` writes
  to stdout and returns nil; `~~`, `~A`, `~S` covered.

## Errors (all raise LispError, never leak a traceback type)

- Unbound symbol, calling a number, wrong arg count for a
  user function, `car` of a number, `+` of a string, division
  by zero, `set!` of an unbound name, unknown `format`
  directive, malformed `let` bindings.

## End to end

- Page Step 5 script (hello / doublen / fib / fact, via
  `run_script` and via `python3 lisp.py file.lisp`) prints
  exactly the page's four lines, in order, nothing else.
- REPL via subprocess (`--repl`, piped input): prompts
  `cclisp> ` appear and the page Step 4 session yields
  `3`, `6`, `DOUBLEN`, `8` in order; `quit` exits cleanly.
- Stdin script mode (`python3 lisp.py -`): `format` output
  appears, result values are not echoed.

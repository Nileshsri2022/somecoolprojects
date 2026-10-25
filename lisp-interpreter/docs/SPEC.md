# lisp-interpreter — SPEC

Coding Challenges: Build Your Own Lisp Interpreter
(https://codingchallenges.fyi/challenges/challenge-lisp/)
— page slug used: `challenge-lisp` (first guess, no 404, no correction needed).

## What it is

A small Lisp interpreter in Python 3 standard library only:
tokenizer, S-expression parser, tree-walking evaluator with
lexically scoped environments, a `cclisp>` REPL, and file/stdin
script execution.

## Challenge steps (from the page)

- **Step 0 — setup:** Python 3, no dependencies.
- **Step 1 — tokenise:** atoms and S-expressions from a string.
  Page examples: `1` -> integer atom; `"Hello, Coding Challenges"`
  -> string atom; `:CC` -> symbol atom; `(format t "Hello, Coding
  Challenge World World")` -> a list of a symbol followed by a
  list; `(defun hello () "Hello, Coding Challenge World")`.
  Also supported here: `;` comments to end of line, and `'x`
  as sugar for `(quote x)`.
- **Step 2 — parse into an AST:** S-expressions become nested
  Python lists (the page's own representation, e.g. `(defun
  doublen (n) (* n 2))` -> `['defun', 'doublen', ['n'], ['*', 'n',
  2]]`, modulo the symbol type used here — see DESIGN.md).
  Page examples: `fib` and `fact` definitions (see TEST_PLAN.md).
- **Step 3 — evaluate:** symbol lookup in nested mappings,
  innermost first, then outwards to the global scope. Page asks
  for mathematical operators, `if`, `defun`, `format`, and
  comparison operators. Working examples from the page:
  `(+ 1 2)` -> `3`, `(* 2 3)` -> `6`, `(defun doublen (n) (* 2 n))`,
  `(doublen 4)` -> `8`.
- **Step 4 — REPL:** prompt `cclisp>`, read-evaluate-print.
  Page session: `(+ 1 2)` -> `3`, `(* 2 3)` -> `6`,
  `(defun doublen (n) (* 2 n))` -> `DOUBLEN`, `(doublen 4)` -> `8`.
- **Step 5 — script from file:** the page's example script
  (hello / doublen / fib / fact with `format`) must print
  exactly:
  ```
  Hello Coding Challenge World
  The double of 5 is 10
  Factorial of 5 is 120
  The 7th number of the Fibonacci sequence is 13
  ```

## Supported syntax

- Atoms: integers (`42`, `-3`), floats (`3.5`), strings
  (`"..."`, escapes `\"`, `\\`, `\n`, `\t`), symbols
  (`doublen`, `+`, `<`, `:CC`), `t` (true), `nil` / `()` (false/nil).
- S-expressions: `(head arg ...)` in prefix notation, nestable.
- Special forms: `quote` (and `'x`), `if`, `define`, `defun`,
  `lambda`, `let`, `let*`, `set!`, `begin`.
- Builtins — arithmetic: `+ - * / mod`
  (`+`/`*` variadic, `-` unary or variadic, `/` true division,
  integral results printed as integers); comparison: `= < > <= >=`
  (chained, e.g. `(< 1 2 3)`); list ops: `list cons car cdr
  append length null? null`; predicates: `number? string?
  symbol? list? atom?`; `not`; output: `format` (see below).
- `format`: `(format t "fmt~%" args...)` prints to stdout and
  returns `nil`; `(format nil "fmt" args...)` returns the
  formatted string instead. Directives: `~%` newline, `~D`
  decimal, `~A` aesthetic (strings raw, others as printed),
  `~S` as printed (strings quoted), `~~` a literal `~`.
  Unknown directives, or a directive with no argument, are errors.

## Usage

```sh
python3 lisp.py                 # REPL if stdin is a tty, else stdin script
python3 lisp.py --repl          # force the REPL (also when piped)
python3 lisp.py script.lisp     # run a file, print only side effects
python3 lisp.py -               # run stdin as a script
```

REPL details: prompt `cclisp> `, continuation prompt `...> `
while parentheses are unbalanced or a string is unterminated.
Type `quit`, `exit`, `(quit)`, or EOF to leave. In the REPL every
form's result is printed; in file/stdin-script mode results are
discarded and only `format` output appears. REPL errors are
printed as `Error: ...` on stdout and the loop continues; file
errors go to stderr with a non-zero exit code.

## Errors

Unbound symbol, calling a non-function, wrong argument count or
type, division by zero, `car`/`cdr` of a non-list, unbalanced
parentheses, unterminated string, and unknown `format`
directives all raise `LispError`. Nothing is silently misread:
an unknown token or a malformed form is an error, not a guess.

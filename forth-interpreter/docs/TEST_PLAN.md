# TEST_PLAN — Forth interpreter

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests drive evaluation programmatically through `Interpreter.run()`
(plus one subprocess CLI test and REPL tests over `StringIO`
streams) — no manual REPL checking.

## Coverage, mapped to the page's steps

- Step 2 arithmetic: `+ - * / mod`, operand order (`10 3 -` = 7,
  `10 3 /` = 3, `10 3 mod` = 1), negative literals, truncated
  (not floored) division/modulo for negative operands.
- Step 3 stack words: `dup drop swap over rot`, each checked by
  final stack contents.
- Step 4 I/O: `.` (value + trailing space, popped), `emit`
  (character, popped), `cr` (newline), `."` string output,
  including a string inside a definition.
- Step 5 definitions: define-and-call, a word calling another
  word, redefinition replaces, comments `( ... )` ignored
  (standalone and inside a definition), unknown word prints
  `<word> ?` and continues, unterminated definition raises
  `ForthError`, redefining a builtin raises `ForthError`.
- Step 6 conditionals: `if/then` taken and skipped, `if/else/then`
  both branches, nested conditionals, all comparisons
  (`< > = <>`) and logic (`and or invert`) returning -1/0.
- Step 6 loops: `do/loop` iteration count and `i` values
  (`5 0 do i . loop` prints `0 1 2 3 4`), empty loop when
  `start >= limit`, nested loops with `i`, a loop inside a
  definition.
- Step 7 programs: the page's Fibonacci program (checked against
  `0 1 1 2 3 5 8 13 21 34 55`) and FizzBuzz program (checked for
  1..24: `Fizz` on multiples of 3, `Buzz` on multiples of 5,
  `FizzBuzz` on 15, the number otherwise) — run from `examples/`
  through the interpreter, plus a CLI subprocess test that runs
  `forth.py examples/fizzbuzz.forth` and checks its stdout.
- REPL: `bye` terminates, stack persists across lines, the prompt
  shows the stack, errors do not kill the REPL, EOF terminates.
- Errors: stack underflow, division/modulo by zero, unterminated
  comment / string / `if` / `do`, stray `then`/`loop`/`else`/`;`,
  unknown word is NOT an error (see above).

## Success criteria

All tests pass (`OK`), the Fibonacci and FizzBuzz example outputs
match the sequences above, and `python3 forth.py examples/*.forth`
exits 0 with no stderr output.

# calculator — SPEC

Coding Challenges #7: Build Your Own Calculator
(https://codingchallenges.fyi/challenges/challenge-calculator/)

## What it is

A command-line calculator: one quoted expression in, one result out.

```sh
python3 calc.py '2 * 3'
6
python3 calc.py '10 / (6 - 1)'
2
```

## Challenge steps (from the page)

- **Step 1 — simple expressions:** `1 + 2`, `2 - 1`, `2 * 3`,
  `3 / 2`. Integers vs floats matter, and invalid input must
  be handled. Quote the expression so the shell does not expand `*`.
- **Step 2 — precedence and parentheses:** `1 + 1 * 5`,
  `(1 + 1) * 5`. The page's recommended approach is infix to
  postfix (reverse Polish notation) via the shunting-yard
  algorithm, then stack evaluation. Example: `(1 * 2) - (3 * 4)`
  becomes `1 2 * 3 4 * -`.
- **Step 3 — more complex expressions:** brackets for precedence
  plus functions `sin`, `cos`, `tan`, with automated tests.

## Supported syntax

- Binary operators: `+`, `-`, `*`, `/`, all left-associative.
  Precedence: `*` and `/` bind tighter than `+` and `-`.
- Parentheses `( )` for grouping, nestable.
- Functions: `sin`, `cos`, `tan` (radians, as in Python's
  `math` module), each taking exactly one parenthesised
  argument, e.g. `sin(0)`, `sin(1 + 2)`. Function names are
  matched case-insensitively (`SIN(0)` works).
- Unary `+`/`-`: a sign at the start of the expression, after
  another operator, or after `(` applies to what follows
  (`-3 + 5`, `2 * -3`, `-(1 + 2)`). This is not spelled out on
  the challenge page but is needed for expressions like
  `2 * -3` to be usable; it is a small, documented extension.
- Numbers: decimal integers and floats (`42`, `3.5`, `.5`,
  `5.`). No scientific notation, no other bases — not in the
  challenge, so not supported; `1e3` is rejected as invalid
  input rather than silently misread.

## Output formatting (int vs float)

All arithmetic is done in floating point internally. A result
is printed as an integer when it is mathematically integral
(`2 * 3` -> `6`, `10 / (6 - 1)` -> `2`), otherwise as the
shortest float repr (`3 / 2` -> `1.5`). No rounding is applied:
`1 / 3` prints `0.3333333333333333`.

## Errors

Any of these prints a message to stderr and exits non-zero,
printing nothing to stdout:

- invalid input (unknown characters, unknown function names,
  empty expression, missing operand, two numbers/operators in
  a row where the grammar forbids it),
- mismatched parentheses (unclosed `(` or stray `)`),
- division by zero.

The CLI takes exactly one argument (the expression). Zero or
more than one argument is a usage error, also stderr + non-zero
exit. `eval()` is never used: parsing is a hand-written
tokenizer + shunting yard + stack evaluator.

## Out of scope (deliberate)

No REPL, no stdin mode, no variables, no `^`/modulo/other
operators, no degrees mode for trig, no scientific notation.
The challenge asks for a CLI tool taking one expression; each
addition above would be speculation beyond it.

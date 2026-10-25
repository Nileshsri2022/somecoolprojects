# calculator — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Pipeline

```
expression string
  -> tokenize()           list of tokens
  -> infix_to_postfix()   shunting yard, list of tokens
  -> evaluate_postfix()   stack evaluation, float
  -> format_result()      int when integral, else float repr
```

One public entry, `evaluate(expr)`, runs the whole pipeline
and returns the formatted string. The CLI (`main`) only parses
argv and prints that string or the error.

## Tokens

A token is either a `float` (a number) or a `str` (an operator
`+ - * /`, a parenthesis `(` `)`, or a function name `sin`
`cos` `tan`). One flat representation keeps the shunting yard
and the evaluator trivial to read; there is no token class
because nothing in the pipeline needs one.

## Tokenizer

Single left-to-right scan, whitespace skipped:

- digits / `.` start a number: `\d+(\.\d*)?` or `\.\d+`.
  A second `.` (as in `1.2.3`) is not consumed into the number,
  so it surfaces later as two adjacent numbers — an error.
- letters start an identifier: `[A-Za-z]+`, lowercased; if it
  is not `sin`/`cos`/`tan` it is an unknown-function error
  immediately, not a mystery value later.
- anything else is an invalid-character error immediately.

Unary signs: a `+`/`-` is unary when it appears at the start,
after an operator, after `(`, or after another unary minus.
If the next thing is a number, the sign is folded into that
number (`2 * -3` tokens are `2 * -3.0`). If the next thing
is `(` or a function, `-` becomes a `neg` token, which the
shunting yard treats like a function (see below); a unary `+`
there is the identity, so nothing is emitted. The `neg`
token matters: rewriting `-(1 + 2)` as `0 - (1 + 2)` would
mis-evaluate `2 * -(1 + 1)` as `2 * 0 - (1 + 1) = -2`
instead of `-4`, because `*` would bind to the `0` first.

## Shunting yard

Standard algorithm, operator stack + output list:

- numbers go straight to output;
- a function is pushed onto the operator stack;
- `(` is pushed; on `)` operators are popped to output until
  `(`, which is discarded, and any function or `neg` tokens
  on top of the stack are then also popped to output (so
  `sin(1 + 2)` and `-(1 + 2)` work, including stacked cases
  like `2 * -sin(0)`);
- an operator pops higher-or-equal-precedence operators
  (all operators here are left-associative) before pushing
  itself;
- at end of input, remaining operators are popped to output.

Precedence: `*` `/` = 2, `+` `-` = 1. Errors: `)` with no
matching `(` (stack empties first), leftover `(` at end of
input. Both are mismatched-parentheses errors.

## Stack evaluation

Walk the postfix tokens: push numbers; on a binary operator
pop `b` then `a` and push `a op b` (division checks `b == 0`
first and raises division-by-zero); on a function pop one
value and push `math.sin`/`cos`/`tan` of it. At the end the
stack must hold exactly one value — anything else (empty
expression, missing operand, two adjacent numbers) is an
invalid-expression error. Popping from an empty stack is the
same error, not an `IndexError` leak.

## Errors

One exception type, `CalcError(ValueError)`, raised by every
stage with a human-readable message. The CLI catches it (and
only it, plus the usage error) and reports `calc: <message>`
to stderr with exit code 1. No tracebacks for bad input.

## Why not `eval()`

The challenge's whole point is parsing and the stack; `eval()`
would also execute arbitrary code. The hand-written pipeline
is ~120 lines and is the deliverable, not a shortcut around it.

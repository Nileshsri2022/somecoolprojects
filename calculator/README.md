# calculator — Build Your Own Calculator

Coding Challenges #7, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Evaluates one arithmetic expression: `+ - * /`, parentheses,
and `sin`/`cos`/`tan` (radians), with precedence handled by
infix-to-postfix conversion (shunting yard) and stack
evaluation. No `eval()`.

## Usage

```sh
python3 calc.py '2 * 3'
6
python3 calc.py '10 / (6 - 1)'
2
python3 calc.py '1 + 1 * 5'
6
python3 calc.py '(1 + 1) * 5'
10
python3 calc.py 'sin(0)'
0
```

Quote the expression so the shell does not expand `*`.
Integral results print as integers (`2 * 3` -> `6`),
otherwise as floats (`3 / 2` -> `1.5`). Errors (invalid
input, mismatched parentheses, division by zero, unknown
function) go to stderr with a non-zero exit code.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps (simple expressions,
precedence/parentheses/postfix, functions), unary signs,
and every error case above, at both library and CLI level.

## Files

- `calc.py` — tokenizer, shunting yard, stack evaluator, CLI.
- `docs/SPEC.md` — challenge spec and supported syntax.
- `docs/DESIGN.md` — pipeline and design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_calc.py` — the test suite.

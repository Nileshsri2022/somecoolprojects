# calculator — TEST_PLAN

Suite: `tests/test_calc.py`, standard `unittest`, run from
the project directory as:

```sh
python3 -m unittest discover -s tests -v
```

No third-party packages. CLI tests spawn `calc.py` as a
subprocess with `sys.executable` so the interpreter matches.

## Cases

### Step 1 — simple expressions (library + CLI)

- `1 + 2` -> `3`, `2 - 1` -> `1`, `2 * 3` -> `6`,
  `3 / 2` -> `1.5`.
- Int vs float formatting: integral results print without a
  decimal point (`2 * 3` -> `6`, `10 / (6 - 1)` -> `2`);
  non-integral results print as floats (`3 / 2` -> `1.5`,
  `1 / 3` -> `0.3333333333333333`).

### Step 2 — precedence, parentheses, postfix

- `1 + 1 * 5` -> `6` (not 10: `*` binds tighter).
- `(1 + 1) * 5` -> `10`, `2 * 3 + 4` -> `10`,
  `10 / (6 - 1)` -> `2`, `((2 + 3) * 4) - 1` -> `19`.
- Postfix conversion itself: `(1 * 2) - (3 * 4)` ->
  `1 2 * 3 4 * -` (the page's example), `1 + 1 * 5` ->
  `1 1 5 * +`.
- Whitespace is insignificant: `2*3`, `  2  *  3  ` both -> `6`.

### Step 3 — functions

- Exact: `sin(0)` -> `0`, `cos(0)` -> `1`, `tan(0)` -> `0`.
- Approximate (trig results are rarely exact floats):
  `sin(1)`, `cos(1)`, `tan(1)` vs `math.sin/cos/tan`, and
  `sin(1 + 2)` vs `math.sin(3)`, `sin(cos(0))` vs
  `math.sin(1)`.
- Case-insensitive names: `SIN(0)` -> `0`.

### Unary signs

- `-3 + 5` -> `2`, `2 * -3` -> `-6`, `-(1 + 2)` -> `-3`,
  `2 - -3` -> `5`.

### Errors (library raises CalcError; CLI exits non-zero with stderr, empty stdout)

- Division by zero: `1 / 0`, `1 / (2 - 2)`.
- Mismatched parentheses: `(1 + 2`, `1 + 2)`, `((1)`.
- Unknown function: `foo(1)`, `sqrt(4)`.
- Invalid input: empty string, whitespace only, `2 +`,
  `2 3`, `* 2`, `2 * * 3`, `1.2.3`, `2 & 3`, `()`.
- CLI usage: zero arguments and two arguments both fail.

### Safety guard

- The source of `calc.py` contains no `eval(` call
  (checked by reading the file, so `evaluate(...)` names do
  not trip it — the check is for the literal `eval(` token).

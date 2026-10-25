# lisp-interpreter — DESIGN

## Pipeline

```
source -> tokenize() -> parse() / parse_all() -> eval(expr, env)
```

1. **Tokenizer** (`tokenize`): scans the source character by
   character and returns a flat list of raw token strings:
   `(`, `)`, `'`, string tokens including their quotes, and
   bare atoms. `;` comments run to end of line and are dropped.
   No evaluation happens here.
2. **Parser** (`parse`, `parse_all`): consumes tokens into an
   AST. A parenthesised group becomes a Python list of its
   elements; `()` becomes `None` (nil). `'x` becomes
   `[Symbol('QUOTE'), x]`. Number tokens become `int`/`float`,
   string tokens become Python `str` (escapes processed),
   anything else becomes a `Symbol`.
3. **Evaluator** (`eval`, `evaluate`): walks the AST against an
   `Env` chain (see below). Self-evaluating values (numbers,
   strings, `True`, `None`) return themselves. A `Symbol` looks
   itself up. A non-empty list is a call: special forms are
   handled without evaluating all their parts; otherwise the
   operator and arguments are evaluated and the result applied.
4. **Printing** (`format_value`): the single Lisp representation
   used by the REPL and by `~S`: numbers as Python repr (but
   see the `/` note below), strings double-quoted with escapes,
   symbols by name, `True` -> `T`, `None` -> `NIL`,
   lists as `(a b c)`, functions as `#<FUNCTION name>` or
   `#<BUILTIN name>`.

## Assumptions (ponytail: stated, not hidden)

- **Symbols are case-insensitive and print uppercase.** The
  page's REPL session prints `(defun doublen ...)` as
  `DOUBLEN`, which is Common Lisp's upcasing convention, so
  symbols are normalised to upper case at parse time
  (`:cc` -> `:CC`, `doublen` -> `DOUBLEN`). String contents
  are never touched. This makes `doublen`, `DOUBLEN`, and
  `Doublen` the same binding, and is the one deliberate
  deviation from a case-preserving toy interpreter.
- **Lexical scope, closures capture their defining env.**
  `lambda` closes over the environment where it is created, so
  a function returned from another function keeps its captured
  bindings (tested by the make-adder test). `let` bindings are
  evaluated in the *outer* env (parallel, Scheme-style `let`);
  `let*` evaluates them sequentially in the growing env.
- **`nil` is both `()` and false.** Parser turns `()` into
  `None`; `nil` also parses to `None`; `t` parses to `True`.
  Only `None` and `False` are falsy for `if`/`not` — `0` and
  `""` are true, as in Lisp. Empty-list results (`(list)`,
  `(cdr '(1))`) are `None`, not a distinct empty list, so they
  print as `NIL`.
- **`cons` needs a list (or nil) as its second argument.**
  Dotted pairs (`(1 . 2)`) are not supported; `cons` with a
  non-list tail is a `LispError` rather than a silently
  invented pair type.
- **Division:** `/` is true division, but an integral result
  is returned as an `int` (`(/ 6 2)` -> `3`, `(/ 5 2)` -> `2.5`).
  This matches the page's integer-looking examples and the
  calculator project's int-when-integral convention.
- **No macros, no dotted pairs, no `cond`, no I/O beyond
  `format`.** The page asks for none of these; adding them
  would be speculative code. `format` covers the page's only
  output need. `define`/`lambda`/`let`/`quote`/`list` ops are
  included because the task brief for this entry names them
  alongside the page's `defun`/`if`/`format` — they are the
  minimal set that makes closures, recursion, and list code
  testable, not a general Scheme.

## Environments

`Env` is a dict plus a `parent` pointer. Lookup walks outward;
`define`/`defun` bind in the *current* env; `set!` rebinds in
the nearest env that already has the name and errors if there
is none (no accidental globals). Function bodies run in a new
child env of the closure's captured env, with parameters bound
there — so recursion works because the function's own name is
already bound in the captured (usually global) env.

## Special forms (arguments NOT all evaluated)

| Form | Behaviour |
|---|---|
| `(quote x)` / `'x` | returns `x` unevaluated |
| `(if c a [b])` | `a` if `c` truthy, else `b` or nil |
| `(define name expr)` | binds `expr`'s value in current env, returns the name symbol |
| `(define (f args) body...)` | sugar for defining a function, returns the name symbol |
| `(defun name (args) body...)` | page's form; same as the `define` sugar, returns the name symbol (hence `DOUBLEN`) |
| `(lambda (args) body...)` | returns a closure; calling it evaluates body in a child of the captured env, last body form is the value |
| `(let ((n v) ...) body...)` | parallel bindings, body in a child env |
| `(let* ((n v) ...) body...)` | sequential bindings |
| `(set! name expr)` | rebind nearest existing binding, returns the value |
| `(begin e...)` | evaluates in order, returns the last value (nil for empty) |

## Builtins (all arguments evaluated)

Arithmetic `+ - * / mod`; comparison `= < > <= >=`; lists
`list cons car cdr append length null? null`; predicates
`number? string? symbol? list? atom?`; `not`; `format`.
Builtins are plain Python callables wrapped with a name and an
arity/type check where a LispError beats a Python traceback:
e.g. `car` of a number, or `+` of a string, raises `LispError`
with a readable message, never a raw `TypeError`.

## REPL / script split

`repl()` owns prompts and result printing; `run_script()`
evaluates forms and discards results. Both share `eval` and
the same global env, so a definition typed in the REPL and one
read from a file behave identically. File mode exits 1 on the
first error; the REPL reports and continues.

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes fully.
- The page's Step 5 script prints exactly the page's four
  output lines (tested, not eyeballed).
- The page's Step 4 REPL session reproduces `3`, `6`,
  `DOUBLEN`, `8` in order.

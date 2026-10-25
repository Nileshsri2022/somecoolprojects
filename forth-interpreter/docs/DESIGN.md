# DESIGN — Forth interpreter

## Assumptions (stated before coding)

- Input is whitespace-separated tokens, as in every example on the
  page (`: say-hi ." Hi" cr ;`). `:` `;` `."` `(` are recognised
  only when separated by whitespace, except that `."` is recognised
  by the scanner wherever it appears at a token start, so
  `." hello"` and `."hello"` both work.
- Only integers exist. A token matching `-?[0-9]+` is a literal;
  a lone `-` is the subtraction word. No floats, no quoted numbers.
- Words are case-insensitive and stored lowercased; string literals
  are case-sensitive. Redefining a builtin word is an error (the
  page never asks for it, and silently shadowing `+` would be a
  debugging trap); redefining a user word replaces it.
- One data stack persists across REPL lines; definitions persist
  across lines too. A fresh `Interpreter` starts empty.
- Control flow is structured only: `if` must be closed by `then`,
  `do` by `loop`, and they nest. No `goto`, no computed jumps.

## Architecture (single file, stdlib only)

```
source text
  -> tokenize()      scanner: skips ( ... ) comments, captures
                     ." ..." string literals, splits the rest on
                     whitespace; yields Token(kind, value)
  -> Parser.parse()  turns the flat token list into a list of nodes
                     and records : definitions in a dict as it goes
  -> Interpreter executes nodes against a data stack + loop stack
```

Nodes are small tuples, e.g. `("push", 5)`, `("word", "+")`,
`("print-str", "Hi")`, `("if", then_nodes, else_nodes)`,
`("do", body_nodes)`, `("call", name)`. Parsing (not execution)
resolves matching `else`/`then`/`loop`, so nested and sequential
control structures need no jump patching and a mismatched closer
is a parse-time `ForthError` with a clear message.

Definitions are stored as parsed node lists, so a word defined
once is parsed once and can be called repeatedly, including
recursively (recursion works because execution looks the word up
in the dictionary at call time).

Execution is a simple recursive walk:

- `push`: append to the data stack.
- Builtin word: pop/push via small helpers; `need(n)` raises
  `ForthError("stack underflow")` instead of an `IndexError`.
- User word: execute its stored nodes (a fresh walk, same stacks).
- Unknown word: emit `"<word> ?\n"`-style output (word, space,
  `?`, newline) and continue.
- `if`: pop the flag; any non-zero value is true (so `-1` and any
  other non-zero value both work).
- `do`: pop `start`, then `limit`; push a `[index, limit]` frame;
  iterate `index` from `start` while `index < limit` (ascending
  only, per SPEC), executing the body each time with `index`
  incremented by 1; `i` reads the innermost frame's index.
  `loop` itself is not a runtime node — the parser consumed it.
- `bye`: raises `StopExecution`, caught by the REPL / file runner
  as a clean stop, not an error.

Output goes to a file-like object supplied to `Interpreter`
(default: an internal `io.StringIO` for tests; `sys.stdout` for
the CLI). This keeps the core testable without subprocesses while
the CLI test still exercises the real entry point.

## Why not a flat interpreter with jump tables

A flat token list plus precomputed jump targets is the classic
approach, but the recursive node walk is shorter, its parse errors
point at the unclosed construct directly, and it makes the test
surface (parse vs execute) obvious. Performance is irrelevant at
this scale (FizzBuzz / Fibonacci are tens of iterations).

## REPL rendering

Each iteration prints the stack bottom-to-top followed by `ok> `
(empty stack: just `ok> `), reads one line, and — when stdin is
not a tty — writes a newline first, simulating terminal echo so
piped sessions read like the page's transcripts. Errors print as
`error: ...` and the REPL continues with the stack as left.

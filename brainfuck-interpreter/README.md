# brainfuck-interpreter — Build Your Own Brainfuck Interpreter

Coding Challenges #55, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A Brainfuck interpreter in Python 3 (standard library only) that
compiles source to bytecode and runs it on a small VM: comments are
dropped at compile time, loop jump targets are resolved at compile
time, runs of `>`, `<`, `+`, `-` collapse into one instruction, and
the `[-]` / `[+]` clear-loop pattern compiles to a single `CLEAR`
instruction. All 8 commands, a 30,000-cell tape (customisable),
byte input/output, and errors for unmatched brackets and pointer
out-of-bounds.

## Usage

```sh
python3 brainfuck.py program.bf          # run a file
python3 brainfuck.py - < program.bf      # run a program from stdin
python3 brainfuck.py                     # REPL, prompt "CCBF> "
python3 brainfuck.py --tape-size 1000 program.bf
```

Program output is bytes on stdout; `,` reads bytes from stdin.
Errors go to stderr with a non-zero exit code.

Library use:

```python
from brainfuck import run
run("++++++++++[>+>+++>+++++++>++++++++++<<<<-]>>>++.>+.+++++++..+++.<<+++.")
# b"Hello!"
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the page's Step 2 program (`Hello, Coding Challenges`),
the page's `Hello!` program, classic Hello World, every command,
loops (including nested), comments, input/EOF behaviour, cell
wrap-around, tape boundaries, unmatched brackets, the compiler
optimisations, and the CLI (file, stdin, errors, `--tape-size`).

## Divergences from the challenge page

Documented in `docs/DESIGN.md`: cells wrap modulo 256, pointer
out-of-bounds is an error (no tape growth), EOF on `,` stores 0,
the REPL interprets lines rather than echoing them, and no
Mandelbrot program is bundled (fetch the one linked from the
challenge page and run it as a manual check — see
`docs/TEST_PLAN.md`).

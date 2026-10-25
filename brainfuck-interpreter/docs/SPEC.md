# Brainfuck Interpreter — SPEC

Source: Coding Challenges, "Build Your Own Brainfuck Interpreter",
https://www.codingchallenges.fyi/challenges/challenge-brainfuck
(slug: `challenge-brainfuck`; the guessed URL worked first try, no 404
correction was needed.)

## Challenge steps covered

- Step 0: environment setup (Python 3, standard library only).
- Step 1: a REPL (`CCBF>` prompt) and running a script file given as a
  command-line argument.
- Step 2: interpret Brainfuck and produce the program's output.
- Step 3: compile source to bytecode (comments dropped at compile time,
  loop jump targets resolved at compile time).
- Step 4: a small virtual machine (VM) runs the bytecode.
- Step 5: the compiler collapses runs of `>`, `<`, `+`, `-` into a single
  bytecode instruction with a count argument.
- Step 6: the compiler recognises the clear-loop patterns `[-]` and `[+]`
  and emits a single `CLEAR` bytecode instruction for them.

## Language

Eight commands; every other character is a comment and is ignored:

| Command | Meaning |
| --- | --- |
| `>` | Move the data pointer right |
| `<` | Move the data pointer left |
| `+` | Increment the cell at the pointer |
| `-` | Decrement the cell at the pointer |
| `.` | Output the byte in the cell at the pointer |
| `,` | Read one input byte into the cell at the pointer |
| `[` | If the cell at the pointer is 0, jump past the matching `]` |
| `]` | If the cell at the pointer is nonzero, jump back to the matching `[` |

Memory: an array of cells, 30,000 by default (customisable with
`--tape-size`), every cell initialised to zero.

## CLI

```sh
python3 brainfuck.py program.bf          # run a file
python3 brainfuck.py - < program.bf      # run a program from stdin
python3 brainfuck.py                     # REPL, prompt "CCBF> "
python3 brainfuck.py --tape-size 1000 program.bf
```

Program output is written as bytes to stdout. `,` reads bytes from
stdin. Errors (unmatched brackets, pointer out of bounds, missing file,
bad arguments) go to stderr and exit non-zero.

## Library API

```python
from brainfuck import run, compile_program, BrainfuckError

run("++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>.>---.+++++++..+++.")  # b"Hello World!\n"
run(",.", b"A")   # b"A" — input is bytes, output is bytes
```

`run(source, input_bytes=b"", tape_size=30000)` returns the output as
`bytes`. `compile_program(source)` returns the bytecode list and raises
`BrainfuckError` on unmatched brackets, so bracket errors are caught
before any execution happens.

## Success criteria

- The page's Step 2 test program and the page's `Hello!` program
  produce their expected output.
- Classic programs (Hello World, echo, cat-style copy loop, nested
  loops) run correctly through the library API, not only via the CLI.
- Unmatched `[` / `]` are rejected with an error, never silently run.
- Comments (any non-command character) are ignored.

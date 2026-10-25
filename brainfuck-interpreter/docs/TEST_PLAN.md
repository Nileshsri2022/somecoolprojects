# Brainfuck Interpreter — TEST PLAN

Run: `python3 -m unittest discover -s tests -v`
from the project directory.

## Library tests (`tests/test_brainfuck.py`)

- **Page programs.**
  - Page Step 2 test program (with its comment prose) produces its
    expected output. Its output is asserted exactly (the program
    prints a greeting — the test pins the real output string rather
    than assuming it).
  - Page `Hello!` program outputs `Hello!`.
  - Classic Hello World program outputs `Hello World!\n`.
- **Each command.**
  - `>` / `<` move the pointer; `+` / `-` change the current cell;
    `.` outputs the current cell as a byte; `,` reads one input byte.
  - Cell wrap: 256 `+`s output byte 0; `-` from 0 outputs byte 255.
- **Loops and bracket matching.**
  - Loop skipped when the cell is 0 (`[.]` with cell 0 outputs
    nothing); loop repeats while nonzero (multiplication loop).
  - Nested loops produce the correct result (Hello World relies on
    them; an explicit nested-loop arithmetic case is also covered).
  - Unmatched `[` raises `BrainfuckError`; unmatched `]` raises
    `BrainfuckError`; a bracket error is raised before any output
    is produced (compile step runs first).
  - Comments ignored: prose, whitespace and newlines interleaved
    with commands do not affect output.
- **Input/output.**
  - Echo program `,[.,]` echoes its input and stops at EOF.
  - EOF on `,` stores 0 (echo loop terminates; a bare `,.` with no
    input outputs byte 0).
  - Multiple input bytes are consumed in order.
- **Optimisations (must not change semantics).**
  - Run collapsing: `+++` behaves as three increments (covered
    implicitly everywhere; an explicit compiled-bytecode check
    asserts `+++` compiles to one `ADD 3` instruction).
  - Clear loop: `[-]` and `[+]` compile to `CLEAR` and zero the
    cell; `[-]` inside a larger program behaves like the loop.
- **Tape behaviour.**
  - Default tape is 30,000 cells (moving right 29,999 times is fine).
  - Moving left of cell 0 raises `BrainfuckError`.
  - Moving right past the last cell raises `BrainfuckError`.
  - A smaller `--tape-size`-equivalent (`tape_size=` argument)
    raises at its own boundary.
- **CLI tests (subprocess, same file).**
  - Running a `.bf` file prints the program's output.
  - A program from stdin (`-` argument) runs.
  - An unmatched-bracket file exits non-zero with an error on
    stderr and no program output on stdout.
  - A missing file exits non-zero.

## Manual checks (not automated)

- REPL: run `python3 brainfuck.py`, enter the `Hello!` program at
  the `CCBF>` prompt, confirm `Hello!` is printed; Ctrl-D exits.
- Mandelbrot: fetch the program linked from the challenge page and
  run it; expect a Mandelbrot rendering (slow in an unoptimised
  interpreter — the page quotes ~20–40 s for a naive one; this one
  has run-collapsing and clear-loop optimisations, so it should be
  faster, but no timing claim is made without measuring it).

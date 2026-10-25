# Brainfuck Interpreter — DESIGN

## Assumptions (stated before coding, per ponytail rules)

1. **Compile-then-run, not direct interpretation.** Steps 3–4 of the
   page ask for a compiler + VM, and that design also gives Step 2
   (bracket matching) for free: jump targets are resolved once at
   compile time instead of being searched on every loop iteration.
   The VM is a plain loop over a list of `(op, arg)` tuples — no
   separate class, no dispatch table machinery beyond one `if/elif`
   chain. Simplicity first.
2. **Bytecode ops.** `RIGHT n`, `LEFT n`, `ADD n`, `SUB n` (runs
   collapsed, Step 5), `OUTPUT`, `INPUT`, `JUMP_IF_ZERO target`,
   `JUMP_IF_NONZERO target`, `CLEAR` (Step 6: `[-]` / `[+]`).
   `ADD`/`SUB` are kept separate rather than signed `ADD` so the
   bytecode reads like the source; the cost is one extra branch.
3. **Cells wrap modulo 256.** The page does not specify overflow
   behaviour. Bytes are the only sane output unit for `.`, and the
   classic programs (Hello World etc.) rely on wrap-around, so cells
   are bytes in `[0, 255]` and `+`/`-` wrap.
4. **Fixed tape, hard error at the edges.** The page suggests 30,000
   cells (or customisable). Moving left of cell 0 or right of the last
   cell raises `BrainfuckError` instead of silently growing the tape:
   growing would hide pointer bugs and change the page's memory model.
   `--tape-size` covers programs that need more room.
5. **EOF on `,` stores 0.** The page does not specify EOF behaviour.
   0 (no change from an empty cell, and the common convention) is
   chosen over -1, which cannot be represented in a byte cell, and
   over leaving the cell unchanged, which would loop forever on
   naive echo programs at EOF.
6. **REPL interprets, not just echoes.** Step 1 asks the REPL to echo
   input; Step 2 supersedes echoing with interpreting. The REPL here
   interprets each entered line and writes its output, which is the
   useful behaviour once an interpreter exists. (Echo-only mode is
   not kept: it would be dead code serving no later step.)
7. **Input/output are bytes.** The library API takes `bytes` and
   returns `bytes`; the CLI reads stdin as bytes and writes stdout
   as bytes. This avoids locale/encoding surprises with `.` output
   above 127 and keeps `,`/` .` symmetric.
8. **Nothing speculative.** No JIT, no LLVM backend, no debugger,
   no profiling hooks — the page's "Going Further" section is
   explicitly out of scope. The Mandelbrot program is not bundled:
   it is a large third-party program, and the test suite covers the
   same loop behaviour with small programs; running it manually is
   noted in the README as a check the user can do.

## Structure

Single file, `brainfuck.py`, standard library only:

- `BrainfuckError(Exception)` — all interpreter errors.
- `compile_program(source)` — filter to commands, collapse runs,
  resolve jumps with a bracket stack, recognise clear loops.
  Raises `BrainfuckError` on an unmatched `]` (seen during the scan)
  or an unmatched `[` (left on the stack at the end).
- `execute(program, input_bytes, tape_size)` — the VM loop.
- `run(source, input_bytes=b"", tape_size=30000)` — compile + execute.
- `main(argv)` — argparse CLI: file argument, `-` for stdin,
  `--tape-size`, no-argument REPL.

## Divergences from the page (all deliberate, all documented here)

- Cell overflow wraps modulo 256 (page silent) — assumption 3.
- Pointer out of bounds is an error, not tape growth (page silent).
- EOF on `,` yields 0 (page silent).
- REPL interprets lines instead of echoing them (Step 1 superseded
  by Step 2 — assumption 6).
- No Mandelbrot program bundled (assumption 8).

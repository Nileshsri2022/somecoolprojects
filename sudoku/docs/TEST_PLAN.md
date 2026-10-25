# Sudoku — Test Plan

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

All tests are `unittest`, stdlib only, and run without a terminal
(no stdin/stdout interaction is tested; `parse_command` and
`format_board` cover the interactive layer's pure parts).

## Coverage map

- Board representation: empty board shape/zeros; parse round-trip
  (digits, `.` and `0` empties); parse errors (short/long string,
  illegal character).
- Move validation (Step 1/2): valid move; row duplicate, column
  duplicate, box duplicate each rejected; out-of-range value and
  coordinates rejected; occupied cell rejected.
- Board validation (Step 2): valid partial board; duplicate in a
  row / column / box each detected; empty board valid; solved
  board valid.
- Solver (Step 3): solves a known puzzle to its known solution;
  returns `None` for an unsolvable board; already-solved board
  returned unchanged; solution counting: 1 for a well-posed
  puzzle, 0 for unsolvable, >= 2 (capped at limit) for an
  under-constrained board.
- Generation (Step 4): generated puzzle has a unique solution,
  its solution matches the returned full board, givens are a
  subset of the solution, and an easy puzzle is strictly smaller
  than a full board. Only easy difficulty is generated in tests
  (speed; see DESIGN.md performance note).
- Fixed cells (Step 4): applying a move to / clearing a fixed
  cell is rejected and leaves the board unchanged; player cells
  can be set and cleared; move value 0 clears.
- Win detection (Step 5): solved board detected; incomplete and
  invalid boards not detected as solved.
- Rendering/input: `format_board` shows `.` for empty, digits for
  filled, and separator lines; `parse_command` accepts every
  command form and rejects malformed input (bad numbers,
  out-of-range coordinates, unknown command, wrong arity).
- CLI level: `--solve` prints the known solution for a known
  puzzle; `--solve` with an unsolvable/invalid puzzle exits
  non-zero; `--help` exits zero. CLI tests invoke `main()` via
  `runpy`/`subprocess` with argv only — no interactive loop is
  exercised (it needs stdin, so it is covered only by
  `parse_command`/`apply_move` unit tests).

## Success criteria

- Every test passes; zero failures/errors.
- `python3 sudoku.py --solve` on the documented example puzzle
  prints the documented solution.

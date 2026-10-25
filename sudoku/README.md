# sudoku — Build Your Own Sudoku

Coding Challenges #53, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Sudoku (no GUI): 9x9 board, row/column/box move
validation, a backtracking solver, unique-solution puzzle
generation, fixed givens, and win detection.

## Usage

```sh
python3 sudoku.py              # easy puzzle
python3 sudoku.py medium
python3 sudoku.py hard
python3 sudoku.py --solve '530070000600195000098000060800060003400803001700020006060000280000419005000080079'
# prints the solved board
```

Interactive commands (rows/cols are 1-based):

```
1 2 5     place 5 at row 1, column 2 (0 clears the cell)
clear 1 2
check     report solved / not solved
solve     fill the board with the solution
new medium
help
quit
```

Givens cannot be cleared or overwritten; player cells can be
set and cleared. Moves that would duplicate a digit in their
row, column, or 3x3 box are rejected.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps (grid/move entry, solution
validation, backtracking solver, unique-solution generation,
fixed-cell rules, win check) plus rendering, command parsing,
and the `--solve` CLI — all without a terminal.

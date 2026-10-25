# Sudoku — Specification

Source: "Build Your Own Sudoku", Coding Challenges
(https://codingchallenges.fyi/challenges/challenge-sudoku/),
slug `challenge-sudoku` (first guess, no 404, no correction needed).
Page steps implemented: Step 0 (language choice), Step 1 (grid +
enter/clear a digit), Step 2 (validate a solution), Step 3 (solver),
Step 4 (generate a starting puzzle + fixed-cell constraints),
Step 5 (check whether the player has succeeded). "Going Further"
items (Killer Sudoku, timer, printing, mobile app) are NOT built.

## Rules (from the page)

- 9x9 grid; each row, each column, and each of the nine 3x3 boxes
  must contain the digits 1-9 exactly once in a solved board.
- The player starts from a partially completed grid which, for a
  well-posed puzzle, has a single solution.
- The player wins by filling the grid so every square's value is
  unique to its row, column, and box.

## Behaviour

- Board: 9 rows x 9 columns of ints; `0` means empty.
- Digits allowed: 1-9 for entry (page Step 1 says "a digit from 0
  to 9"; 0 is treated as "clear", not as a placed value, and Step 4
  says the player "cannot enter any value except the digits 0 to 9"
  — entering 0 via a move clears the cell, matching the Step 1
  clear operation).
- Fixed (given) cells from the generated puzzle cannot be cleared
  and cannot be overwritten.
- Player-set cells can be set and cleared freely (subject to the
  digit range; a move that breaks row/column/box uniqueness is
  rejected with an error, not silently accepted).
- `check` reports solved (complete + valid) or not; it does not
  reveal the solution. `solve` fills the board with the solver's
  solution (a play aid, not part of the page's required steps,
  kept because the solver already exists).
- Puzzle generation: generate a solved board, then remove cells
  one at a time (random order) keeping a removal only if the
  resulting puzzle still has exactly one solution (verified with
  the Step 2/3 code, per Step 4). Stop at the difficulty's target
  number of givens, or earlier if every remaining removal would
  break uniqueness.
- Difficulties (target givens; actual givens may be higher if
  uniqueness blocks further removal): easy 40, medium 32, hard 28.

## CLI

```
python3 sudoku.py [difficulty]      # easy | medium | hard, default easy
python3 sudoku.py --solve '<81 chars>'   # solve a puzzle, print solution
python3 sudoku.py --help
```

Interactive commands (rows/cols are 1-based):

```
r c v   place digit v (1-9) at row r, column c; v = 0 clears the cell
clear r c
check   report solved / not solved
solve   fill the board with the solution
new [difficulty]   start a fresh puzzle
help
quit
```

Puzzle strings for `--solve` are 81 characters of digits, with
`0` or `.` for empty cells. Invalid input exits non-zero with a
message on stderr.

## Non-goals

- No GUI (terminal only, per task scope; the page suggests
  click-to-enter, which maps to typed coordinates here).
- No Killer Sudoku, timer, printing, persistence, or hints that
  reveal more than the `solve` command already does.

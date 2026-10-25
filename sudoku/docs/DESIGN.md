# Sudoku — Design

## Assumptions (stated before coding, per ponytail rules)

- Python 3 standard library only; single file `sudoku.py`.
- All game logic is pure, non-interactive functions operating on
  plain data, so unit tests run without a terminal. Only `main()`
  / the `play()` loop touch stdin/stdout.
- Board = `list[list[int]]`, 9x9, `0` = empty. Functions never
  mutate a caller's board unless their name says so (`solve_in_place`
  is the one mutating helper, used internally); public `solve()`
  returns a new board or `None`.
- Fixed cells are tracked as a separate 9x9 boolean grid
  (`fixed[r][c]`), derived from the generated puzzle (non-zero
  cells are fixed). This keeps the board representation trivial
  and makes the Step 4 constraint a one-line check.
- Coordinates: 0-based inside functions, 1-based in the CLI.
  The conversion lives only in the input-parsing layer.

## Functions

| Function | Purpose |
|---|---|
| `empty_board()` | Fresh 9x9 of zeros. |
| `parse_board(text)` / `board_to_string(board)` | 81-char round-trip (`0`/`.` = empty). Raises `ValueError` on bad length/characters. |
| `box_index(row, col)` | `(row // 3) * 3 + col // 3`. |
| `is_valid_move(board, row, col, value)` | True iff cell is in range, value 1-9, cell empty, and value absent from its row, column, and box (the cell itself excluded — it is empty, so no special-casing needed). |
| `is_valid_board(board)` | No duplicate non-zero in any row, column, or box. Partial boards can be valid. |
| `is_complete(board)` / `is_solved(board)` | Complete = no zeros; solved = complete and valid. |
| `find_empty(board)` | First empty cell (row-major) or `None`. |
| `solve(board)` | Backtracking solver (page Step 3's backtracking option; constraint propagation not built — one solver is enough). Returns solved copy or `None` if unsolvable. Tries candidates 1-9 in order, so output is deterministic. |
| `count_solutions(board, limit=2)` | Backtracking counter stopping at `limit`; the uniqueness test is `count == 1` with limit 2, which avoids enumerating every solution. |
| `generate_full_board(rng)` | Backtracking fill with candidates shuffled by `rng` — a random solved board. |
| `generate_puzzle(difficulty, seed=None)` | Full board, then removals in shuffled order, each kept only if `count_solutions == 1`; stops at target givens. Returns `(puzzle, solution)`. |
| `fixed_grid(puzzle)` | Boolean grid: True where the puzzle has a given. |
| `apply_move(board, fixed, row, col, value)` | Pure move: returns `(new_board, error_or_None)`. Rejects out-of-range coordinates, fixed cells, and invalid placements; value 0 clears a non-fixed cell. |
| `clear_cell(board, fixed, row, col)` | Pure clear; same fixed-cell rule. |
| `format_board(board, fixed=None)` | Text grid with `|`/`-` separators every 3 cells; `.` for empty; fixed cells shown plain, player cells shown plain too (no colour codes — keeps output testable and pipe-friendly). |
| `parse_command(line)` | Pure CLI parser: `('move', r, c, v)`, `('clear', r, c)`, `('check',)`, `('solve',)`, `('new', difficulty_or_None)`, `('help',)`, `('quit',)`; raises `ValueError` with a usable message on bad input. |

## Why backtracking, not constraint propagation

The page names both; backtracking is the smallest code that
solves and counts solutions, and counting (for generation) needs
a search anyway. Candidate ordering is plain 1-9 for `solve()`
(deterministic, testable) and shuffled for generation (variety).

## Performance note

Uniqueness-checked generation does one bounded solution count
per attempted removal (~50 attempts). Easy/medium puzzles
generate in a few seconds; hard (28 givens) can take longer
because late removals need deeper searches. Tests therefore
generate only easy puzzles and use fixed known puzzles for
solver/count tests, keeping the suite fast.

## Divergences from the page

- Terminal UI instead of click-to-enter (task scope: no GUI).
- `solve` command added as a play aid (not a page step).
- Move validation rejects rule-breaking placements immediately;
  the page only requires solution validation (Step 2/5), but
  immediate rejection is the standard reading of "each square
  must contain a value unique to its row, column, and box" and
  makes `check` meaningful.

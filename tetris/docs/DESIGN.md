# DESIGN — Tetris

## Assumptions (stated before coding)

- Python 3 standard library only: `curses` for the interactive UI,
  `random` for the bag, nothing else.
- All game rules live in pure, non-interactive code so unit tests
  run with no terminal: the curses layer only reads keys and draws
  strings produced by pure functions.
- Terminal size: the UI needs roughly 24 rows x 40 columns; if the
  terminal is smaller, curses still runs but the drawing may clip —
  this is accepted, not handled, to keep the code minimal.

## Module layout (single file `tetris.py`)

- `SHAPES`: each tetromino as a tuple of strings, one character
  per cell (`#` filled, `.` empty). The piece letter is its key.
- `rotate_cw(shape)` / `rotate_ccw(shape)`: matrix rotation with
  empty outer rows/columns stripped, so every piece rotates with
  the same code path. Four clockwise rotations return any piece to
  its original shape; the O piece is rotation-invariant.
- `cells_of(shape)`: shape -> list of (dx, dy) filled offsets.
- `Board` (list of lists, `WIDTH = 10`, `HEIGHT = 20`):
  `empty_board()`, `collides(board, shape, x, y)`,
  `lock_piece(board, shape, x, y, letter)`,
  `clear_lines(board)` -> (new board, rows cleared).
- `Piece`: kind, shape (current rotation), x, y; `rotated(dir)`.
- `Game`: owns board, current piece, bag queue, score, lines,
  level, state (`playing`, `paused`, `over`). Methods:
  `spawn()`, `move(dx)`, `rotate(dir)`, `soft_drop()`,
  `hard_drop()`, `tick()` (one gravity step; locks + spawns on
  landing), `level_for(lines)`, `gravity_interval(level)`,
  `score_for_lines(n, level)`. All are pure state transitions —
  no I/O, no curses, no `time` calls inside them (the UI owns
  timing with `gravity_interval`).
- Rendering: `render_text(game)` -> one string: bordered board
  with the falling piece overlaid, plus score / level / lines /
  next piece. The curses UI draws this string (with colour pairs
  when available, falling back to plain text). A `render_board`
  helper draws a bare board for tests.
- UI (`main`, curses only): welcome screen, help screen, game
  loop (non-blocking key reads, gravity via elapsed time),
  pause overlay, game-over screen with restart. `main()` is never
  executed on import, so tests can import the module freely.
- Determinism for tests: `Game` accepts an optional `pieces`
  iterable (fixed spawn order, bypassing the bag) and an optional
  `random.Random` instance, so tests never depend on chance.

## Scoring / level numbers (chosen, page only gives an example)

The page's example (10 / 30 / 50) shows multi-row clears beating
the sum of singles but gives no full table. The classic
Guideline-style table scaled to the page's spirit is used:
100 / 300 / 500 / 800 x level. Soft drop +1/cell and hard drop
+2/cell are the standard values. Level every 10 lines.

## Divergences from the page (deliberate, minimal)

1. Terminal UI instead of the page's click/Play-button UI: the
   task brief requires terminal-only, no GUI. Welcome/help screens
   are text screens with key presses instead of buttons.
2. No high scores: optional on the page ("you could even include
   some high scores"); skipped to keep the build minimal.
3. No wall kicks: a rotation that collides is simply rejected.
   The page never mentions wall kicks; full SRS kicks would be
   speculative complexity.
4. No hold piece: not in the page's steps; skipped.
5. Spawn fully inside the board (y = 0) rather than partially
   above it: there are no hidden rows, so game-over on spawn
   collision is exact and testable.
6. 7-bag randomiser instead of a uniform random pick per piece:
   still random, and it matches the page's "order is random"
   while avoiding long single-piece droughts.
7. Retro monochrome rendering option is not a separate mode:
   colour is used when the terminal supports it, plain block
   characters otherwise — same game either way.

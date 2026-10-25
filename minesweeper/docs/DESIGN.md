# minesweeper — DESIGN

## Assumptions (stated before coding, per ponytail rules)

1. Terminal only, no GUI. The page offers a GUI as one option, not
   a requirement; the task brief pins this to terminal.
2. Library coordinates are 0-based; CLI coordinates are 1-based.
   The conversion lives only in the CLI layer, so tests never deal
   with the off-by-one.
3. A win = all non-mine cells revealed. Flags are advisory only.
   Rationale: the page defines winning as opening all safe cells,
   and requiring correct flags would make a fully-revealed board
   with one misplaced flag a loss, which no classic implementation
   does.
4. Neighbour counts are computed on the fly from the mine set, never
   cached. This keeps mine relocation (safe first click) trivially
   correct — there is no count table to keep in sync.
5. Mines are placed with `random.Random(seed).sample`, not
   rejection sampling. Rejection sampling can loop arbitrarily long
   on near-full boards; `sample` is uniform, O(cells), and
   deterministic for a given seed, which is what tests need.

## Structure (one file, `minesweeper.py`)

- `Board` — small mutable state object: `rows`, `cols`, `mines`
  (frozenset of `(r, c)`), `revealed` (set), `flagged` (set),
  `status` (`'playing'`/`'won'`/`'lost'`). Kept mutable because a
  game board is inherently stateful; the functions around it are
  still pure in the sense that matters for tests: no I/O, no
  terminal, no global state, deterministic given a seed.
- `create_board(rows, cols, mine_count, seed=None, safe_cell=None)`
  — validates (`rows, cols >= 1`; `0 <= mine_count < rows*cols`,
  so at least one safe cell always exists; `safe_cell`, if given,
  must be in bounds) and places mines. `safe_cell` is excluded
  from placement, which shrinks the sample pool by one.
- `neighbours(board, r, c)` — the up-to-8 in-bounds neighbours.
- `neighbour_count(board, r, c)` — mines among neighbours;
  `None` if the cell itself is a mine (a count is meaningless there).
- `reveal(board, r, c)` — returns `'ignored'` for out-of-bounds,
  already-revealed, flagged, or post-game cells; `'mine'` when a
  mine is hit (status -> `'lost'`, all mines become visible via
  render); otherwise flood-reveals with an explicit stack (iterative
  BFS, no recursion — a large empty board must not hit Python's
  recursion limit) and returns `'ok'`, setting status to `'won'`
  when the last safe cell is revealed.
- `toggle_flag(board, r, c)` — toggles on hidden cells only;
  returns whether anything changed.
- `ensure_safe_first_click(board, cell)` — if `cell` holds a mine,
  moves it to the first mine-free cell in row-major scan order.
  Used by the CLI so the very first reveal can never lose; the
  library equivalent is `safe_cell` at creation time.
- `mines_remaining(board)` — `mine_count - len(flagged)`; may go
  negative if the player over-flags, matching classic counters.
- `render(board, reveal_mines=False)` — pure string. Column
  numbers across the top, row numbers down the side, one character
  per cell: `.` hidden, `F` flagged, `*` mine (only when
  `reveal_mines` or game over), digit for a revealed numbered cell,
  space for a revealed 0. Mines that were correctly flagged still
  show as `F` on loss (they were found); unflagged mines show `*`.
- CLI (`main`, `play_game`) — argument parsing, the input loop,
  elapsed-time measurement, and the play-again prompt. All I/O
  lives here; nothing in the logic functions reads stdin or writes
  stdout, so unit tests run without a terminal.

## What was deliberately NOT built

- No live ticking timer (page Step 1 shows one). A ticking display
  needs a thread/redraw loop; elapsed time at game end conveys the
  same information with far less code. Documented divergence.
- No league table / best scores (page "Going Further"). Needs
  persistent storage; out of minimum scope.
- No chord / double-click reveal (reveal all neighbours of a
  satisfied numbered cell). Not on the page; speculative.
- No curses UI. Plain `input()`/`print()` keeps the game runnable
  anywhere, including piped/non-TTY environments, and testable.

## Difficulties (classic sizes)

| name         | rows | cols | mines |
|--------------|------|------|-------|
| beginner     | 9    | 9    | 10    |
| intermediate | 16   | 16   | 40    |
| expert       | 16   | 30   | 99    |

Explicit `--rows/--cols/--mines` override `--difficulty`.

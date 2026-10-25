# minesweeper — SPEC

Coding Challenges: Build Your Own Minesweeper
(https://codingchallenges.fyi/challenges/challenge-minesweeper/)
Page slug used: `challenge-minesweeper` — first guess, no 404, no correction needed.

## What it is

A terminal-based Minesweeper game. Python 3 standard library only,
single main file `minesweeper.py`. No GUI (per task brief; the page
itself suggests PyGame/a frontend stack as options, but a text board
is an allowed reading of the steps and keeps the game fully testable
without a terminal).

## Challenge steps (from the page)

- **Step 1 — draw the grid for the initial game state.** The page's
  example shows a mines-remaining counter and an elapsed-time counter.
  Here: the header line shows mines remaining (total mines minus
  flags placed); elapsed time is printed at game end instead of a
  live ticking counter, because a live counter would need a
  background thread for no gameplay benefit (see DESIGN.md).
- **Step 2 — reveal the mine / safe state after a cell is chosen.**
  Revealing a cell shows its adjacent-mine count (0–8), or floods
  outwards through connected 0-count cells, stopping at numbered
  cells (classic flood reveal).
- **Step 3 — detect hitting a mine, reveal the mines not found, and
  offer to play again.** On loss, all mines are shown; the CLI asks
  whether to play again and restarts with a fresh board.
- **Step 4 — detect a win.** A win is when every non-mine cell has
  been revealed. Flagging all mines is not required to win (flagging
  is a marking aid, not the win condition) — this matches the page's
  wording "open all the cells that you can without triggering a mine".
- **Going Further — different size playing areas.** Supported via
  `--difficulty beginner|intermediate|expert` and explicit
  `--rows/--cols/--mines`. A league table / best scores is NOT built
  (speculative scope; see DESIGN.md).

## Rules implemented

- The board is a grid; mines are placed uniformly at random
  (`random.Random(seed).sample` over all cells, so every placement
  of `mine_count` distinct cells is equally likely).
- A revealed cell shows the number of mines among its (up to) 8
  neighbours; 0 renders as a blank.
- Hidden cells render as `.`, flagged cells as `F`, mines (only
  shown after game over, or in `render(..., reveal_mines=True)`)
  as `*`.
- Flagging toggles a flag on a hidden cell only; flagged cells
  cannot be revealed until unflagged.
- The first revealed cell is guaranteed safe: the CLI moves the
  mine off the first-revealed cell if it landed there
  (`ensure_safe_first_click`). Library callers can get the same
  guarantee up front with `create_board(..., safe_cell=(r, c))`.
- Out-of-bounds coordinates, actions on already-revealed cells,
  and any action after the game is over are ignored (no crash,
  no state change).

## Interface

Library (0-based coordinates, all pure / non-interactive — no
`input()` or `print()` inside game logic):

```python
board = create_board(rows, cols, mine_count, seed=42)
neighbour_count(board, r, c)   # int 0..8, or None for a mine cell
reveal(board, r, c)            # 'ok' | 'mine' | 'ignored'
toggle_flag(board, r, c)       # True if the flag state changed
board.status                   # 'playing' | 'won' | 'lost'
render(board)                  # str, text board
```

CLI (1-based coordinates, for humans):

```sh
python3 minesweeper.py                    # beginner: 9x9, 10 mines
python3 minesweeper.py --difficulty expert
python3 minesweeper.py --rows 5 --cols 5 --mines 3 --seed 7
```

In-game commands: `r <row> <col>` reveal, `f <row> <col>` flag/unflag,
`q` quit, `h` help.

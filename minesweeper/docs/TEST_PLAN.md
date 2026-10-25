# minesweeper — TEST_PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests are `unittest`, all run without a terminal: they exercise
only the library functions (`create_board`, `neighbour_count`,
`reveal`, `toggle_flag`, `ensure_safe_first_click`,
`mines_remaining`, `render`). The interactive CLI loop is not unit
tested (it needs stdin); its only logic — 1-based to 0-based
conversion — is a two-line subtraction covered by manual play.

## Cases (in `tests/test_minesweeper.py`)

- Creation: exact mine count; seeded boards are identical across
  calls and differ across seeds; `safe_cell` is never mined;
  invalid inputs raise `ValueError` (zero/negative dimensions,
  too many mines, mine count filling the board, out-of-bounds
  safe cell); zero mines is allowed.
- Neighbour counts: hand-built boards (mines placed by explicit
  set, not RNG) covering corners, edges, centre, and the
  mine-cell-returns-`None` case.
- Reveal: single numbered reveal; flood reveal through a 0 region
  stops at numbered cells and does not leak into mines or across
  the board; revealing a mine loses and reveals mines on render;
  revealing a flagged cell, an already-revealed cell, an
  out-of-bounds cell, or any cell after game over is ignored with
  no state change.
- Flags: toggle on/off; flagging a revealed cell is ignored;
  flagging out of bounds is ignored; flags block reveal until
  removed; mines-remaining counter tracks flags.
- Win: revealing the last safe cell wins (including via flood);
  a board with zero mines is won by flood-revealing everything;
  a win is not granted while any safe cell stays hidden, even if
  every mine is flagged.
- Safe first click: `ensure_safe_first_click` moves a mine off
  the clicked cell, preserves the total mine count, and is a no-op
  when the cell was already safe.
- Render: hidden/flagged/numbered/blank/mine characters; header
  row and mines-remaining line; losing render shows unflagged
  mines; winning render shows all safe cells.

## Manual checks (done once, not automated)

- `python3 minesweeper.py --rows 5 --cols 5 --mines 3 --seed 7`:
  play a full game to a win and to a loss; confirm the play-again
  prompt restarts with a fresh board and `q` quits cleanly.
- Invalid CLI input (`r x y`, `r 99 99`, unknown command) prints
  help/error text and does not crash or end the game.

# TEST_PLAN — Tetris

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No terminal, no curses, no network, no randomness dependency:
tests import `tetris` and drive `Game` / board functions directly.
Fixed piece sequences are injected via `Game(pieces=[...])`.

## Cases

- Shapes: all seven kinds exist; every shape's filled cells form
  exactly 4 blocks; rotating any shape 4x clockwise returns the
  original; O is invariant under rotation; I alternates
  horizontal/vertical; rotate_ccw undoes rotate_cw.
- Collision: piece at the left/right/bottom edges cannot move
  further out; a piece overlapping a locked cell collides; a piece
  in empty space does not.
- Movement: `move(-1)`/`move(1)` shift x only when the target is
  free and are rejected at walls / against locked cells;
  `move` never changes y or the board.
- Rotation: rotation rejected when it would collide or leave the
  board (piece unchanged); accepted rotation changes the shape.
- Gravity / locking: `tick()` moves the piece down one row;
  a piece resting on the floor locks on the next `tick()` and the
  next piece spawns; locked cells appear on the board.
- Line clears: one full row clears and rows above drop down;
  two simultaneous full rows both clear; a non-full row is kept;
  `clear_lines` returns the correct count; scoring awards
  100/300/500/800 x level for 1/2/3/4 rows.
- Scoring/levels: soft drop adds 1/cell, hard drop adds 2/cell;
  level is 1 at 0–9 lines, 2 at 10–19 lines; gravity interval
  shrinks as level rises and never drops below 0.05s.
- Hard drop: piece lands on the floor / on locked cells, locks,
  and awards 2 points per cell travelled.
- Bag: a bag sequence of 7 draws contains each piece exactly
  once (seeded `random.Random`); fixed `pieces=` order is honoured.
- Game over: spawning onto a board whose spawn area is filled
  sets state `over` and further moves/ticks change nothing.
- Restart: a fresh `Game` (the UI's restart path) starts with an
  empty board, score 0, lines 0, level 1, state `playing`.
- Rendering: `render_text` shows the border, the falling piece,
  and score/level/lines labels; rendering never mutates the game.

## Success criteria

- All tests pass (`OK`, zero failures/errors).
- `python3 tetris.py --help` prints usage/controls without
  starting curses.
- Interactive play is smoke-checked by reading the code path only
  (no automated curses test — curses cannot run headless here);
  the pure-logic coverage above is what the tests guarantee.

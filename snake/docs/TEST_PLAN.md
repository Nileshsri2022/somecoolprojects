# Snake — TEST PLAN

All tests live in `tests/test_snake.py`, use `unittest`, and run
without a terminal (no curses import is exercised by the tests
beyond importing the module, which only imports curses at top
level — the game logic itself never calls it).

Run:

```sh
python3 -m unittest discover -s tests -v
```

## Cases

### Construction / start state
- Default game is 20x20, snake length 4, head in the centre row,
  body trailing left of the head, direction right, alive, score 0.
- Food is inside the board and not on the snake.
- Custom size respected; too-small boards rejected (ValueError).

### Movement
- One step right moves head by (1, 0), length unchanged.
- Each direction (up/down/left/right) moves the head correctly.
- Direction reversal (right -> left) is ignored; a legal turn
  (right -> up) is applied on the next step.
- Two queued turns (right -> up -> left) are applied one per
  tick, and do not cause a self-reversal.
- Repeating the current direction in the queue is a no-op.
- `set_direction`/`step` after death are no-ops.

### Food / growth / scoring
- Moving onto food grows the snake by 1, adds 10 to the score,
  increments foods eaten, and spawns a new food not on the snake.
- Moving elsewhere keeps length and score unchanged.
- `spawn_food` never returns a snake cell; with a seeded RNG the
  result is reproducible; with exactly one free cell it returns
  that cell; with no free cell it returns None.
- Filling the board by eating the last food ends the game with
  `death="win"` and `food=None`.

### Collisions
- Stepping outside any of the four edges ends the game with
  `death="wall"` and `alive=False`.
- Stepping into the body ends the game with `death="self"`.
- Stepping into the tail cell that is vacated on a non-eating
  tick is safe; the same move while eating is a self-collision.
- A dead game does not move further on later `step()` calls.

### Speed
- `tick_interval(0)` is 0.150 s; it decreases with foods eaten
  and never drops below 0.060 s.

### Rendering
- `render()` returns height+2 bordered rows of width+2 chars.
- Head renders `O`, body `o`, food `*`, border `#`; the head
  position in the rendered grid matches the body head.
- Render output for a small known game matches exactly.

### CLI
- `--help` exits 0 and prints usage (subprocess-free: via the
  argument parser path used by `main_cli`, tested through
  `parse_args`); invalid width/height rejected.

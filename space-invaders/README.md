# space-invaders — Build Your Own Space Invaders

Coding Challenges entry 50, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Space Invaders (no GUI): move your ship along the bottom,
shoot the 5x11 invader formation before it lands, hide behind 4
destructible shield bases, and survive on 3 lives. Clearing the
formation starts a faster next level.

## Usage

```sh
python3 space_invaders.py [--width W] [--height H] [--tick-ms MS]
```

Defaults: 60x24 board, 80 ms per tick.

Controls: Left / `A` move left, Right / `D` move right, Space fires,
`Q` quits, `R` starts a new game after game over.

## Rules

- Formation: 5 rows x 11 invaders, moving as one group. At either
  screen edge it reverses direction and steps down one row, and it
  steps more often as invaders are destroyed and on later levels.
- Scoring by row: top two rows 30 points, middle two rows 20,
  bottom row 10.
- One player bullet in flight at a time. Invaders drop bombs (max 3
  in flight) from the bottom-most invader of a random column.
- Bullets and bombs both destroy shield cells they hit. A bomb
  hitting the player costs one life and recentres the ship.
- Game over when lives run out or any invader reaches the player's
  row. Clearing all invaders advances a level (score and lives kept).

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover formation movement and edge reversal, speed-up, player
movement/clamping, firing, bullet/bomb collisions with invaders,
shields and the player, level advance, invasion and lives game
over, rendering, and CLI validation — all on pure functions, with
no terminal needed.

## Files

- `space_invaders.py` — game logic (`new_game`, `move_formation`,
  `step`, `render`, …) + thin curses shell.
- `docs/SPEC.md` — challenge spec and rules.
- `docs/DESIGN.md` — design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_space_invaders.py` — the test suite.

## Divergences from the challenge page

- No mystery ship and no music/sound: both are listed on the page
  under "Going Further" as optional extras, not required steps.
- Speed-up is per invader destroyed (plus per level), not strictly
  per descent — the classic arcade behaviour, monotonic in the same
  direction as the page's "a little faster each time they step down".
- Player bullet count is capped at one in flight (classic rule);
  the page does not specify a cap.
- No sprite graphics files: glyphs are characters, since the
  terminal has no sprite support. The page allows custom graphics.

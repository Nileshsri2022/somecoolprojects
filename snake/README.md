# snake — Build Your Own Snake Game

Coding Challenges entry, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Snake (Python 3 standard library only, `curses` for the
interactive UI). Board 20 x 20 by default, snake starts 4 cells
long in the centre moving right, one food at a time, +10 points
per food, faster as you eat, game over on wall or self collision,
restart with `r`.

## Usage

```sh
python3 snake.py                 # play
python3 snake.py --width 30 --height 15
python3 snake.py --help
```

## Controls

| Key              | Action               |
| ---------------- | -------------------- |
| Arrow keys / WASD| Change direction     |
| `p`              | Pause / resume       |
| `q`              | Quit                 |
| `r`              | Restart (game over)  |

## Tests

```sh
python3 -m unittest discover -s tests -v
```

All game logic (movement, growth, food spawning, wall/self
collision, scoring, speed) is pure and covered by tests that run
without a terminal; only the thin curses UI in `snake.py` needs one.

## Files

- `snake.py` — pure game logic + curses UI + CLI.
- `docs/SPEC.md` — challenge spec and fixed rules.
- `docs/DESIGN.md` — design assumptions and divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_snake.py` — the test suite.

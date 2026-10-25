# asteroids — Build Your Own Asteroids

Coding Challenges: Build Your Own Asteroids
(https://codingchallenges.fyi/challenges/challenge-asteroids)

A terminal clone of the 1979 arcade game Asteroids, in Python 3
standard library only. Fly the ship, shoot asteroids (they split
into two faster pieces, up to three times), dodge the occasional
flying saucer, and survive — 3 lives, harder fields each level,
smaller targets worth more points.

Docs first, then code — see `docs/` (`SPEC.md`, `DESIGN.md`,
`TEST_PLAN.md`). All game logic is pure, non-interactive
functions in `asteroids.py`; the `curses` UI is a thin loop over
them, so the tests run with no terminal.

## Play

```sh
python3 asteroids.py
```

| Key | Action |
| --- | ------ |
| Left / `a` | Rotate left |
| Right / `d` | Rotate right |
| Up / `w` | Thrust |
| Space | Fire / start game |
| `q` | Quit |

Score (top of screen): large asteroid 20, medium 50, small 100,
saucer 200. The session high score is shown on the start and
game-over screens.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover ship rotation/thrust/inertia/wrap, bullets, asteroid
movement/splitting, all collisions, scoring, lives, level
advance, the saucer, rendering, and seeded determinism — all
without a terminal.

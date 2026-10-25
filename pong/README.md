# pong — Build Your Own Pong

Coding Challenges #36, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Pong (no GUI): you control the left paddle, a
beatable AI controls the right one. First to the winning
score wins.

## Usage

```sh
python3 pong.py [--winning-score N] [--width W] [--height H]
                [--paddle-height N]
```

Defaults: winning score 5, field 80x24, paddle height 4.

Controls: `W`/`S` or Up/Down move the left paddle,
`Q` quits, `R` starts a new game after a win.

## Rules

Ball serves from a random point on the centre line towards
a random player at a random angle (within 45 degrees of
horizontal). It bounces off the top/bottom walls, reverses
horizontal direction on a paddle hit (with the angle set
by where it struck the paddle), and scores for the
opponent when it passes a player's edge. After every
point the ball is re-served.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover serve, paddle movement/clamping, wall bounce,
paddle collision and hit angle, scoring, winning, the AI,
rendering, and CLI argument validation — all on pure
functions, with no terminal needed.

## Files

- `pong.py` — game logic (`new_game`, `serve`,
  `move_paddle`, `ai_move`, `step`, `render`) + thin
  curses shell.
- `docs/SPEC.md` — challenge spec and rules.
- `docs/DESIGN.md` — design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_pong.py` — the test suite.

## Divergences from the challenge page

- No key-configuration dialog and no colour-scheme
  options (page Step 2 suggests them as "go wild" extras);
  keys are fixed to `W`/`S` + arrows.
- Paddle hits set the ball's vertical angle from the hit
  offset (centre = flat, edges = up to 45 degrees);
  the page only requires a horizontal reversal.
- Network multiplayer (Going Further) is not built.
- Terminal/curses instead of a GUI: per this project's
  brief, all logic is pure and terminal-free so it is
  fully unit-testable.

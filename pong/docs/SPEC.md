# pong — SPEC

Source challenge: Build Your Own Pong, Coding Challenges
(https://codingchallenges.fyi/challenges/challenge-pong/),
page slug `challenge-pong`. The first-guess URL worked; no
404, no slug correction needed.

## Challenge steps, mapped to this build

- Step 0 — language/environment: Python 3 standard library
  only. Terminal only, no GUI (per this project's brief).
- Step 1 — draw the table: `render()` produces a text table:
  a score line on top, a dashed centre line, two paddles,
  one ball. No border is drawn, so the full width/height is
  playable field (see DESIGN.md).
- Step 2 — two paddles, user controls the left one: left
  paddle moves with `W`/`S` or Up/Down arrow keys in the
  curses game. Key configuration dialog / colour scheme from
  the page are NOT built (see divergences).
- Step 3 — ball rules, implemented exactly as the page states:
  1. At the start of play and after every point, the ball
     appears at a random point on the central line and moves
     towards a random player at a random angle from the
     horizontal.
  2. On hitting the top or bottom of the pitch it bounces
     (vertical direction reverses), horizontal direction
     unchanged.
  3. On reaching the left or right edge a point is scored
     against the player on that side and play restarts at (1).
  4. On hitting a player's paddle it changes horizontal
     direction.
- Step 4 — computer player: the right paddle is AI-controlled.
  It tracks the ball only while the ball moves towards it,
  at most one cell per tick, so it is beatable (see DESIGN.md).
- Step 5 — score and win: the score is shown at the top of
  the screen, the winning score is settable
  (`--winning-score`, default 5); when either player reaches
  it the winner is celebrated and the player is offered a
  new game (press `R` to restart, `Q` to quit).
- Going Further (network multiplayer) is NOT built.

## Rules as implemented

- Field: `width` columns x `height` rows, default 80x24.
  Coordinates are floats for the ball, ints for paddles.
  Ball `x` in `[0, width-1]`, `y` in `[0, height-1]`.
- Paddles: left at column 1, right at column `width - 2`,
  both `paddle_height` cells tall (default 4), top row `y`
  clamped to `[0, height - paddle_height]`.
- Ball speed: horizontal component is always `+1` or `-1`
  cell per tick; vertical component is in `[-1, 1]`.
  Serve angle is chosen uniformly in `[-45, +45]` degrees
  from horizontal, so `|vy| <= 1` always holds.
- Wall bounce: if the ball would leave the top (`y < 0`) or
  bottom (`y > height - 1`), it is clamped to the edge and
  `vy` reverses; `vx` is untouched.
- Paddle hit: when the ball's new column reaches a paddle's
  column while travelling towards it, and its row lies
  within the paddle's span, `vx` reverses and `vy` is set
  from the hit offset (see DESIGN.md). The ball is placed
  just outside the paddle so it cannot stick to it.
- Scoring: if the ball's new `x < 0`, the right player
  scores; if `x >= width`, the left player scores. The
  scorer's total increments, then the ball is re-served
  (unless the score wins the game, in which case the ball
  stops and `winner` is set).
- Win: first player to reach `winning_score` wins.
  `winning_score` must be >= 1.

## Interface

```
python3 pong.py [--winning-score N] [--width W] [--height H]
                [--paddle-height N]
```

Controls in the curses game: `W`/`S` or Up/Down move the
left paddle, `Q` quits, `R` restarts after a win. The game
runs at one tick per ~70 ms; the AI moves the right paddle
once per tick.

All game logic lives in pure functions in `pong.py`
(`new_game`, `serve`, `move_paddle`, `ai_move`, `step`,
`render`, `is_game_over`); none of them touches the
terminal, so the unit tests run without a terminal.

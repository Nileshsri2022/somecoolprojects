# Snake — SPEC

Source: Coding Challenges, "Build Your Own Snake Game",
https://codingchallenges.fyi/challenges/challenge-snake/
(slug `challenge-snake`, fetched 2026-10-25; first guess, no 404, no correction needed.)

## The game (from the page)

The player controls a snake moving around a playing grid at a fixed
speed. The goal is to eat food that appears at random locations on
the grid. For each item eaten the snake becomes longer and the player
scores points. The game ends when the snake hits the edge of the grid
or its own body.

## Steps mapped to this build

- Step 0 — Language/environment: Python 3, standard library only.
  Terminal UI via `curses`; no GUI, no PyGame (see DESIGN.md).
- Step 1 — Game grid and score display: a bordered grid plus a
  score line, rendered as text by the pure `render()` function and
  drawn by the curses UI.
- Step 2 — Snake drawn and moving: the snake starts in the centre,
  4 cells long (the page suggests trying four initially), moving
  right (shifted right on narrow boards so the body fits on-board).
  Each tick removes the tail cell and adds a new head cell
  (unless growing). The head renders differently from the body.
- Step 3 — Wall collision: hitting the grid edge ends the game,
  shows the score, and offers a new game (`r` restarts, resetting
  all state).
- Step 4 — Food: one food item at a random grid cell, never on the
  snake. Head/food collision lengthens the snake by one, adds to
  the score, removes that food and spawns a new one elsewhere.
- Step 5 — Self collision: the head hitting the snake's own body
  ends the game.
- Going Further — not built: multiplayer and a persistent
  high-scores table. Both are explicitly out of scope (see
  DESIGN.md); the game-over screen does show the final score.

## Rules fixed by this spec (page leaves them open)

- Board: 20 wide x 20 high by default; `--width`/`--height` override.
- Score: 10 points per food eaten (the page says "scores points"
  but gives no value).
- Speed: starts at one tick every 150 ms and gets 5 ms faster per
  food eaten, down to a floor of 60 ms. The page says "fixed speed"
  for a single game; speeding up as the snake grows is the usual
  Snake behaviour and is documented here as a deliberate choice.
- Direction changes that would reverse the snake (e.g. right -> left
  while moving right) are ignored; queued changes are applied one
  per tick so fast keypresses cannot cause an instant reversal.
- Moving into the cell the tail is vacating on the same tick is
  safe (the tail moves away) unless the snake is eating on that
  tick, in which case the tail stays and it is a self-collision.
  This is the standard reading of "remove the tail, add a head".
- A board completely filled by the snake has no free cell for food:
  `spawn_food` returns `None` and the game is won/over (see
  DESIGN.md). This is an edge case, not a page step.

## Controls (curses UI)

| Key              | Action               |
| ---------------- | -------------------- |
| Arrow keys / WASD| Change direction     |
| `p`              | Pause / resume       |
| `q`              | Quit                 |
| `r`              | Restart (game over)  |

## Usage

```sh
python3 snake.py                 # play
python3 snake.py --width 30 --height 15
python3 snake.py --help
```

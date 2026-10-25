# asteroids — SPEC

Coding Challenges: Build Your Own Asteroids
(https://codingchallenges.fyi/challenges/challenge-asteroids)

Page slug used: `challenge-asteroids` (first guess, no 404, no correction).

## What it is

A terminal clone of the 1979 arcade game Asteroids, in Python 3
standard library only. The ship flies in an asteroid field, shoots
asteroids, and the game gets harder as levels progress. Interactive
play uses `curses`; every piece of game logic is a pure,
non-interactive function in `asteroids.py` so the unit tests run
with no terminal at all.

```sh
python3 asteroids.py
```

## Challenge steps (from the page)

- **Step 1 — game screen:** a start screen with the title and a
  "press SPACE to start" prompt, then the play field.
- **Step 2 — start a game:** the ship starts in the middle of the
  screen and asteroids move across it. Anything leaving one edge
  "wraps" around and re-enters on the opposite edge.
- **Step 3 — control the ship:** rotate to change the direction it
  faces, thrust to accelerate in the facing direction. Once moving
  it keeps moving; speed decays slowly (damping) unless thrust is
  applied again. The ship wraps like the asteroids.
- **Step 4 — shoot and split:** bullets leave the front of the ship
  and travel in a straight line. A hit asteroid splits into two
  faster pieces; asteroids split three times in total (large ->
  medium -> small -> destroyed).
- **Step 5 — scores:** the smaller the target, the higher the
  score. Score, lives and level are shown at the top of the screen.
- **Going Further — high score:** the best score of the session is
  kept and shown on the start / game-over screens.

## Rules implemented (from the page intro, which the steps assume)

- The player starts with 3 lives. Colliding with an asteroid (or
  the flying saucer) loses one life; with no lives left the game
  is over. After losing a life the ship respawns in the centre
  with brief invulnerability.
- The game gets harder over time: each new level spawns one more
  large asteroid than the last (level 1 = 4).
- The occasional flying saucer drifts across the screen and can be
  shot for points; colliding with it loses a life like an asteroid.

## Controls (curses UI)

| Key | Action |
| --- | ------ |
| Left / `a` | Rotate left |
| Right / `d` | Rotate right |
| Up / `w` | Thrust |
| Space | Fire / start game |
| `q` | Quit |

## Scoring

| Target | Points |
| ------ | ------ |
| Large asteroid | 20 |
| Medium asteroid | 50 |
| Small asteroid | 100 |
| Saucer | 200 |

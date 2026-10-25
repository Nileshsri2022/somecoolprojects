# Space Invaders — SPEC

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-space-invaders/
Slug used: `challenge-space-invaders` — worked on the first try, no 404,
no correction needed.

## What the page requires

Space Invaders (1978): the player moves a ship horizontally across the
bottom of the screen and fires at aliens above. Bases sit between the
player and the aliens as cover.

- Step 0: pick a language/environment. Here: Python 3 standard library
  only, terminal UI via `curses`.
- Step 1: initial screen — top info bar (score, lives remaining),
  player, bases, and ground at the bottom.
- Step 2: display the aliens — the original had five rows of eleven,
  evenly spaced, moved in unison but individually removable on a hit.
- Step 3: movement — player moves left/right only, clamped to the
  screen edges. Aliens move left/right as a group, stepping down one
  row each time they touch a screen edge, and moving a little faster
  each time they step down.
- Step 4: shooting and collisions — aliens occasionally drop bombs
  that fall towards the player; the player shoots on a button press.
  Handle collisions between shots/bombs and aliens/bases/player,
  update the score and damage, and detect aliens reaching the bottom.
- Step 5: end game — display "Game Over" and offer a new game.
- Going Further (optional): mystery ship across the top, music that
  speeds up with the aliens.

## Rules implemented (see DESIGN.md for the exact numbers)

- 5 rows x 11 columns of invaders, moving as one formation.
- Formation steps down one row and reverses direction at either edge,
  and steps more often as invaders are destroyed and on later levels.
- Player: 3 lives, moves left/right only, one bullet in flight at a
  time. A hit on the player costs one life; at 0 lives the game ends.
- Scoring by row: top two rows 30 points, middle two rows 20, bottom
  row 10 (classic arcade values, applied to a 5-row formation).
- 4 destructible shield bases between player and invaders. Player
  bullets and invader bombs both destroy shield cells they hit.
- Clearing all invaders starts the next level: a fresh formation,
  faster, with score and lives carried over.
- Game over when lives run out or any invader reaches the player's
  row. After game over, `R` starts a new game.

## Controls (curses UI)

- Left / `A`: move left. Right / `D`: move right.
- Space: fire. `Q`: quit. `R`: new game after game over.

# Space Invaders — DESIGN

## Assumptions (stated before coding, per ponytail rules)

- Terminal only, no GUI and no pygame: `curses` is the thin shell
  around pure game logic, exactly as in the sibling pong/tetris builds.
- The board is a character grid, not pixels. One invader, one bullet,
  one bomb and one shield cell each occupy exactly one grid cell, so
  collision is exact cell equality — no bounding boxes, no radii.
- All game logic is pure functions on a `Game` dataclass and is fully
  testable without a terminal. The curses shell only reads keys,
  calls `step()`, and draws `render()`.

## Board and constants

- Default board: 60 wide x 24 high (overridable via CLI flags).
- Row 0 is the info bar (score/lives/level, drawn by the UI, not
  stored in the grid); the playfield runs rows 1..height-1.
- Ground is the last row (`height - 1`); the player sits one row
  above it (`height - 2`).
- Player glyph `^`, invader glyphs by row (`W` top rows, `V` middle,
  `U` bottom — distinct per row band so scoring is visible),
  player bullet `|`, bomb `!`, shield cell `#`, ground `=`.

## State (`Game` dataclass)

- `width, height, player_x, lives, score, level`
- `invaders`: list of `Invader(x, y, row)` — `row` is the original
  formation row (0 = top), which decides the score value.
- `direction`: +1 (right) or -1 (left) for the whole formation.
- `tick`: frame counter; the formation moves only when
  `tick % move_interval == 0` (checked before incrementing).
- `bullets`: player bullets (at most one, classic rule).
  `bombs`: invader bombs (capped at 3 in flight).
- `shields`: set of `(x, y)` cells, 4 bases, each 5 wide x 2 high,
  evenly spaced above the player row.
- `status`: `"playing"` or `"game_over"`.

## Formation

- `new_game()` builds 5 rows x 11 columns: columns spaced 3 cells
  apart starting at x = 5, rows spaced 2 cells apart starting at
  y = 3. On a 60-wide board that spans x = 5..35, leaving room to
  sweep both ways.
- `move_formation()`: if the next horizontal step would push any
  invader past either edge, reverse `direction` and shift every
  invader down one row instead; otherwise shift every invader
  horizontally by `direction`. This is the page's Step 3 rule.
- Speed: `move_interval = max(2, 10 - (killed // 5) - (level - 1) * 2)`
  where `killed` is invaders destroyed this level. So the formation
  steps every 10 ticks at level start and accelerates as invaders
  die and on later levels, never faster than every 2 ticks. This is
  a tick-count approximation of "a little faster each time they step
  down" — it is monotonic in the same direction and deterministic,
  which the page's wording leaves open.

## Shooting and collisions (in `step()`, in this order)

1. Player move (clamped to `0..width-1`), optional fire: a bullet
   spawns directly above the player only if none is in flight.
2. Bullets move up one cell; bombs move down one cell; anything
   leaving the playfield is dropped.
3. Bullet vs invader: first hit removes that invader, adds its row
   score, removes the bullet. Bullet vs shield: removes that shield
   cell and the bullet. (A bullet can destroy at most one thing.)
4. Bomb vs shield: removes that shield cell and the bomb. Bomb vs
   player: costs one life, clears all bullets and bombs, recentres
   the player; at 0 lives `status = "game_over"`.
5. Formation move (on its tick), then invader fire: with a seeded
   `random.Random` (default: a fresh one), each tick has a chance to
   drop a bomb from a random bottom-most invader of a random column,
   only if fewer than 3 bombs are in flight. Randomness is injected
   so tests can seed it deterministically.
6. End checks: if no invaders remain, advance a level (fresh
   formation, `level += 1`, score and lives kept). If any invader
   reaches the player row or below, `status = "game_over"`.
   A `step()` on a game-over game is a no-op.

## Rendering

- `render(game)` returns one string: the info bar, then the grid
  with invaders, shields, bullets, bombs, player and ground, then a
  `GAME OVER — press R` line when applicable. Pure function, no
  curses calls, so tests can assert on it.

## Divergences from the challenge page (deliberate, minimal)

- No mystery ship and no music/sound: the page lists both under
  "Going Further" as optional extras, not required steps.
- Speed-up is per invader destroyed (plus per level), not strictly
  per descent: the page says "a little faster each time they step
  down"; tying speed to remaining invaders is the classic arcade
  behaviour and is monotonic in the same direction.
- Player bullet count is capped at one in flight (classic rule);
  the page does not specify a cap.
- No graphics files: glyphs are drawn from characters, since the
  terminal has no sprite support. The page allows custom graphics.

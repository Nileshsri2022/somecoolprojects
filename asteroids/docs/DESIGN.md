# asteroids — DESIGN

## Assumptions

- The world is a fixed grid of `WIDTH x HEIGHT` cells (80 x 24,
  a typical terminal), but all positions and velocities are floats
  so movement is smooth between cells; rendering rounds to the
  nearest cell.
- Coordinates use screen convention: x grows right, y grows down.
  An angle of 0 points right, `-pi/2` points up, so the ship
  starts facing up. A velocity is `(cos(angle), sin(angle))`
  times a speed, which is consistent in this convention.
- One `step()` is one game tick (the curses loop runs ~15 ticks
  per second). All tuning constants are per-tick values, not
  per-second, so tests can reason about a single tick exactly.
- `curses` is imported lazily inside `main()` only. Importing
  `asteroids.py` as a library never touches the terminal, which
  is what makes the logic fully unit-testable.

## Model

Plain dataclasses, no behaviour hidden in methods:

- `Ship`: x, y, vx, vy, angle.
- `Asteroid`: x, y, vx, vy, size (3 = large, 2 = medium, 1 = small).
  Radius and score are derived from size via `ASTEROID_RADIUS`
  and `ASTEROID_SCORE`, never stored redundantly.
- `Bullet`: x, y, vx, vy, life (ticks remaining).
- `Saucer`: x, y, vx, vy. Always crosses horizontally.
- `Game`: ship, asteroids, bullets, saucer (or None), score,
  lives, level, tick, invulnerable (ticks remaining), game_over,
  high_score, and an `rng` (a `random.Random`, so tests can seed
  it for deterministic spawns).

## Pure logic functions

- `wrap(value, limit)` — toroidal wrap via modulo.
- `rotate_ship(ship, direction)` — `direction` is -1, 0 or +1;
  angle is normalised to `[-pi, pi]`.
- `apply_thrust(ship)` — adds `THRUST` along the facing angle.
- `move_ship(ship)` / `move_asteroid(a)` / `move_bullet(b)` —
  advance by velocity and wrap (ship velocity also damps by
  `DAMPING = 0.99`, i.e. speed decays slowly, per Step 3).
- `fire_bullet(game)` — spawns at the ship's nose with the ship's
  velocity plus `BULLET_SPEED` along the facing angle; capped at
  `MAX_BULLETS = 4`, as in the arcade game. Returns the bullet
  or None when at the cap.
- `split_asteroid(a)` — large/medium split into two children one
  size smaller, at the same position, flying apart at
  `+/-0.7 rad` from the parent's heading and 0.3 faster (a
  stationary parent's children still move, at speed 0.5, in
  opposite-ish directions). Small asteroids return `[]`.
- `collides(a, b, radius_a, radius_b)` — circle overlap test.
- `spawn_level(game, level)` — `3 + level` large asteroids at
  random positions at least 12 cells from the centre, so the
  respawning ship is never born inside an asteroid.
- `spawn_saucer(game)` — enters from a random side at a random
  height, crossing horizontally at speed 0.4.
- `step(game, rotate=0, thrust=False, fire=False)` — one tick:
  input, movement, bullet expiry, saucer auto-spawn (every 600
  ticks), bullet/asteroid, bullet/saucer and ship/asteroid-or-
  saucer collisions, life loss / respawn / game over, and level
  advance when the field is cleared. Score and high score update
  inside the collision handling.
- `render_frame(game)` — pure: returns the play field as a list
  of strings (ship glyph by facing octant, `O`/`o`/`.` for
  large/medium/small asteroids, `*` bullets, `U` saucer). The
  curses UI only draws these strings plus a HUD line.

## Divergences from the page (deliberate, minimal)

1. **Terminal, not GUI.** The page suggests PyGame / a frontend
   stack; this build is terminal-only (`curses`), per the task
   brief. All page mechanics are preserved.
2. **Saucer does not shoot.** The page mentions the saucer only
   as something to shoot / avoid. It drifts and can be shot or
   collided with, but fires no bullets of its own — that keeps
   the collision model to one bullet list.
3. **High score is per-session, not persisted.** The Going
   Further high-score table is kept in memory for the session
   (shown on start / game-over screens); no score file is
   written.
4. **Level-clear timing.** A level advances the tick the last
   asteroid is destroyed, spawning the next field immediately
   (no inter-level pause), so `step()` stays a single pure tick.
5. **Respawn invulnerability instead of a safe-zone check.**
   After losing a life the ship respawns in the centre with 30
   invulnerable ticks rather than waiting for the centre to
   clear; asteroids are never cleared on respawn.

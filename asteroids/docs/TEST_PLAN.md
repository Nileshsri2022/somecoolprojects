# asteroids — TEST_PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No terminal is needed: tests import only the pure logic in
`asteroids.py` (`curses` is imported lazily inside `main()`).

## Coverage map

- **Wrap:** positions past each edge re-enter on the opposite
  edge, for ship and asteroid alike, including negative coords.
- **Ship:** rotation changes angle by `ROTATION` per tick in the
  right direction and normalises past `pi`; thrust adds velocity
  along the facing angle; velocity damps by `DAMPING` each tick
  without thrust and keeps the ship drifting (inertia).
- **Bullets:** spawn at the ship's nose, travel straight along
  the facing angle plus the ship's velocity, expire after
  `BULLET_LIFE` ticks, and respect the `MAX_BULLETS` cap.
- **Asteroids:** move and wrap; a large hit splits into two
  faster mediums, a medium into two smalls, a small is destroyed
  outright; children fly in different directions.
- **Collisions:** bullet/asteroid (bullet consumed, score added,
  small-target scores highest), ship/asteroid, ship/saucer,
  bullet/saucer; no collision when objects are far apart; an
  invulnerable ship does not lose a life.
- **Scoring / lives / levels:** 20/50/100 for large/medium/small,
  200 for the saucer; losing a life respawns the ship in the
  centre with invulnerability; losing the last life sets
  `game_over` and freezes the game; clearing a level advances
  the level and spawns a larger field with score and lives kept.
- **Saucer:** spawns crossing horizontally from an edge, wraps,
  and is removed when shot.
- **Rendering:** `render_frame` returns `HEIGHT` rows of `WIDTH`
  characters, places the ship/asteroid/bullet/saucer glyphs at
  the right cells, and draws the ship glyph matching its facing
  octant (e.g. `^` when facing up).
- **Determinism:** a seeded `Game` spawns a reproducible level
  field (same asteroid positions across two seeded games).

## What is NOT tested

- The curses UI itself (key handling, screen drawing, frame
  timing): it is a thin loop over `step()` and `render_frame()`,
  both fully tested. Verify it manually with
  `python3 asteroids.py` in a real terminal.

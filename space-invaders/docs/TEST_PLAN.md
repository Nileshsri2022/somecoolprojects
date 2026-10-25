# Space Invaders — TEST PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests run on pure functions — no terminal, no curses, no
unseeded randomness (randomness is injected via `random.Random`
seeds where a test needs it).

## Cases (tests/test_space_invaders.py)

1. `new_game`: 5 rows x 11 columns = 55 invaders, rows 0-4, player
   centred on the player row, 3 lives, score 0, level 1, status
   playing, 4 shield bases present, formation direction right.
2. Player movement: left/right moves by one, clamps at both edges,
   ignores a game-over game.
3. Formation movement: moves right by one on its tick, does not move
   off-tick, reverses direction and steps down one row (without a
   horizontal move) at the right edge, and symmetrically at the
   left edge.
4. Speed-up: `move_interval` shrinks as invaders are destroyed and
   on higher levels, and never drops below 2.
5. Player fire: spawns one bullet above the player; a second fire
   while one is in flight spawns nothing; the bullet moves up one
   cell per step and is dropped when it leaves the playfield.
6. Bullet vs invader: bullet on an invader cell removes that invader
   only, adds the correct row score (30/20/10 by row band), removes
   the bullet.
7. Bullet vs shield: bullet on a shield cell removes that cell and
   the bullet, and does not score.
8. Bomb vs shield: bomb on a shield cell removes that cell and the
   bomb.
9. Bomb vs player: costs exactly one life, clears bullets and bombs,
   recentres the player; the third such hit ends the game.
10. Invader fire: with a seeded RNG, a long run of steps produces at
    least one bomb, bombs never exceed the cap of 3, and a bomb
    spawns below an invader (from a bottom-most invader column).
11. Level advance: destroying the last invader starts the next level
    with a fresh 55-invader formation, level incremented, score and
    lives preserved.
12. Game over by invasion: an invader stepped onto the player row
    ends the game, and further steps are no-ops.
13. Rendering: the rendered string contains the score, lives, player
    glyph, an invader glyph, a shield glyph and the ground line;
    after game over it contains `GAME OVER`.
14. CLI validation: bad width/height/tick values are rejected
    (argparse errors), and valid flags parse.

## Success criteria

- Every test above passes: `OK` with no failures or errors.
- `python3 space_invaders.py --help` exits cleanly.
- No imports beyond the Python standard library.

# pong — TEST_PLAN

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

No terminal is needed: every test constructs a `Game`
directly and calls pure functions. The curses shell is
not unit-tested (it only wires keys to these functions);
it is verified by a smoke run, not by automation.

## Cases (tests/test_pong.py)

Serve:
- default serve puts the ball on the centre column
  (`width // 2`) with `|vx| == 1` and `|vy| <= 1`;
- explicit direction/angle serve is exact
  (`direction=-1, angle_deg=0` -> `vx=-1, vy=0`);
- seeded serve is reproducible and stays in bounds over
  many serves (row in range, `|vy| <= 1`).

Paddle movement:
- move up/down by the delta; clamping at the top (0)
  and bottom (`height - paddle_height`); both sides.

Wall bounce:
- top wall: ball moving up past row 0 clamps to 0,
  `vy` flips, `vx` unchanged;
- bottom wall: same, mirrored.

Paddle collision:
- left paddle hit flips `vx`, ball placed outside paddle;
- right paddle hit flips `vx`;
- ball passing a paddle column outside the paddle span
  does NOT flip `vx` (it goes on to score);
- centre hit -> `vy == 0`; top-edge hit -> `vy < 0`;
  bottom-edge hit -> `vy > 0`; `|vy| <= 1` after a hit.

Scoring and winning:
- ball past the left edge scores for right; past the
  right edge scores for left; after a non-winning score
  the ball is re-served on the centre line;
- reaching `winning_score` sets `winner`, stops the ball,
  and further `step()` calls change nothing;
- `is_game_over()` is False during play, True once a
  winner is set.

AI:
- moves towards the ball's row by at most one cell when
  the ball approaches (`vx > 0`);
- does not move when the ball travels away (`vx <= 0`);
- stays clamped at the field edges.

Rendering:
- score line shows both scores; winner line shows the
  winner once won;
- output has exactly `height + 1` lines, each field row
  exactly `width` wide;
- ball, both paddles, and the dashed centre line are all
  present in the rendered text;
- rendering does not mutate state.

CLI argument validation:
- `parse_args` accepts defaults and custom values;
- invalid values (winning score 0, tiny width/height,
  paddle taller than the field) are rejected.

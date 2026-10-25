# pong — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Representation

One dataclass, `Game`, holds all mutable state:

```
width, height, paddle_height, winning_score
left_y, right_y      # top row of each paddle (int)
ball_x, ball_y       # floats
vx, vy               # floats, |vx| == 1 while in play
left_score, right_score
winner               # None, "left", or "right"
```

No separate Ball/Paddle classes: nothing in the game needs
methods on them, and one flat state object keeps `step()`
trivial to test (build a `Game`, set fields, call `step`,
assert fields). Paddle columns are derived, not stored:
left `1`, right `width - 2`.

## Tick order in step()

`step(state)` does exactly one tick and returns an event
string (`None`, `"left_scores"`, `"right_scores"`,
`"left_wins"`, `"right_wins"`):

1. If `winner` is already set, do nothing, return `None`.
   A won game never advances.
2. Move the ball: `ball_x += vx`, `ball_y += vy`.
3. Wall bounce: clamp `y` to `[0, height - 1]` and flip
   `vy` if it went out. Horizontal direction untouched,
   per the page.
4. Paddle collision: if travelling left and the new `x`
   is `<= 1` (and the old `x` was `> 1`), or travelling
   right and the new `x` is `>= width - 2` (and the old
   `x` was `< width - 2`), and the ball's row is within
   the paddle's span, it is a hit: flip `vx`, set `vy`
   from the hit offset, and place the ball one column
   outside the paddle. Checking the old position prevents
   a ball already sitting on a paddle column from bouncing
   repeatedly.
5. Scoring: if `ball_x < 0` the right player scores, if
   `ball_x >= width` the left player scores. On a score,
   if the scorer reaches `winning_score` set `winner`
   and stop the ball (`vx = vy = 0`); otherwise re-serve
   immediately (ball back on the centre line, new random
   direction/angle).

Paddle collision is checked before scoring, so a ball that
reaches a paddle column on the same tick is returned, not
scored — a miss is only a ball that passes the paddle
column outside the paddle's span.

## Serve

`serve(state, direction=None, angle_deg=None, rng=None)`:
places the ball at `x = width // 2` (the central line;
for even widths this is the first column right of centre,
documented, not fudged) and a random row `y` in
`[0, height - 1]`. If `direction` is omitted it is a
random `+1`/`-1`; if `angle_deg` is omitted it is uniform
in `[-45, 45]`. Then `vx = direction`,
`vy = tan(angle)` (so `|vy| <= 1`, matching the speed
invariant). The explicit parameters exist only so tests
can serve deterministically; the game always calls it
with neither, i.e. fully random, as the page requires.
`rng` defaults to the module `random` module; tests pass
a seeded `random.Random`.

## Paddle hit angle

On a paddle hit, `vy` is set from where the ball struck:

```
centre = paddle_y + (paddle_height - 1) / 2
offset = (ball_y - centre) / (paddle_height / 2)  # ~[-1, 1]
vy = max(-1, min(1, offset))
```

Hitting the paddle centre keeps the ball level; hitting an
edge sends it off at up to 45 degrees. This is the one
deliberate addition beyond the page's bare "changes
horizontal direction": without it every rally would be a
flat back-and-forth and the AI/player could never change
the ball's angle. It preserves `|vy| <= 1` and is covered
by tests (centre -> 0, top -> negative, bottom -> positive).

## Player movement

`move_paddle(state, side, delta)` adds `delta` (-1 up,
+1 down, but any int works) to that side's top row and
clamps to `[0, height - paddle_height]`. Clamping, not
erroring, is the choice: holding a key at the edge is
normal play, not an error.

## Computer player (beatable by construction)

`ai_move(state)` moves the right paddle at most one cell
per tick, and only while the ball travels towards it
(`vx > 0`):

- Target is the ball's current row (not a predicted
  intercept row — no prediction, so a fast angled ball
  beats it).
- If the paddle's centre is above the ball it moves down
  one cell, if below it moves up one cell, if within half
  a cell it stays.
- If the ball travels away (`vx <= 0`) the paddle does
  not move at all, so it is out of position after its own
  return.

One cell per tick against a ball moving one column per
tick with `|vy|` up to 1 means the AI cannot keep up with
steep angles — that, plus no prediction, is what makes
it beatable. No difficulty levels: the page asks for one
beatable opponent, not a ladder.

## Rendering

`render(state)` returns one string: a score line
(`Left 2 - 1 Right`, or `Left wins!` / `Right wins!` once
won) followed by `height` rows of `width` characters.
Per row: paddle columns show `|`, the ball cell shows
`O`, the centre column shows `:` on alternating rows
(dashed centre line), everything else is a space. The
ball's float position is rounded to the nearest cell for
display only; rendering never mutates state. If the ball
cell coincides with a paddle cell, the ball wins (`O`),
so a hit is always visible.

## Curses shell (thin)

`play(stdscr)` is the only terminal code: it sets
non-blocking input, reads keys, calls `move_paddle` /
`ai_move` / `step` once per ~70 ms tick, and draws
`render(state)` with `addstr`. On win it draws the final
frame and waits for `R` (new game, same settings) or `Q`.
`main(argv)` only parses arguments and calls
`curses.wrapper(play)`; argument validation
(`winning_score >= 1`, `width >= 10`, `height >= 5`,
`paddle_height >= 2` and `< height`) raises `ValueError`
via argparse's `type`/`parser.error` path before any
terminal is opened, so bad flags fail cleanly.

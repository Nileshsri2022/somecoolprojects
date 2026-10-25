# Snake — DESIGN

## Assumptions (stated before coding, ponytail rules)

1. Terminal only, per the task brief. `curses` is stdlib, so the
   "Python 3 standard library only" constraint still holds. No
   PyGame, no GUI toolkit.
2. All game logic is pure and terminal-free. The curses code is a
   thin shell: read a key, call `set_direction`/`step`, draw
   `render()` output. Every rule below is unit-testable without
   a terminal.
3. Coordinates are `(x, y)` cell pairs, `x` right, `y` down,
   origin at the top-left inner cell. The snake body is a list,
   head first. This makes "remove tail, add head" a one-liner
   and makes self-collision a membership test.
4. One food item at a time, as on the page. Food never spawns on
   the snake; spawning takes an injectable `random.Random` so
   tests are deterministic.
5. Minimum board size is enforced (at least 5x5, and large enough
   for the 4-cell starting snake) rather than crashing on a
   degenerate `--width`/`--height`.

## Module layout (`snake.py`, single file)

- `DIRECTIONS` — `UP/DOWN/LEFT/RIGHT` as `(dx, dy)`; `OPPOSITE`
  for reversal rejection.
- `spawn_food(width, height, occupied, rng)` -> `(x, y) | None`.
  Returns `None` only when no free cell exists (full board).
- `tick_interval(foods_eaten)` -> seconds between ticks:
  `max(0.060, 0.150 - 0.005 * foods_eaten)`.
- `class Game` — the whole state:
  - fields: `width`, `height`, `body`, `direction`,
    `_pending` (direction queue), `food`, `score`,
    `foods_eaten`, `alive`, `death` (`None | "wall" | "self" |
    "win"`), `rng`.
  - `Game(width, height, rng=None)` — centre start, length 4,
    moving right, one food spawned.
  - `set_direction(d)` — appends to the queue if it is not the
    opposite of the last queued/current direction and not a
    repeat of it; no-ops after death.
  - `step()` — applies at most one queued direction, computes
    the new head, checks wall/self collision, grows on food
    (score += 10, new food), otherwise drops the tail.
    Sets `alive=False` and `death` on wall/self collision.
    If the snake fills the board after eating, `food=None`,
    `alive=False`, `death="win"`. No-op once dead.
  - `render()` -> list of strings: `#` border, `O` head,
    `o` body, `*` food, space elsewhere. Pure string output so
    tests can assert exact boards without curses.
- Curses shell: `main(stdscr)` (game loop with `timeout()` set
  from `tick_interval`), `play()` (`curses.wrapper`), CLI
  parsing in `main_cli()` (`--width`, `--height`, `--help`).
  Only this shell touches the terminal.

## Why a direction queue, not a single pending direction

A single pending direction loses fast keypresses; worse, two
keypresses between ticks (e.g. up then left while moving right)
applied naively would let the snake reverse into itself. The
queue applies one change per tick and each queued change is
validated against the direction before it, so up-then-left is
legal but right-then-left is rejected at queue time.

## Why the tail cell is safe to enter (except when eating)

`step()` computes the body that will remain after the move:
if not eating, the tail cell is dropped, so the new head may
land there. If eating, nothing is dropped, so the same cell is
a collision. This matches the page's tail-removal description
and is covered by dedicated tests.

## Divergences from the page (all documented, none hidden)

- Terminal/`curses` instead of a pixel grid: the page's Step 1
  talks in pixels/cells (e.g. 20x20 cells of 20 px). Here one
  terminal character is one cell; there are no pixels.
- Score value (10/food) and speed-up curve: unspecified on the
  page, fixed here (see SPEC.md).
- "Win" on a full board: unspecified on the page; treated as
  game over with `death="win"` rather than crashing in
  `spawn_food`.
- Not built: multiplayer, persistent high scores (page's
  "Going Further" — out of scope, minimum code).

## Success criteria

- `python3 -m unittest discover -s tests -v` passes (see
  TEST_PLAN.md).
- `python3 snake.py --help` prints usage without starting curses.
- Playable in a terminal: snake moves, eats, grows, scores,
  dies on wall/self, restarts with `r`.

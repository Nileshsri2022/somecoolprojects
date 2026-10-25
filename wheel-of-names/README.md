# wheel-of-names — Build Your Own Wheel of Names

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Wheel of Names (no GUI): enter names, shuffle or
sort them, spin a wheel that slows down, and get a winner —
plus a standalone HTML/SVG snapshot of the final wheel that
can be opened in a browser.

## Usage

Non-interactive (spin once):

```sh
python3 wheel.py --names Alice,Bob,Carol,Dave
python3 wheel.py --names Alice,Bob,Carol --fast --seed 42
python3 wheel.py --file names.txt --html wheel.html
python3 wheel.py --entry "Alice:2:#e6194b" --entry "Bob:1" --fast
python3 wheel.py --names Alice,Bob,Carol --list
```

No arguments at all starts an interactive prompt:

```
wheel> add Alice
wheel> add Bob
wheel> shuffle
wheel> spin
wheel> html wheel.html
wheel> quit
```

Interactive commands: `add NAME`, `remove NAME`, `list`,
`shuffle`, `sort`, `spin [--fast]`, `html PATH`, `quit`.
A `--file` line is one name per line, or
`name|weight|#color` for advanced entries.

## Rules

- Default mode: every name gets an equal segment (360/N
  degrees); neighbours always get different colours.
- Advanced mode: a weight sizes a segment proportionally
  and a `#RRGGBB` colour overrides the palette.
- The winner is picked first (uniform, or proportional to
  weight), then the animation lands on it — the animation
  never re-decides the result. The pointer sits at the top.
- Spins use 5–10 full turns with an ease-out cubic slowdown.
- With `--seed N` a spin is fully reproducible.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover parsing, add/remove, shuffle/sort, segment
geometry and colours (including the N = 9 wrap-around case),
weighted segments, spin reproducibility and pointer
consistency, animation frames, SVG/HTML rendering, and
CLI argument building — all on pure functions with seeded
RNG, no terminal needed.

## Files

- `wheel.py` — list management, segments, spin, SVG/HTML
  rendering, terminal animation, and a thin CLI shell.
- `docs/SPEC.md` — challenge spec and steps.
- `docs/DESIGN.md` — design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_wheel.py` — the test suite.

## Divergences from the challenge page

- No GUI: the page allows desktop/CLI/web, and this
  project's brief is terminal-only. The wheel is visualised
  as a terminal spin animation plus a static HTML/SVG file
  (no JavaScript animation in the HTML — duplicating the
  terminal animation in JS would be speculative extra code).
- The page's advanced mode is colour + size per segment,
  implemented here as weight + `#RRGGBB` strings, the
  terminal equivalent of a colour picker.
- Going Further items (deploy, save/share wheels, Discord
  bot) are not built; the HTML snapshot is a plain file
  that can be opened or shared as-is.
- Challenge page slug: `challenge-wheel`, not
  `challenge-wheel-of-names` (that URL 404s); see
  `docs/SPEC.md`.

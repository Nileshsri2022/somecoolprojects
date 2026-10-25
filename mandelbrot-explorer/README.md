# mandelbrot-explorer — Build Your Own Mandelbrot Set Explorer

Coding Challenges #84, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Source page: https://codingchallenges.fyi/challenges/challenge-mandelbrot
(note: the slug is `challenge-mandelbrot`, not
`challenge-mandelbrot-set-explorer` — that guess 404s).

Draws the Mandelbrot set by escape-time iteration of `f(z) = z^2 + c`
from `z = 0`: a point escapes when `|z| > 2`, and points that have not
escaped after `--max-iter` iterations are treated as inside the set.
Python 3 standard library only, no display needed.

## Usage

```sh
# ASCII art of the full set (default view -2..2 on both axes)
python3 mandelbrot.py --width 80 --height 40

# A zoomed view, two ways (page Steps 2-3): bounding box, or centre + magnification
python3 mandelbrot.py --box -1.75 1.75 -1.75 1.75 --width 80 --height 40
python3 mandelbrot.py --center -0.5 0 --zoom 2 --width 80 --height 40

# PNG export (page Step 5): size + DPI + palette are user-chosen.
# Defaults to 800x800 when --width/--height are not given.
python3 mandelbrot.py --output mandelbrot.png --dpi 300 --palette fire
python3 mandelbrot.py --output small.png --width 400 --height 400 --dpi 72 --palette ocean
```

Palettes: `grayscale` (default), `fire`, `ocean`. Inside points are
black in PNG and `@` in ASCII; outside points shade by escape speed.
`--box` wins over `--center/--zoom` if both are given. Bad values
(non-positive width/height/max-iter/zoom/DPI, a reversed box, an
unknown palette, a non-`.png` output path) exit non-zero with a
message on stderr.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps: known inside/outside points and exact
escape counts, coordinate mapping and zoom, ASCII dimensions and
content, palette colours, PNG structure/CRC/DPI (72 and 300), and the
CLI — all without a display.

## Divergences from the page (documented, not hidden)

- The page specifies no CLI, pixel mapping, or palette values, so those
  are this project's choices, documented in `docs/SPEC.md`.
- The default view is the page's `-2..2` on each axis, not the classic
  `-2.5..1` by `-1..1` framing; any framing is reachable via `--box`.
- ASCII uses one fixed gradient (colour customisation applies to PNG,
  per Step 4's colouring discussion); there is no interactive
  bounding-box selection on a plotted image — selection is via
  `--box` / `--center --zoom` flags, which is the headless equivalent.
- "Going Further" (other fractals) is not built.
- No push to GitHub in this task (builds and tests only, per the
  assignment); the repo root README and the sync record were untouched.

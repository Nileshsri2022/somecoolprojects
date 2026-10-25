# SPEC — Mandelbrot Set Explorer

Source challenge page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-mandelbrot
("Build Your Own Mandelbrot Set Explorer", Coding Challenges #84).

Slug note: the first guess `challenge-mandelbrot-set-explorer` returned
HTTP 404. The correct live slug, reached via the site's graphics tag page,
is `challenge-mandelbrot` (no `-set-explorer` suffix).

## Steps from the page, mapped to this build

| Page step | Requirement | Implementation |
|---|---|---|
| Step 0 | Set up a project | This directory; no push in this task (builds/tests only) |
| Step 1 | Draw the Mandelbrot set: plot the complex numbers `c` for which `f(z) = z^2 + c`, iterated from `z = 0`, does not diverge | `escape_count(c, max_iter)` + `render_ascii()`; default view `-2..2` on both axes, as the page states |
| Step 2 | Draw a zoomed-in view (e.g. `-1.75..1.75`, or `-1.75..-1.5`) | `--box xmin xmax ymin ymax` and `--zoom` (see below) |
| Step 3 | Let the user select what to explore: a bounding box, or a centre + magnification | `--box` for a bounding box; `--center CX CY --zoom FACTOR` for centre + magnification |
| Step 4 | Let the user customise the colours | `--palette {grayscale,fire,ocean}` for PNG colouring; ASCII uses a fixed gradient (see DESIGN.md) |
| Step 5 | Export as PNG, with user-specified size and DPI (e.g. 72 for web, 300+ for a poster) | `--output FILE.png --width W --height H --dpi DPI`; PNG is hand-written with stdlib `zlib`/`struct` only, and carries a `pHYs` chunk encoding the DPI |
| Going Further | Other fractals | NOT built (out of scope; see divergences in README.md) |

## Behaviour contract

- Escape rule: iterate `z <- z^2 + c` from `z = 0`. A point escapes at
  the first iteration where `|z| > 2` (tested as `x*x + y*y > 4`, so no
  square root is needed). `escape_count` returns that iteration number
  (1-based: the iteration that produced the escaping value). If no
  iteration escapes within `max_iter` iterations, it returns `max_iter`
  and the point is treated as inside the set.
- Coordinate mapping: pixel `(px, py)` in a `width x height` grid maps to
  `real = xmin + px / width * (xmax - xmin)` and
  `imag = ymax - py / height * (ymax - ymin)`. Row 0 is the top of the
  image (largest imaginary part). Pixel centres are not used; the
  top-left pixel maps exactly to `(xmin, ymax)`, which keeps the mapping
  trivially testable.
- ASCII rendering: `render_ascii(view, width, height, max_iter)` returns
  a list of `height` strings, each exactly `width` characters long.
  Inside points render as `@`; outside points render from the gradient
  `" .:-=+*#%"` (space for the fastest escapees, `%` for the slowest),
  so `@` is reserved for the set itself.
- Zoom: `--zoom FACTOR` with `--center CX CY` (defaults `0 0`) shrinks
  the view's width and height by `FACTOR` around the centre
  (`FACTOR > 1` zooms in, `0 < FACTOR < 1` zooms out). `--box` takes
  precedence over `--center/--zoom` if both are given.
- PNG: `--output` writes a true-colour (colour type 2) PNG at
  `--width x --height` pixels, coloured by `--palette`, with inside
  points black. The `pHYs` chunk records the DPI as pixels per metre
  (`round(dpi * 39.3700787)`); the pixel data itself does not change
  with DPI — DPI is metadata, exactly as the page's 72 vs 300 DPI
  distinction implies.
- Defaults: view `-2..2` on both axes, `80 x 40` ASCII, `800 x 800` PNG
  when `--output` is given without `--width/--height`, `max_iter = 100`,
  palette `grayscale`.
- Errors: non-positive width/height/max-iter/DPI, non-positive zoom,
  a box with `xmin >= xmax` or `ymin >= ymax`, an unknown palette, or
  an `--output` path not ending in `.png` are rejected with a message
  on stderr and a non-zero exit code. No display, window, or GUI is
  required: ASCII goes to stdout and PNG to a file, so everything is
  testable headlessly.

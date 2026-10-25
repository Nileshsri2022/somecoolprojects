# DESIGN — Mandelbrot Set Explorer

## Assumptions (stated before coding, ponytail rules)

1. The page gives no CLI, no exact pixel mapping, and no palette values,
   so those are this design's choices, documented in SPEC.md — not claims
   about the page.
2. The page's default view is `-2..2` on each axis, so that is the
   default, even though the classic full-set framing is `-2.5..1` by
   `-1..1`; the user can reach any framing with `--box`.
3. "Inside" can only ever be approximate: a point is called inside when
   it has not escaped after `max_iter` iterations. Boundary points may
   be misclassified at low `max_iter`; that is inherent to escape-time
   rendering, not a bug.
4. Python's `complex` type is not used for the hot loop. The iteration
   is written with two floats (`x`, `y`) so the escape test
   `x*x + y*y > 4` avoids a square root and a `complex` allocation per
   step. The public API still accepts a `complex` for `escape_count`.
5. One file (`mandelbrot.py`), stdlib only (`argparse`, `struct`,
   `zlib`, `sys`). PNG encoding is hand-written: signature, IHDR, pHYs,
   IDAT (one zlib stream, filter byte 0 per scanline), IEND, each chunk
   with a CRC-32. No Pillow, no NumPy.

## Module layout (`mandelbrot.py`)

- `escape_count(c, max_iter=100)` — the escape-time core. Loop:
  `x, y = 0.0, 0.0`; each iteration `x, y = x*x - y*y + c.real,
  2*x*y + c.imag`; if `x*x + y*y > 4`, return the iteration number
  (1-based). Otherwise return `max_iter` after the loop.
- `map_pixel(px, py, width, height, view)` — `view` is a
  `(xmin, xmax, ymin, ymax)` tuple; returns a `complex` per SPEC.md.
- `zoom_view(view, cx, cy, factor)` — pure function: new half-widths
  are the old half-widths divided by `factor`, centred on `(cx, cy)`.
  Keeps the view's aspect ratio.
- `ascii_char(count, max_iter)` — `count >= max_iter` gives `'@'`;
  otherwise `GRADIENT[count * (len(GRADIENT) - 1) // max_iter]` with
  `GRADIENT = " .:-=+*#%"`, so the fastest escapees are spaces and
  near-set points are `%`.
- `render_ascii(view, width, height, max_iter=100)` — nested loop over
  rows/columns calling `map_pixel` + `escape_count` + `ascii_char`.
  Returns `list[str]`, no printing (testable without stdout).
- `PALETTES` — name -> list of RGB stops; `palette_color(count,
  max_iter, palette)` returns black `(0, 0, 0)` for inside points and a
  linearly interpolated stop colour otherwise, with `count / max_iter`
  as the position. Palettes: `grayscale` (white -> grey), `fire`
  (yellow -> orange -> red -> dark red), `ocean` (cyan -> blue ->
  deep blue).
- `write_png(path, view, width, height, max_iter, palette, dpi)` —
  renders the same escape grid as bytes, then writes the PNG described
  above. DPI affects only the `pHYs` chunk.
- `parse_args(argv)` / `main(argv=None)` — `argparse` CLI. `--box`
  (4 floats) wins over `--center`/`--zoom`. ASCII is the default
  output; `--output` switches to PNG. Validation uses
  `parser.error(...)` (exit code 2) for bad values.

## Verifiable success criteria

- Known points classify correctly (see TEST_PLAN.md for the table).
- `render_ascii` returns exactly `height` rows of exactly `width`
  characters, and its centre region contains `@` for the default view.
- A PNG written by `write_png` starts with the PNG signature, parses
  as IHDR/pHYs/IDAT/IEND with correct CRCs (checked by re-reading it
  with stdlib `struct`/`zlib` in tests), and its `pHYs` value matches
  the requested DPI.
- CLI: `python3 mandelbrot.py --width 20 --height 10` prints 10 lines
  of 20 characters; invalid arguments exit non-zero.

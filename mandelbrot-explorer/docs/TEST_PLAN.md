# TEST_PLAN — Mandelbrot Set Explorer

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No display, network, or third-party package is needed.

## Cases

### escape_count (known points, hand-traced)

| `c` | Expected | Why (trace) |
|---|---|---|
| `0` | `max_iter` | stays at 0 forever |
| `-1` | `max_iter` | cycles `0, -1, 0, ...` |
| `-2` | `max_iter` | `0, -2, 2, 2, ...`, never `> 2` |
| `0.25` | `max_iter` | cusp of the main cardioid, in the set |
| `-0.5` | `max_iter` | converges, never escapes |
| `3` | `1` | first iterate is `3`, `|3| > 2` |
| `2` | `2` | `0, 2, 6`, escapes on iteration 2 |
| `1` | `3` | `0, 1, 2, 5`, escapes on iteration 3 |
| `0.5` | `5` | `0, 0.5, 0.75, 1.0625, 1.6289, 3.153...`, escapes on iteration 5 |
| `1j` | `max_iter` | cycles `0, i, -1+i, -i, -1+i, ...` |
| `2j` | `2` | `0, 2i, -4+2i`; `z1` has `|z| = 2` (not `> 2`, so no escape), `z2` has `|z| > 2`, so it escapes on iteration 2 |

Also: `escape_count` with a small `max_iter` caps at `max_iter`
(e.g. `escape_count(1, max_iter=2) == 2`), and `max_iter <= 0` raises
`ValueError`.

### map_pixel / zoom_view

- Top-left pixel `(0, 0)` maps to `(xmin, ymax)`; the mapping is
  linear: doubling the grid position doubles the offset from the
  origin corner.
- `zoom_view` with factor 2 halves both half-widths around the centre;
  factor 1 is the identity; a non-positive factor raises `ValueError`.
- A zoomed view centred on the default view's centre keeps the same
  centre.

### render_ascii / ascii_char

- Output dimensions: exactly `height` rows, each exactly `width` chars.
- `ascii_char(max_iter, max_iter) == '@'`; `ascii_char(0, max_iter)`
  is a space; characters get "denser" (later in the gradient) as the
  count grows.
- The default view's render contains `@` (the set is visible) and also
  spaces (outside points exist); a render of a far-away box
  (e.g. `10..11` on both axes) contains no `@` at all.

### Palettes / PNG

- `palette_color` returns black for inside points, and a valid
  3-tuple of 0..255 ints for outside points, for every palette.
- Unknown palette name raises `ValueError` (library) / non-zero exit
  (CLI).
- `write_png` output: starts with the 8-byte PNG signature; chunk
  walk (length, type, CRC via `zlib.crc32`) reaches IEND with no
  trailing bytes; decompressed IDAT has `height` scanlines of
  `1 + width * 3` bytes; the `pHYs` pixels-per-metre equals
  `round(dpi * 39.3700787)` for 72 and 300 DPI.
- PNG pixel check: the centre pixel of the default view is black
  (inside the set); a corner pixel is not black.

### CLI (subprocess-free, via `main()` with captured stdout/stderr)

- Default ASCII run prints the requested number of rows/columns.
- `--box` and `--center/--zoom` runs succeed and print ASCII.
- `--output out.png` writes a PNG file (verified as above).
- Bad width (`0`), bad zoom (`0`), reversed box, unknown palette,
  and a non-`.png` output path all exit non-zero.
</atem:ner>

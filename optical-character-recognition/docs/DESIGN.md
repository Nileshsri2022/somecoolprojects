# DESIGN — OCR tool

## Pipeline

```
load image -> greyscale -> binarise -> [optional deskew] -> segment
  -> group into lines -> normalise each blob -> template match -> text
```

All stages are pure functions in `ocr.py` so the test suite can exercise
each stage without invoking the CLI.

## 1. Loading and greyscale

- Netpbm: a small hand-written parser. Tokeniser skips whitespace and
  `#` comments; P4/P5/P6 raw bodies are read as bytes after exactly one
  whitespace byte following the maxval token.
- PNG: parses the chunk stream, requires `IHDR` first, collects `IDAT`
  payloads, inflates with `zlib`, then applies the PNG unfilter
  (None/Sub/Up/Average/Paeth) per scanline. Only colour types 0/2/6 at
  bit depth 8, non-interlaced, are accepted; anything else raises
  `ValueError` with the reason.
- Greyscale: RGB -> `0.299R + 0.587G + 0.114B` (integer arithmetic).
  RGBA alpha is composited over white. PGM values are scaled by
  `maxval` to 0–255.

## 2. Binarisation

- Default: Otsu's method — the threshold maximising between-class
  variance of the greyscale histogram. Ink is dark-on-light by default.
- `--threshold N`: fixed threshold, ink = pixels with value <= N.
- `--invert`: ink = pixels with value >= N (or >= Otsu threshold).
- Output is a 2-D list of 0/1 (1 = ink).

## 3. Deskew (`--deskew` only)

For each angle in -10..+10 degrees (1-degree steps, plus 0), rotate the
binary image about its centre with nearest-neighbour sampling and score
it by the sum of squared horizontal-projection counts (a correctly
levelled line concentrates ink into few rows, so this score peaks at
the true angle). The best angle wins; ties keep the smallest
|angle|. Cost is bounded: the search runs on the binary image and the
range is small by design (see SPEC.md divergence 3). The correction
itself is then applied to the GREYSCALE image with bilinear
interpolation and the result re-binarised: re-sampling a binary image
a second time fragments thin diagonal strokes (W, R) — found by test,
fixed this way. Rotation crops to the original canvas — text touching
the border may clip, which is documented, not hidden, and deskew
fixtures are padded for that reason.

## 4. Segmentation (character bounds)

- Connected components over ink pixels with 8-connectivity, via an
  iterative flood fill (no recursion limit risk).
- Noise filter: blobs narrower than 2 px or shorter than 3 px, or with
  fewer than 4 ink pixels, are dropped (they cannot be characters in
  the supported font at any sane scale and are almost always specks).
- Boxes: `(x, y, w, h)` in original image coordinates, after deskew if
  enabled.

## 5. Line grouping

Blobs are sorted by vertical centre; a blob joins the current line if
its vertical centre lies within the current line's y-span expanded by
half the median blob height, otherwise it starts a new line. Within a
line, blobs sort left-to-right. Word gaps: if the horizontal gap to the
previous blob is >= max(3, 0.8 * median blob width on the line), one
space is emitted. This is deliberately simple: it assumes roughly
horizontal, single-column text, which is the documented scope.

## 6. Recognition (template matching)

- Templates: the 5x7 bitmap font `FONT` (A–Z, 0–9). Each glyph is 7
  strings of 5 characters (`#` = ink, `.` = background).
- Normalisation: a blob's bitmap is resampled to 5x7 by majority vote
  within each of the 5x7 cells of its bounding box. This makes
  recognition scale-invariant for clean block-scaled renderings of the
  font, which is exactly what the fixtures are.
- Matching: Hamming distance (count of differing cells) to every
  template; the best match wins if its distance <= 6 (out of 35 cells),
  otherwise the character is `?`. The threshold 6 tolerates one noisy
  cell row/column of damage but not a different letter: the closest
  distinct letter pairs in this font (e.g. `O`/`Q` is not in the set;
  `O` vs `0`, `I` vs `1`) differ by at least 4–5 cells, so 6 is a
  compromise documented here, not a tuned-to-perfection claim.
- Rendering helper: `render_text()` draws text with the same font at
  an integer scale with configurable spacing, used by the test suite
  to build exact synthetic fixtures and by `--boxes-pbm` demos. It is
  part of the tool, not hidden test-only code: fixtures and templates
  share a font by design, and SPEC.md says so plainly.

## 7. CLI

`argparse` only. Text goes to stdout (so it pipes), diagnostics and
`--boxes` lines go to stderr, box images go to `--boxes-pbm`. Errors
print to stderr and exit non-zero; "no text found" is a success with
empty stdout, not an error.

## Files

- `ocr.py` — the whole tool (loading, pipeline, font, CLI).
- `tests/test_ocr.py` — unittest suite; fixtures are generated in
  memory (PBM bytes via `render_text`, PNG bytes via a tiny in-test
  encoder using `zlib`/`struct`), never from external files.

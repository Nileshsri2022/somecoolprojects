# Build Your Own Optical Character Recognition (OCR)

A Python 3 standard-library-only OCR tool, built for
[Coding Challenge #80](http://codingchallenges.fyi/challenges/challenge-ocr/)
("Build Your Own Optical Character Recognition" on codingchallenges.fyi).

**Honest scope:** this is a template-matching OCR for clean, block-style
text in its own built-in 5x7 bitmap font — uppercase `A`–`Z` and digits
`0`–`9` only. It is NOT general-purpose OCR, NOT handwriting recognition,
and NOT production-grade. See `docs/SPEC.md` for the exact supported
formats, character set, divergences from the challenge page, and
everything deliberately not built.

## Usage

```sh
python3 ocr.py INPUT [--threshold N] [--deskew] [--boxes]
                     [--boxes-pbm FILE] [--invert]
```

- `INPUT` — a PNG (non-interlaced, 8-bit, greyscale/RGB/RGBA) or a
  Netpbm file (PBM/PGM/PPM, ASCII or raw).
- Prints recognised text, one line per text line, to stdout.
- `--boxes` prints `char x y w h` lines to stderr.
- `--boxes-pbm FILE` writes a PBM with boxes drawn around characters.
- `--deskew` corrects skew up to ±10 degrees.
- `--invert` reads light-on-dark images.
- No text found prints nothing and exits 0; bad input exits non-zero.

## Pipeline

Load → greyscale → Otsu binarisation → optional deskew → connected-
component segmentation → line grouping → 5x7 template matching.
Full design notes: `docs/DESIGN.md`.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Fixtures are synthetic only, generated in memory. See
`docs/TEST_PLAN.md` for coverage and measured fixture accuracy.

## Files

- `ocr.py` — the whole tool
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md`
- `tests/test_ocr.py`

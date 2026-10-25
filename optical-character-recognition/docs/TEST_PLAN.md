# TEST_PLAN — OCR tool

Run: `python3 -m unittest discover -s tests -v` from the project root.
All fixtures are synthetic, generated in memory by the tests (PBM via
`ocr.render_text`, PNG via a tiny in-test encoder). No external images,
no network, no page test image (see SPEC.md divergence 4).

## Coverage map

| Area | Tests |
|---|---|
| Netpbm parsing | PBM ASCII + raw, PGM ASCII + raw with maxval scaling, PPM ASCII + raw, comments/whitespace, truncated input raises, unknown magic raises |
| PNG decoding | Greyscale + RGB + RGBA 8-bit non-interlaced round-trip; all five filter types (via per-row filter bytes in the encoder); interlaced / palette / 16-bit rejected |
| Binarisation | Otsu separates a dark/light fixture; fixed threshold respected; invert flips polarity |
| Deskew | A +5-degree skewed rendering is recognised with `--deskew` logic (`deskew()` picks an angle within 1 degree of the true skew on the fixture); 0-degree input stays ~0 |
| Segmentation | Boxes found for every character of a word; blank image yields no boxes; speck noise filtered |
| Line grouping | Two-line fixture yields two lines in order; word gap yields a space; lines sorted top-to-bottom |
| Recognition | Every glyph A–Z and 0–9 recognised at scale 1, 2 and 3; multi-word sentences; unknown blob yields `?`, not a crash |
| CLI end-to-end | `ocr.py` on a PBM and a PNG fixture prints the expected text; `--boxes` output; `--boxes-pbm` file is a valid PBM containing box pixels; blank image prints nothing with exit 0; missing file / unsupported format exits non-zero |
| Accuracy (honest) | `test_accuracy_report` prints the measured fixture accuracy to stderr during the run; the numbers below are the run's results, not targets |

## Measured accuracy (run 2026-10-25, suite green — update if the code changes)

- Clean fixtures (all 36 glyphs, scales 1–3): 108/108 = 100.0%.
- Skewed fixture ("HELLO WORLD", scale 3, +5 degrees, with deskew):
  11/11 characters = 100.0% through the full pipeline (greyscale
  correction). Note: the binary-rotation-only path fragments W/R at
  5 degrees and is NOT the pipeline path; the angle search still uses
  binary rotation.
- Noisy fixture ("NOISE" + one isolated speck pixel): recognised
  exactly, speck dropped by the noise filter.
- Deskew angle recovery on the "HELLO" scale-3 fixture: within 2
  degrees of the true +5-degree skew.
- What these numbers do NOT mean: they measure template matching
  against renderings of the tool's own font. They say nothing about
  real-world photos, screenshots, other fonts, or handwriting, and
  must not be quoted without that qualifier.

# SPEC — Build Your Own Optical Character Recognition (OCR)

## Resolved challenge page

- URL: http://codingchallenges.fyi/challenges/challenge-ocr/
- Title: "Build Your Own Optical Character Recognition"
- Found via: codingchallenges.fyi tag pages (graphics / beginner) and web search;
  the page itself was read end-to-end before any code was written.
- The page is Coding Challenge #80 (see also the Substack post of the same
  title). It has no versioned test data, no mandated character set, no
  mandated image format beyond a PNG suggestion, and no pass/fail threshold.

## Challenge steps (as written on the page) and how each is met

| Page step | What the page asks | This build |
|---|---|---|
| Step Zero | Create a project in your stack/language of choice; CLI, GUI or API — your choice. | Python 3 standard library only, command-line tool `ocr.py`. |
| Step 1 | Load an image and detect whether it contains any text and where it is. Suggested: PNG support; converting to a binary (black/white) image is suggested; test with a rectangle with text in various locations. | Loads PNG (see Formats) and Netpbm PBM/PGM/PPM; converts to greyscale, then to a binary image with Otsu's threshold (or an explicit `--threshold`). Text regions are found by connected-component analysis (Step 3's boxes double as the Step 1 location evidence). A blank image yields no text and exit code 0. |
| Step 2 | De-skew the text if needed so all text is aligned in the same plane. Test image on the page: six lines, some white, some dark grey, some skewed. | `--deskew` searches small angles and picks the angle whose horizontal projection profile is sharpest (see DESIGN.md). Default is off, because deskewing a clean image can only hurt it. Range is deliberately small (see Divergences). |
| Step 3 | Identify character bounds; suggested verification: render the test image with boxes around all detected characters. | `--boxes` prints one `char x y w h` line per detected character to stderr; `--boxes-pbm FILE` writes a PBM copy of the input with a 1-pixel box drawn around every detected character. |
| Step 4 | Identify the characters detected. The page names approaches from matrix matching through deep-learning neural networks, and points at the Kaggle Digit Recognizer as a standalone version of this step. | Matrix (template) matching — the classical, non-neural end of the range the page allows. Each segmented character is normalised to a 5x7 grid and matched by Hamming distance against built-in 5x7 templates. No neural network, no trained model, no LLM (see Scope limits). |
| Going Further | Extract text from video. | NOT built. See "Not built". |

## Supported input formats (exact)

- PNG: non-interlaced, 8-bit, colour types 0 (greyscale), 2 (RGB),
  6 (RGBA). Decoded by hand with `zlib` + PNG unfiltering — no PIL, no
  external decoder. Interlaced PNGs, 16-bit PNGs, palette PNGs and
  ancillary-chunk-dependent features are rejected with a clear error.
- Netpbm: P1/P4 (PBM), P2/P5 (PGM), P3/P6 (PPM), ASCII and raw variants,
  with `#` comments. `maxval` is honoured for PGM/PPM (any value up to
  65535 for ASCII forms; raw forms assume maxval <= 255, which is the
  standard raw case).
- Anything else (JPEG, GIF, BMP, TIFF, WebP, …) is NOT supported and is
  rejected with a clear error. This is a deliberate stdlib-only limit,
  not a silent gap: decoding those formats by hand is out of scope.

## Supported character set (exact)

Uppercase letters `A`–`Z` and digits `0`–`9` only, in the built-in 5x7
bitmap font defined in `ocr.py` (`FONT`). Lowercase letters, punctuation,
spaces inside a word are handled as follows:

- Word gaps: a horizontal gap between consecutive characters on a line
  that is at least 0.8x the median character width on that line
  (minimum 3 px) is emitted as a single space.
- Any segmented blob that matches no template within the distance
  threshold is emitted as `?` — never silently dropped, never guessed
  beyond the threshold.
- Lowercase input, serif/proportional fonts, anti-aliased text from a
  real renderer, handwriting, rotated text beyond the deskew range, and
  touching/overlapping characters are NOT supported. The tool is a
  template matcher for its own bitmap-font style, and its accuracy
  figures (TEST_PLAN.md) are measured on synthetic fixtures rendered
  with that font. Do not present it as general-purpose OCR.

## Command-line interface

```
python3 ocr.py INPUT [--threshold N] [--deskew] [--boxes]
                     [--boxes-pbm FILE] [--invert]
```

- `INPUT`: path to a PNG or Netpbm file.
- `--threshold N` (0–255): fixed binarisation threshold; default is
  Otsu's automatic threshold.
- `--deskew`: enable the small-angle deskew search before segmentation.
- `--boxes`: also print `char x y w h` lines to stderr.
- `--boxes-pbm FILE`: also write a PBM with boxes drawn around characters.
- `--invert`: treat white-on-black as the ink colour (the page's test
  image mixes white and dark-grey text; this flag plus Otsu covers the
  light-on-dark case for uniform images — mixed-polarity images in a
  single file are NOT handled, see Divergences).
- Output: recognised text, one line per detected text line, on stdout.
  Exit code 0 on success (including "no text found", which prints
  nothing), non-zero with a message on stderr for unreadable or
  unsupported input.

## Deliberate divergences from the page

1. **No OpenCV, no off-the-shelf tools.** The page offers OpenCV as an
   option; this build implements every stage from scratch in the
   standard library, which is the page's "hard mode" path.
2. **No PNG suggestion taken as PNG-only.** Netpbm is added because it
   is trivially parseable by hand and makes synthetic fixtures exact
   (no compression artefacts in the test path). PNG is still supported.
3. **Deskew range limited to ±10 degrees in 1-degree steps.** The page
   does not state an angle; ±10 covers the page's "some lines are
   skewed" case for typical synthetic tests while keeping the search
   cheap. Larger skew is reported honestly as unsupported.
4. **The page's own test image is not used as a fixture.** Its URL is
   recorded below, but the image mixes white and dark-grey text on
   (presumably) varied backgrounds and real rendered fonts, which this
   template matcher cannot read. Tests therefore use synthetic fixtures
   only, and no accuracy claim is made on the page's image. Claiming
   otherwise would be fabrication.
   Page test image URL (as shown on the page):
   https://codingchallenges.fyi/assets/images/Coding_Challenge_OCR_Test_Image-b43e7558d169e48567d5d3a2819f9469.png
5. **Mixed polarity in one image not handled.** Step 2's test image has
   white lines and dark-grey lines; a single global threshold cannot
   separate both polarities at once. `--invert` handles uniform
   light-on-dark images. Per-line polarity detection is out of scope.
6. **No GUI, no API, no video.** CLI only; "Going Further" (video) is
   not built.

## Not built (honest scope limits)

- Video extraction ("Going Further").
- Handwriting recognition, arbitrary fonts, lowercase, punctuation
  beyond `?` fallback, cursive/connected scripts, non-Latin scripts.
- JPEG/GIF/BMP/TIFF/WebP decoding; interlaced or 16-bit or palette PNG.
- Colour segmentation, adaptive/local thresholding (Otsu is global),
  layout analysis beyond line grouping (columns, tables, reading order
  across columns), spell correction, language modelling.
- Production accuracy claims of any kind. See TEST_PLAN.md for the
  measured fixture accuracy and its limits.

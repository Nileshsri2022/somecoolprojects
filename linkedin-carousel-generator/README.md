# linkedin-carousel-generator — Build Your Own LinkedIn Carousel Generator

Coding Challenges #21, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Turns a plain-text deck into a LinkedIn carousel: a PDF with one
1080 x 1080 page per slide, plus an HTML preview with the same
slides and prev/next navigation. Python 3 standard library only —
the PDF writer is hand-written (base-14 fonts need no embedding)
and JPEG images are embedded verbatim.

## Deck format

Slides are separated by a line containing exactly `---`. The first
non-empty line of a slide is its title (`# ` stripped); the rest
are body lines, `- ` lines are bullets. A slide may start with a
`!bg <path> [opacity]` directive for a per-slide background image
(JPEG only in PDF; default opacity 0.15).

```text
# Stop shipping features nobody asked for
- Talk to five users first
- Write down the one problem

---
# The interview script
Thirty minutes. Five questions. No feature talk.
```

## Usage

```sh
python3 carousel.py build deck.txt --pdf carousel.pdf --preview preview.html \
  --bg ffffff --fg 111111 --font Helvetica --font-size 36 \
  --author "Ada Lovelace" --handle "@ada" --avatar avatar.jpg
```

`--preview` is optional; `--pdf` defaults to `carousel.pdf`.
Colours are `RRGGBB` hex; fonts are `Helvetica`, `Helvetica-Bold`,
`Times-Roman`, `Courier`. Errors (bad colour/font/size, empty
deck, missing file, non-JPEG image for PDF) exit non-zero and
write no output file.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps (1080-square preview, profile,
colours/font/size, slide add + navigate, per-slide background
image with transparency, PDF export with xref verification),
plus every CLI error case. The sample JPEG in
`tests/fixtures/sample.jpg` is a genuine 8x8 JPEG generated with
ffmpeg for the embed tests.

## Divergences from the challenge page (all documented in `docs/`)

- No live GUI: the page leaves the shape open, and a CLI + HTML
  preview covers every numbered step while keeping layout and
  pagination unit-testable without a display server or browser.
- PDF-only JPEG embedding (PNG works in the HTML preview, where
  the browser decodes it); a PNG decoder was out of proportion.
- Avatar is a square, not a circle crop; text wrapping uses an
  estimated character width (stdlib has no font metrics); non-Latin-1
  characters render as `?` in PDF (base-14 font coverage).
- PowerPoint/DOCX export and LinkedIn API posting are the page's
  "Going Further" only and are not built.

# DESIGN — LinkedIn Carousel Generator

## Assumptions (stated up front, per ponytail rules)

1. The page leaves the implementation shape open (web app, desktop
   app, API, no GUI). A CLI + HTML-preview tool is the smallest
   shape that covers every numbered step, and keeps layout and
   pagination unit-testable without a browser or display server.
   A Tkinter GUI would add untestable surface and is not built.
2. Text measurement uses a fixed per-character width estimate
   (0.5 x font size for body, 0.55 x for the title) instead of real
   font metrics, because the standard library ships no font-metric
   data for the base-14 fonts. Wrapping is therefore approximate:
   lines are conservative (they fit inside the slide with margin
   in the common case) but a line measured short could overflow
   slightly for wide characters. This is documented, not hidden.
3. PDF pages are 1080 x 1080 points, matching the page's 1080 x 1080
   pixel square 1:1. LinkedIn accepts the resulting PDF as a
   document; points vs pixels only affect print size, not layout.
4. Only JPEG images are embedded in PDF output. A JPEG can be
   embedded verbatim with `/DCTDecode`; a PNG would need a decoder
   (zlib + unfiltering + colour-type handling) that is out of
   proportion for this project. PNGs still work in the HTML preview
   (the browser decodes them) and produce a clear error for PDF.
5. The avatar is drawn as a plain square, not cropped to a circle:
   PDF has no cheap circle-clip path in a minimal writer, and a
   square keeps the writer small. Documented as a divergence.

## Module layout (single file, `carousel.py`)

- `Slide` (dataclass): `title`, `body` (list of lines), `bg_image`
  (path or None), `bg_opacity` (float).
- `Theme` (dataclass): `bg`, `fg` (RGB triples), `font`, `font_size`,
  `author`, `handle`, `avatar`.
- `parse_hex(s) -> (r, g, b)` — validates `#RRGGBB` or `RRGGBB`.
- `parse_deck(text) -> list[Slide]` — splits on `---` lines, strips
  `# ` headings, extracts a leading `!bg` directive, drops empty
  slides, raises `ValueError` on an empty deck.
- `wrap_text(text, max_width_pt, font_size, char_factor) -> list[str]`
  — greedy word wrap on the width estimate; over-long words are
  hard-split so no line ever exceeds the width estimate.
- `layout_slide(slide, theme, index, total) -> list[TextLine]`
  — pure function: title line(s), body lines, author line, footer
  `N / total`, with x/y coordinates in points. No I/O, so it is
  directly unit-testable. Bullet lines keep their `- ` marker in
  PDF output because the `•` glyph is outside base-14 Latin-1
  coverage and would extract as `?`. Coordinates: 90 pt margin all round,
  title at top (below the avatar row when an author is set),
  body below the title, author at top-left, footer bottom-right.
- `escape_pdf(s)`, `build_pdf(deck, theme) -> bytes` — minimal PDF
  writer: catalog, pages, one page + content stream per slide,
  graphics-state object for the background-image opacity, JPEG
  XObject images (parsed header for width/height only, bytes copied
  verbatim). Objects are numbered deterministically; the xref table
  is computed from real byte offsets. PDF text uses UTF-8-escaped
  literal strings with `\(`, `\)`, `\\` escapes; characters outside
  Latin-1 are replaced with `?` (base-14 fonts have no Unicode
  coverage — documented divergence).
- `build_html(deck, theme) -> str` — one `<section class="slide">`
  per slide, inline styles from the theme, prev/next buttons and a
  counter driven by a few lines of vanilla JS, background images as
  `<img>` with CSS opacity. HTML-escaped text throughout.
- `main(argv) -> int` — argparse CLI, `build` subcommand only.
  Writes the PDF and/or HTML; on error prints to stderr, exits 1,
  and does not leave a partial output file behind (files are built
  fully in memory first).

## Pagination

`N / total` appears on every PDF page (footer) and in the HTML
counter. Slide order is input order; there is no reordering
feature (the page asks to add and navigate, not to reorder).

## What is deliberately NOT built

- PowerPoint / DOCX export, LinkedIn API posting (page's "Going
  Further" only).
- A live-editing GUI, drag-and-drop layout, or image cropping.
- PNG/WebP embedding in PDF, font embedding, or real font metrics.
- Automatic content splitting: the author decides slide breaks with
  `---`. (An auto-split helper would be speculative; the page asks
  the user to author slides.)

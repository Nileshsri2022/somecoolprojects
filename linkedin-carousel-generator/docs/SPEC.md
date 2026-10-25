# SPEC — LinkedIn Carousel Generator (Coding Challenges, entry 21)

Source page: https://codingchallenges.fyi/challenges/challenge-licq/
Slug used: `challenge-licq` (found by web search; the guessed
`challenge-linkedin-carousel-generator` form was NOT used — the search
result gave the real slug directly, no 404 was hit).

## What the page asks for

A tool that lets a user write text and get a carousel usable in a
LinkedIn post — i.e. a PDF document builder. Steps on the page:

- Step 0: pick a language, set up a project. (Python 3, stdlib only.)
- Step 1: slide preview + text box; preview updates with the text.
  Slide size 1080 x 1080 (the page's chosen square; max 4320 x 4320).
- Step 2: profile image (top-left corner) + name/handle beneath it.
- Step 3: background colour, foreground colour, font face and size,
  applied to all slides.
- Step 4: add slides and navigate through them, editing each slide's text.
- Step 5: per-slide background image, with high transparency
  (configurable).
- Step 6: export as PDF, one page per slide, reflecting font, colours,
  content and per-slide background image.
- Going further: PowerPoint, other formats, LinkedIn API posting —
  out of scope (see DESIGN.md).

## Input format (this implementation)

Plain text, one file, slides separated by a line containing exactly
`---` (with optional surrounding whitespace). Inside a slide:

- The first non-empty line is the title. A leading `# ` is stripped
  (Markdown-style heading), as is a leading `## `.
- Remaining non-empty lines are body lines. Lines starting with `- `
  are bullets; they keep the `- ` marker in PDF output (the `•`
  glyph is outside base-14 Latin-1 coverage).
- Empty input, or input with no non-empty slide, is an error.
- A slide with no body is allowed (title-only slide, e.g. a cover).

Example:

```
# Stop shipping features nobody asked for
- Talk to five users first
- Write down the one problem
- Then build

---
# The interview script
Thirty minutes. Five questions. No feature talk.
```

## Theme / deck options

- `--bg RRGGBB`, `--fg RRGGBB`: background / foreground colours,
  deck-wide (Step 3). Defaults: white background, near-black text.
- `--font NAME`: a PDF base-14 font name: `Helvetica`,
  `Helvetica-Bold`, `Times-Roman`, `Courier`. Default `Helvetica`.
  (Base-14 fonts need no embedding, which is what makes a
  stdlib-only PDF writer possible.)
- `--font-size N`: body font size in points, default 36. Title is
  1.6x body size. Must be > 0.
- `--author NAME` / `--handle @name`: printed on every slide
  (Step 2, text part). `--avatar PATH` is accepted and, when the
  file is a JPEG, embedded as a small square in the top-left of
  every PDF page; in the HTML preview any image path is referenced
  directly (see Divergences).
- Per-slide background image: a slide may carry a directive line
  `!bg <path> [opacity]` as its first line (opacity 0..1, default
  0.15 — the page's "high transparency"). The directive is not
  rendered as text. JPEG only in PDF (see Divergences).

## Outputs

- PDF (`--pdf out.pdf`, default `carousel.pdf`): one 1080 x 1080 pt
  page per slide, background fill, title, wrapped body, author line,
  footer page number `N / total`, optional JPEG background image
  drawn full-bleed under the text at the requested opacity, optional
  JPEG avatar top-left. Hand-written minimal PDF writer (objects,
  xref table, trailer) — no third-party PDF library exists in the
  standard library.
- HTML preview (`--preview out.html`): one 1080 x 1080 px slide
  section per slide with the same colours/font/text, prev/next
  navigation and a slide counter, plus per-slide background images
  referenced by path. This is the Step 1/Step 4 "preview + navigate"
  surface in a form that is fully testable without a GUI toolkit or
  a browser: the slide model, layout and pagination are pure
  functions, and the HTML is plain text output.
- CLI: `python3 carousel.py build INPUT [--pdf OUT] [--preview OUT]
  [--bg HEX] [--fg HEX] [--font NAME] [--font-size N]
  [--author NAME] [--handle HANDLE] [--avatar PATH]`

## Errors

Bad hex colour, unknown font, non-positive font size, opacity
outside 0..1, missing input file, empty deck, unreadable or
non-JPEG image for PDF output: all exit non-zero with a message
on stderr and write no output file.

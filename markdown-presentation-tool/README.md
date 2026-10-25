# Markdown Presentation Tool

Write a presentation in Markdown, present it in a browser, build a
static HTML deck, or export a PDF handout. Built for the Coding
Challenges task [Build Your Own Markdown Presentation Tool](https://codingchallenges.fyi/challenges/challenge-md-to-slides)
(Go `Present` / Slidev style).

Python 3 standard library only — no dependencies to install.

## Usage

```sh
python3 mdslides.py new my-talk --title "My Talk"
cd my-talk
# edit slides/slides.md — a line containing exactly `---` starts a new slide
python3 ../mdslides.py serve .            # present, with live reload
python3 ../mdslides.py serve . --raw      # Step 2: raw-text rendering
python3 ../mdslides.py build . -o deck.html
python3 ../mdslides.py export-pdf . -o deck.pdf
```

`serve` binds `127.0.0.1` (default port 8000, `--port 0` for an
ephemeral port). Use arrow keys / Prev / Next to move between
slides; editing `slides/slides.md` reloads the browser page.

## What it supports

- Slide splitting on `---`; headings, paragraphs, bullets, ordered
  lists, fenced code blocks, blockquotes, inline bold / italic /
  code / links / images (see `docs/SPEC.md` for the exact dialect).
- Default HTML template + CSS, overridable per-piece via
  `template/template.html` and `template/style.css` (Step 4:
  delete one file to fall back to the built-in default for it).
- PDF export (Step 5) — a genuine multi-page PDF, but text-based
  (Helvetica), not a pixel copy of the HTML theme; see SPEC for
  this and other deliberate divergences.

## Not built

PowerPoint / Google Slides export and running example code
inside slides — both are "Going Further" on the challenge page,
not core steps. No GUI presenter; delivery is via the browser.

## Layout

```
mdslides.py          # the whole tool (stdlib only)
docs/SPEC.md         # challenge steps, divergences, scope limits
docs/DESIGN.md       # design notes
docs/TEST_PLAN.md    # test coverage map
tests/test_mdslides.py
```

## Tests

```sh
python3 -m unittest discover -s tests -v
```

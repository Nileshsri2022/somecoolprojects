# SPEC — Markdown Presentation Tool

Source challenge: https://codingchallenges.fyi/challenges/challenge-md-to-slides
(Read 2026-10-25; page live, not a 404.)
The challenge asks for a Go `Present`- / Slidev-style tool: author a
presentation in Markdown, then deliver it with the tool.

## Commands (single program, Python 3 standard library only)

```
python3 mdslides.py new <dir> [--title "My Talk"]
python3 mdslides.py serve <project-dir> [--port 0] [--raw]
python3 mdslides.py build <project-dir> [-o deck.html]
python3 mdslides.py export-pdf <project-dir> [-o deck.pdf]
python3 mdslides.py --help
```

`new` scaffolds a project; `serve` presents it in a browser;
`build` writes a self-contained static HTML deck; `export-pdf`
writes a PDF handout. All commands are headless-testable except the
browser viewing itself (the server is tested over HTTP).

## Challenge steps — status

| Step | Page asks | Built |
|------|-----------|-------|
| Step 0 | Pick language / set up project | Yes — Python 3 stdlib only, one main file `mdslides.py` |
| Step 1 | `new` creates folder structure: slides, template/customisation, images, `.git`, stack config, README explaining use | Yes — `slides/slides.md`, `template/` (with default `template.html` + `style.css`), `images/`, `config.json`, project `README.md`, `.git` via `git init` |
| Step 2 | Web server rendering Markdown as raw text + live reload on edit | Yes — `--raw` renders escaped raw text per slide; normal mode renders HTML. Every request re-reads the source file, and the served page polls `/__version__` and reloads when the source changes |
| Step 3 | Render Markdown as HTML with a default template | Yes — embedded default template + CSS; headings, paragraphs, bullets, ordered lists, code fences, inline bold/italic/code/links/images, blockquotes |
| Step 4 | User-defined template directory, falling back to the default for missing pieces | Yes — per-piece fallback: `template/template.html` and `template/style.css` are used when present, otherwise the embedded default for that piece |
| Step 5 | Export slides to PDF | Yes — `export-pdf` writes a real multi-page PDF (one page per slide), generated with stdlib-only PDF code |
| Going Further | PowerPoint / Google Slides export; running example code | NOT built (see below) |

## Markdown dialect (documented subset)

- Slide separator: a line containing exactly `---` (surrounding
  whitespace allowed). A document with no separator is one slide.
- Headings `#` … `######`, paragraphs, unordered lists (`-`, `*`),
  ordered lists (`1.` …), fenced code blocks (``` … ```, optional
  language tag kept as a CSS class), blockquotes (`>`).
- Inline: `**bold**`, `*italic*`, `` `code` ``, `[text](url)`,
  `![alt](src)`.
- HTML in the source is escaped, never passed through (no raw-HTML
  injection via slide content).
- A slide's title is its first heading, else "Slide N"; the deck
  title is `config.json`'s `title`, else the first slide's title,
  else "Untitled Presentation".

## Project layout created by `new`

```
<project>/
  config.json          {"title": ..., "source": "slides/slides.md",
                        "template_dir": "template"}
  slides/slides.md     example deck (3 slides)
  template/template.html   default HTML shell (customisable)
  template/style.css       default CSS (customisable)
  images/              (empty, for slide images)
  README.md            how to edit, serve, build, export
  .git/                created by `git init`
```

`serve`/`build`/`export-pdf` locate the source as: `config.json`
`source` if set, else `slides/slides.md`, else `slides.md` in the
project root, else any `*.md` directly under `slides/`.

## Deliberate divergences

1. **PDF is text-based, not a print of the HTML deck.** With stdlib
   only (no browser, no ReportLab, no WeasyPrint) there is no HTML
   renderer available. `export-pdf` therefore emits a genuine PDF
   (header, objects, xref table, trailer) with one page per slide,
   rendering headings/bullets/code as wrapped Helvetica text. It is
   a readable handout, not a pixel-faithful copy of the HTML theme.
   The HTML deck itself also carries print CSS so a browser can
   print it to PDF as an alternative.
2. **`.git` via the `git` binary, not a from-scratch git writer.**
   The page offers implementing Build-Your-Own-Git Step 1 as an
   option ("you could invoke git or …"); this build invokes git.
   If `git` is absent, `new` still scaffolds everything else and
   prints a warning instead of failing.
3. **Template placeholders are minimal.** The shell uses
   `{{title}}`, `{{style}}`, `{{slides}}` (and `{{slide_count}}`).
   There is no Slidev-style theme/layout system (multiple named
   layouts, per-slide frontmatter layouts) — the page mentions
   Slidev themes/layouts as inspiration, but its own steps only
   require a default template plus a user template directory.
4. **Live reload is poll-based, not a websocket.** The served page
   fetches `/__version__` (a hash of the source file) every second
   and reloads on change. No websocket dependency, same user-visible
   effect, and trivially testable over HTTP.
5. **No frontmatter / speaker-notes / per-slide layout syntax.**
   The page does not specify any; none is invented. Content after
   a slide's body is just body content.

## NOT built (honest scope limits)

- PowerPoint (`.pptx`) export, Google Slides export — "Going
  Further" only; not claimed.
- Running example code inside slides (Present's `play` feature) —
  "Going Further" only; code blocks are displayed, never executed.
- A GUI presenter / desktop app — the page's delivery mechanism is
  a web server + browser, which is what is built.
- A full CommonMark implementation — tables, footnotes, nested
  lists, task lists, strikethrough, autolinks, reference links,
  and raw HTML are not supported (see TEST_PLAN for the exact
  covered subset). Nested lists render as flat list items.
- Slide transitions/animations beyond keyboard/arrow navigation
  and a plain slide counter; no presenter view, no timer.
- No network fetching of images: image `src` values are passed
  through as-is (relative paths resolve against the project dir
  when served/built from it only if the user serves the file;
  the static deck does not embed images).

## Success criteria

- `new` produces the full layout above and a `.git` directory
  when git is available.
- `serve` returns the slides as HTML (or raw text with `--raw`)
  and reflects an edit without a server restart.
- `build` writes a standalone HTML file containing every slide.
- `export-pdf` writes a file starting with `%PDF-` and ending
  with `%%EOF`, one page per slide.
- Full unittest suite green (see TEST_PLAN.md).

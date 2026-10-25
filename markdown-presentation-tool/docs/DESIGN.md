# DESIGN — Markdown Presentation Tool

## Overview

One file, `mdslides.py`, Python 3 standard library only. No
third-party Markdown, templating, PDF, or server library is used,
so the tool runs anywhere Python 3.8+ exists.

```
mdslides.py
  ├── CLI parsing (argparse, subcommands: new / serve / build / export-pdf)
  ├── split_slides(text)          --- separator -> list[str]
  ├── parse_slide(text)           markdown subset -> Slide(title, html, plain_lines)
  ├── render_inline(text)         bold/italic/code/links/images, HTML-escaped
  ├── render_markdown(text)       block parser -> HTML string
  ├── load_template(project_dir)  per-piece fallback (file vs embedded default)
  ├── render_deck(...)            template shell + per-slide <section> markup
  ├── DeckHTTPRequestHandler      http.server; re-reads source per request;
  │                               /__version__ returns sha1 of source bytes
  ├── write_pdf(slides, path)     minimal hand-rolled PDF writer
  └── new_project(dir, title)     scaffold + `git init` (best effort)
```

## Markdown parsing

Two passes, both line-oriented and deliberately small:

1. `split_slides`: split on lines whose stripped form is exactly
   `---`. Blank leading/trailing slides produced by leading or
   trailing separators are dropped; interior empty slides are kept
   (they are a real, if empty, slide) — actually: empty slides
   between separators are dropped too, so `a\n---\n---\nb` is two
   slides, not three. This is recorded here because it is a
   judgement call, not something the page specifies.
2. Block parser: fenced code blocks are recognised first (a fence
   swallows everything until the closing fence, so `---` inside a
   code block never splits a slide — splitting happens before
   block parsing, so this needs care: see below).
   Paragraphs, headings, lists (consecutive `-`/`*` lines form one
   `<ul>`, consecutive `1.` lines form one `<ol>`), blockquotes
   (consecutive `>` lines form one `<blockquote>`).

Ordering note: slide splitting happens on raw lines *before*
code-fence awareness, so a `---` line inside a fenced code block
would split the slide. This is a known limitation of the simple
splitter, documented in SPEC.md's dialect section by omission
(the dialect defines `---` as the separator unconditionally).
In practice authors put code fences on their own slides or avoid
a bare `---` inside code. The test suite pins the unconditional
behaviour rather than pretending otherwise.

Inline rendering: escape HTML first (`&`, `<`, `>`), then apply
code spans, images, links, bold, then italic, in that order, so
markup inside a code span is not reinterpreted.

## Templates

Embedded defaults:

- `DEFAULT_CSS`: dark slide background, centred content column,
  large headings, readable code blocks, print rules (`@media
  print` shows one slide per printed page).
- `DEFAULT_TEMPLATE`: `<!doctype html>` shell with
  `{{title}}`, `<style>{{style}}</style>`, and `<main>` holding
  one `<section class="slide">` per slide, plus a small script:
  arrow-key / click navigation (only one slide visible at a
  time), a `Slide N / M` counter, and the live-reload poller
  (only included when serving, not in `build` output, so the
  static file has no dangling `/__version__` request).

`load_template(project_dir)`: reads `config.json` for
`template_dir` (default `template`); if
`<template_dir>/template.html` exists it is used, else the
embedded shell; same independently for `style.css` vs embedded
CSS. A user template may omit any placeholder; missing
`{{slides}}` simply yields a deck with no slides rendered, and
`{{style}}`/`{{title}}` are substituted when present. Unknown
`{{...}}` tokens are left untouched.

Serving: `http.server.ThreadingHTTPServer` on an ephemeral port
when `--port 0` is given (the default is 8000; tests always pass
an ephemeral port). Only two routes exist: `/` (the deck, or
raw-text rendering with `--raw`) and `/__version__` (JSON
`{"version": "<sha1>"}`). Any other path returns 404. The server
binds 127.0.0.1 by default, not 0.0.0.0.

## PDF writer

`write_pdf` builds a minimal PDF 1.4 document by hand:

- One page object per slide, Letter size (612 x 792 pt), 54 pt
  margins, Helvetica / Helvetica-Bold.
- The slide title at 20 pt bold, body lines at 11 pt, wrapped at
  ~95 characters (measured by a fixed 6 pt/char approximation —
  Helvetica is proportional, so this is approximate wrapping,
  good enough for a handout).
- Bullets render with a `•` prefix, code lines in Courier 10 pt.
- PDF strings are escaped (`\`, `(`, `)`); non-Latin-1 characters
  are replaced with `?` (documented limit: no Unicode font is
  embedded, stdlib has no font tooling).
- Objects, byte offsets, xref table and trailer are computed
  programmatically and verified by tests (header, `%%EOF`,
  `/Count N` page count, title text present).

## `new` scaffolding

Writes `config.json`, `slides/slides.md` (a 3-slide example
deck demonstrating headings, bullets, and a code block),
`template/template.html` and `template/style.css` (copies of the
embedded defaults, so the user has something concrete to edit),
an empty `images/` directory, and a project `README.md`.
Then runs `git init -q <dir>` via subprocess; failure (git
missing, or git erroring) warns on stderr and does not abort.
Re-running `new` into an existing non-empty directory refuses
unless `--force` is given, to avoid clobbering a user's deck.

## Error handling

- Missing project dir / missing source file: clear stderr
  message + exit code 2 (argparse-style usage errors are 2 as
  well; unexpected internal errors propagate as tracebacks).
- `build`/`export-pdf` refuse to write over the source markdown
  file itself (same-path check).
- `serve` prints the URL and serves until Ctrl-C (KeyboardInterrupt
  exits cleanly with code 0).

# TEST_PLAN — Markdown Presentation Tool

Run: `python3 -m unittest discover -s tests -v` from the project
directory. All tests use only the standard library (`unittest`,
`tempfile`, `urllib`, `threading`); HTTP tests bind port 0
(ephemeral) and shut the server down in `tearDown`.

## Coverage map

### Slide splitting (`TestSplitSlides`)
- `---` splits into the right number of slides, in order.
- No separator → one slide.
- Leading/trailing separators do not create empty slides.
- Interior empty slides are dropped (pinned behaviour).
- Whitespace around `---` still splits; `----` and `--` do not.

### Inline + block rendering (`TestRenderMarkdown`)
- Headings h1–h6; paragraph wrapping; HTML escaping (`<script>`
  in source is escaped, never emitted raw).
- Unordered lists (`-` and `*`), ordered lists, consecutive items
  grouped into one `<ul>`/`<ol>`.
- Fenced code blocks, language class preserved, code escaped.
- Blockquotes.
- Inline bold, italic, code spans, links, images; markup inside
  a code span is not reinterpreted.
- Slide title: first heading, else "Slide N".

### Templates (`TestTemplates`)
- Embedded default contains `{{slides}}` placeholder handling
  and renders every slide as a `<section class="slide">`.
- User `template.html` overrides the shell; user `style.css`
  overrides the CSS; deleting one piece falls back to the
  embedded default for that piece only (per-piece fallback,
  Step 4).
- `build` output is a single file containing all slide titles
  and no live-reload poller.

### `new` scaffolding (`TestNewProject`)
- Full layout created: `config.json`, `slides/slides.md`,
  `template/template.html`, `template/style.css`, `images/`,
  `README.md`, `.git/` (git is present in the test environment;
  the test skips the `.git` assertion if `git` is not found).
- Example deck has 3 slides when split.
- Refuses a non-empty existing directory without `--force`.

### HTTP serving + live reload (`TestServe`)
- `GET /` returns 200 with the rendered slide HTML.
- `GET /?anything` still serves the deck (query ignored).
- `GET /nope` returns 404; `/__version__` returns JSON with a
  `version` field.
- Raw mode (`--raw` equivalent) returns escaped raw markdown
  inside `<pre>`, not rendered HTML headings.
- Live reload: after editing the source file on disk, a second
  `GET /` returns the new content and `/__version__` changes —
  with no server restart.

### PDF export (`TestExportPdf`)
- Output starts with `%PDF-`, ends with `%%EOF`.
- `/Count 3` for a 3-slide deck; slide titles appear in the body.
- Non-empty file for a single-slide deck; works from a project
  dir (via the CLI function, not just the library call).

### CLI end-to-end (`TestCli`)
- `new` → `build` → file exists and contains slide content.
- `new` → `export-pdf` → valid PDF header.
- Missing project dir exits non-zero with a message on stderr.
- `--help` exits 0.

## Not covered (honest gaps)

- Browser rendering / visual appearance: no headless browser is
  used; HTML is asserted as text, not rendered.
- PDF visual fidelity: only structural checks (header, trailer,
  page count, title bytes) — glyph layout is not verified.
- Concurrent multi-client serving beyond the threading server's
  own behaviour.
- The `git init` failure path when git is absent (environment
  has git; the warning branch is code-reviewed, not executed).

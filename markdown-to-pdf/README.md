# markdown-to-pdf — Build Your Own Markdown To PDF Editor

Coding Challenges entry 67, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Turns Markdown into a PDF and an HTML preview with the same
content and styling, with a terminal editing loop and a file
watcher in place of a GUI. Python 3 standard library only — the
PDF writer is hand-written (base-14 fonts need no embedding),
as in the LinkedIn Carousel project in this repo.

Challenge page: https://codingchallenges.fyi/challenges/challenge-md-to-pdf
(slug note: `challenge-markdown-to-pdf` and
`challenge-markdown-to-pdf-editor` both 404; the real slug was
found via the site's `tags/beginner` index).

## What it covers (the page's steps)

- Step 1 — Edit: `edit` subcommand, a terminal editing loop
  (`print`, `append`, `insert N`, `replace N`, `delete N`,
  `pdf`, `save`, `quit`), or just pass a source file to `convert`.
- Step 2 — Preview: `preview` writes an HTML preview; `convert
  --preview` writes PDF + HTML together.
- Step 3 — Customise: `--font helvetica|times|courier`,
  `--font-size`, `--heading-scale`, `--bg`/`--fg` (RRGGBB),
  `--page a4|letter`.
- Step 4 — Export: hand-written PDF that matches the preview.

Markdown supported: headings H1–H6, bold `**`/`__`, italic
`*`/`_`, inline code, links, images (placeholder line, see
below), unordered/ordered/nested lists, fenced code blocks,
blockquotes, horizontal rules, hard line breaks.

## Usage

```sh
python3 md2pdf.py convert doc.md -o doc.pdf --preview doc.html
python3 md2pdf.py convert doc.md --page letter --font times \
  --font-size 14 --bg fffff8 --fg 222222
python3 md2pdf.py preview doc.md -o doc.html
python3 md2pdf.py edit doc.md --pdf doc.pdf
python3 md2pdf.py watch doc.md -o doc.pdf --preview doc.html
```

`convert` without `-o` writes `<input-basename>.pdf`. Errors
(missing file, bad colour/font/page/size) exit non-zero and
write no output file.

Editor example (lines until a lone `.` for multi-line commands):

```text
$ python3 md2pdf.py edit doc.md --pdf doc.pdf
md> append
# New section
Some text.
.
md> pdf
PDF written.
md> quit
Saved doc.md
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the parser, HTML preview, PDF structure (header,
xref offsets, `%%EOF`), `pdftotext` text extraction, page sizes,
customisation flags, CLI error cases, and the editor loop, all
with temp files only. Watch mode is covered indirectly: it calls
the same `convert()` the CLI tests exercise.

## Divergences from the challenge page (all in `docs/SPEC.md`)

- No GUI / web app: the page leaves the tool shape open and
  explicitly blesses a CLI + source-file + HTML-preview shape.
- No live split-pane preview inside `edit`; rebuild on `pdf`,
  or use `watch` for rebuild-on-change.
- Images are not fetched or embedded: `![alt](url)` renders as
  `[Image: alt]`.
- Links are styled (blue, underlined) in the PDF but carry no
  clickable annotation; the HTML preview keeps real `<a href>`.
- Non-Latin-1 characters become `?` in the PDF (base-14 fonts
  have no Unicode coverage); the HTML preview keeps them.
- No Word/LaTeX export (optional "Going Further" items).
  HTML export and A4/Letter page sizes are implemented.

# SPEC — Markdown To PDF Editor (somecoolprojects entry 67)

Source page: https://codingchallenges.fyi/challenges/challenge-md-to-pdf
("Build Your Own Markdown To PDF Editor").
Slug note: the first guesses `challenge-markdown-to-pdf` and
`challenge-markdown-to-pdf-editor` both 404. The real slug was found
via the site's `tags/beginner` index, whose "Build Your Own Markdown
To PDF Editor" entry links to `challenge-md-to-pdf`.

## What the page asks for (numbered steps)

- Step 0: repo + README.md describing the challenge and how to use
  the solution.
- Step 1 — Edit: a window (in the broadest sense) in which the user
  can edit markdown. For a CLI tool the page explicitly allows
  "specify a source file" instead of building a full text editor.
- Step 2 — Preview: preview the rendered markdown in a separate
  window; for a CLI tool the page explicitly allows "a preview as
  HTML" or rendering on the command line (it cites Glow as
  inspiration for terminal rendering).
- Step 3 — Customise: let the user select the font, the font sizes
  for headings and text, the background colour of the document, and
  anything else reasonably useful.
- Step 4 — Export: export the rendered document as a PDF that looks
  just like the preview.
- Going further (optional): export as HTML / Word / LaTeX; different
  page sizes (Letter, A4, ...). HTML export and page sizes are
  implemented here; Word/LaTeX are not (see Divergences).

## Markdown syntax covered (the page's "Basic Syntax" recap)

- Headings `#` … `######` (a space after the hashes is required;
  `#no-space` is plain text, matching CommonMark).
- Bold `**text**` and `__text__`; italic `*text*` and `_text_`;
  inline code `` `code` ``; links `[text](url)`; images
  `![alt](url)`.
- Unordered lists `-`, `*`, `+` (one marker per item); ordered
  lists `1.`, `2.`, ... Nested lists by 2-space indent per level.
- Fenced code blocks `` ``` `` (optional info string ignored).
- Also implemented (small, standard, needed for real documents):
  paragraphs, blank-line separation, horizontal rule `---` on its
  own line, blockquotes `> `, and hard line breaks via two trailing
  spaces inside a paragraph (rendered as a new line).

## CLI contract

```
python3 md2pdf.py convert INPUT.md [-o OUT.pdf]
    [--preview OUT.html] [--page a4|letter] [--font helvetica|times|courier]
    [--font-size N] [--heading-scale F] [--bg RRGGBB] [--fg RRGGBB]
python3 md2pdf.py preview INPUT.md [-o OUT.html] [same style flags]
python3 md2pdf.py edit INPUT.md [--pdf OUT.pdf] [--preview OUT.html]
    [same style flags]
python3 md2pdf.py watch INPUT.md -o OUT.pdf [--preview OUT.html]
    [--interval SECONDS] [same style flags]
```

- `convert` writes the PDF (default: input basename with `.pdf`)
  and, with `--preview`, an HTML file with the same content and
  styling. Exit code 0 on success.
- `preview` writes only the HTML preview.
- `edit` is the Step 1 editor: a terminal editing loop over the
  source file (see DESIGN.md). Commands: `print`, `append`,
  `insert N`, `replace N`, `delete N`, `pdf`, `save`, `quit`.
  `edit` saves on `save`/`pdf`/clean `quit` only when the buffer
  changed and the user confirms (or stdin is not a TTY, where
  `quit` saves without prompting so scripts can drive it).
- `watch` rebuilds PDF (and preview, if given) whenever the input
  file's mtime changes, until interrupted (Ctrl-C).
- Errors — missing input file, unreadable file, bad colour
  (`RRGGBB` hex only), unknown font, non-positive font size,
  unknown page size, unknown subcommand — exit non-zero with a
  message on stderr and write no output file.
- Python 3 standard library only. No external PDF library: the PDF
  writer is hand-written (same approach as the LinkedIn Carousel
  project in this repo), using PDF base-14 fonts, which need no
  embedding.

## PDF contract

- A4 (595 x 842 pt) by default, Letter (612 x 792 pt) with
  `--page letter`; 54 pt margins; text flows across pages.
- Fonts: Helvetica / Times-Roman / Courier families, with bold,
  oblique, and bold-oblique variants selected per span.
- Heading sizes derive from the body size: H1 = body x 2.0,
  H2 = x 1.67, H3 = x 1.33, H4 = x 1.17, H5 = x 1.0, H6 = x 0.92,
  each multiplied by `--heading-scale` (default 1.0).
- The file must start with `%PDF-`, contain a correct `xref`
  table and `trailer` with matching byte offsets, and end with
  `%%EOF`. Text must be extractable with `pdftotext` (poppler)
  for all ASCII test documents.
- Background colour fills every page; foreground colour is the
  body text colour; links render in blue; code spans/blocks render
  in the Courier family on a light-grey background.

## Divergences from the page (honest, documented)

- No GUI / web app: the page leaves the tool shape open ("online,
  command line, or offline GUI — the choice is yours") and
  explicitly blesses a CLI + source-file + HTML-preview shape.
  This build is a CLI: terminal editing loop + HTML preview + PDF.
  There is no windowed editor and no live split-pane GUI.
- No live preview inside `edit`: the loop rebuilds the PDF/preview
  on the `pdf` command and `watch` rebuilds on every save; there
  is no auto-refreshing split pane.
- Images are not fetched or embedded: `![alt](url)` renders as a
  placeholder line `[Image: alt]`. Fetching remote images would
  need network access and embedding raster images is out of scope
  for the hand-written writer in this build.
- Links are styled (blue, underlined) but carry no clickable PDF
  annotation (`/Annots` + `/URI`); the URL is preserved in the
  HTML preview as a real `<a href>`.
- Non-WinAnsi characters (outside Latin-1) are replaced with `?`
  in the PDF, because base-14 fonts have no embedded Unicode
  coverage. The HTML preview keeps the original characters.
- No Word (.docx) or LaTeX export (listed under "Going Further",
  optional). HTML export and A4/Letter page sizes are done.

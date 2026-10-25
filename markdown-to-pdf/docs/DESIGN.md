# DESIGN — Markdown To PDF Editor

## Assumptions (stated before coding, ponytail rule)

1. The page's four steps map cleanly onto a CLI: source file =
   Step 1's allowed alternative, HTML file = Step 2's allowed
   alternative, flags = Step 3, hand-written PDF = Step 4.
2. One main file (`md2pdf.py`) is enough: parser, HTML renderer,
   PDF writer, and CLI/edit-loop are small and share one block
   model. Splitting them would add import plumbing for no gain.
3. Only the page's recap syntax plus the small set in SPEC.md
   (hr, blockquote, hard break) is in scope. No tables, footnotes,
   reference links, or Setext headings — they are not on the page.
4. Word wrap must be by measured width, not character count, or
   the PDF will not "look just like the preview". Base-14 AFM
   widths are therefore tabulated for Helvetica and Times; Courier
   is fixed-width (600/1000 em). Bold/oblique share the regular
   widths, which is true of the core-font metrics to within the
   rounding this tool needs.
5. Tests must not depend on a GUI or a browser: PDF validity is
   checked structurally (header, xref offsets, `%%EOF`) and by
   `pdftotext` text extraction when poppler is present, with
   byte-level fallbacks otherwise. All tests use temp files.

## Block model

`parse(text) -> list[Block]`, where a block is one of:

- `("heading", level, spans)` — level 1..6
- `("para", spans)`
- `("ul", items)` / `("ol", items)` — item = `(spans, subblocks)`
  so nested lists survive; a nested list is a subblock of its item
- `("code", text)` — fenced block, language ignored
- `("quote", spans)` — one `> ` line per block (consecutive `> `
  lines merge into one paragraph-like block)
- `("hr",)` — a line that is exactly `---`, `***`, or `___`
  (only when it cannot be read as a list item / Setext — there is
  no Setext support, so the rule is just: the whole line matches)

Inline parsing (`parse_inline`) turns a line into spans:
`("text"|"bold"|"italic"|"bolditalic"|"code"|"link", text, url?)`.
It is a single left-to-right scan: code spans are recognised
first (their contents are never re-scanned), then images
(`![alt](url)` -> a link span flagged as image, rendered as a
placeholder), then links, then `**`/`__` bold, then `*`/`_`
italic. Unmatched delimiters are left as literal text — a
deliberate choice: silently dropping user text would be worse
than showing a stray `*`.

List parsing is line-based with indent tracking: an item's
continuation lines (indented past the marker) join the item;
a deeper-indented list becomes a subblock. Ordered markers are
renumbered on output (input numbers are ignored, so `1. 1. 1.`
still renders 1, 2, 3).

## Rendering — shared layout, two back ends

Both back ends consume the same block list, so preview and PDF
cannot drift apart in content (only in fonts/metrics, which is
inherent to PDF vs browser rendering).

- HTML: blocks -> elements (`h1`..`h6`, `p`, `ul`/`ol`/`li`,
  `pre`/`code`, `blockquote`, `hr`), spans -> `strong`/`em`/
  `code`/`a`. One `<style>` block carries the customisation
  (font family, sizes, bg/fg). Escaped with `html.escape`.
- PDF: blocks -> flowed lines. `wrap_spans` splits spans into
  words (keeping each word's style), then greedily packs words
  into lines of at most the text width, measured with the AFM
  tables at the current size. A page break starts a new page
  when the next line would cross the bottom margin; headings
  keep with the following line where possible (a heading alone
  at the bottom of a page is moved to the next page).
- PDF content streams use `BT/ET`, `Tf`, `Td`, `Tj` per fragment
  (one `Tj` per span-fragment, so bold/italic/code mid-line work)
  and `re f` rectangles for the page background and code-block
  shading. Strings are PDF-escaped (`\`, `(`, `)`) and encoded
  Latin-1 with `?` replacement (see SPEC divergences).

## PDF writer (hand-written, no library)

Objects, in order: catalog, pages, one page + one content stream
per page, then font objects (Helvetica, Helvetica-Bold,
Helvetica-Oblique, Helvetica-BoldOblique, Times-*, Courier —
only the families actually used are emitted, but the resource
dictionary maps fixed names F1.. so the code stays simple:
F1 regular, F2 bold, F3 oblique, F4 bold-oblique of the chosen
family, F5 Courier for code). Offsets are recorded as bytes are
written, then a `xref` table and `trailer` with `/Size` and
`/Root` are appended, ending in `%%EOF`. This is the same shape
as the carousel project's writer, verified there by xref checks.

## Editor loop (`edit`)

`edit_loop(lines, instream, outstream, on_pdf)` is pure over
streams so tests can drive it without a TTY: it prints a numbered
listing on `print`, and mutates the line list on `append`
(lines until a lone `.`), `insert N` / `replace N` (same `.`
terminated input), `delete N`. `pdf` calls the callback (the
CLI wires it to a real convert); `save`/`quit` return the final
lines. The CLI only writes the file back when the buffer changed.
Prompting on dirty `quit` happens only on a real TTY; piped
input saves unconditionally, so scripted sessions terminate.

## Watch mode

Polls the input file's mtime every `--interval` seconds
(default 1.0) and rebuilds on change. Polling, not inotify:
stdlib only, and polling is portable. It rebuilds via the same
`convert()` function as the CLI, so watch output is identical
to a manual convert. Stops cleanly on KeyboardInterrupt.

## What was deliberately NOT built

- No GUI, no web server, no live split-pane preview (page
  allows CLI shape; see SPEC).
- No image fetching/embedding, no clickable link annotations,
  no .docx/.tex export, no tables/footnotes (all documented in
  SPEC as divergences, not silently missing).

# DESIGN — Ebook Reader

Single file: `ebook_reader.py` (Python 3 standard library only:
`zipfile`, `xml.etree.ElementTree`, `html.parser`, `json`, `re`,
`textwrap`, `argparse`, `urllib`, `dataclasses`). No third-party deps.

## EPUB parsing (`parse_epub`)

EPUB = ZIP. Parsing is namespace-agnostic: every XML tag is reduced to
its local name (`{ns}tag` -> `tag`), so EPUB 2 and EPUB 3 package
documents parse with the same code.

1. Read `META-INF/container.xml`, take the first `rootfile`
   `full-path` (default `OEBPS/content.opf` if container is missing).
2. Parse the OPF: `metadata` -> `dc:title`, `dc:creator`, `dc:language`,
   `dc:identifier` (first of each; missing title -> filename stem,
   missing author/language -> `""`); `manifest` -> id -> (href, media-type);
   `spine` -> ordered itemrefs (skip `toc` item and any `linear="no"`);
   cover = manifest item with `properties="cover-image"` or id `cover`.
3. Resolve each spine href relative to the OPF directory inside the ZIP.
   For each content file, strip the XHTML to text (below) and derive a
   chapter title from the first `<h1>`/`<title>`/heading, else the href
   basename.
4. Table of contents, in preference order:
   a. EPUB 3 nav document: the manifest item with
      `properties` containing `nav`; parse its `<nav epub:type="toc">`
      links (`href`, link text) in document order.
   b. EPUB 2 NCX: the spine's `toc` attribute (or manifest id `ncx`);
      walk `navMap/navPoint` recursively, `navLabel/text` + `content src`
      (fragment after `#` stripped, matched to a chapter by href).
   c. Fallback: one TOC entry per spine chapter.
   TOC entries carry `title`, `chapter_id` (or `None` if unmatched)
   and `href`.
5. Stylesheets: manifest items with media-type `text/css` are recorded
   on `Book.stylesheets`; their rules are not interpreted.

Errors: missing/invalid ZIP, missing container rootfile target, missing
OPF, or a spine item absent from the ZIP raise `EpubError` (a
`ValueError` subclass). A book with no spine chapters parses but has
zero chapters — callers treat that as an empty book, not a crash.

## XHTML -> text (`_XhtmlToText`, `html.parser.HTMLParser`)

Block elements (`p`, `h1`–`h6`, `div`, `section`, `blockquote`, `li`,
`tr`, `br`, `hr`) flush the current line; headings emit their text on
its own line; `li` items are prefixed with `"- "`; `script`/`style`
content is dropped; entities are unescaped by the parser; runs of
blank lines collapse to one. Inline tags contribute only their text.

## Pagination and reading (`paginate`, `Reader`)

`paginate(text, width, lines_per_page)` wraps paragraphs with
`textwrap` at `width` (never below 20) and groups wrapped lines into
pages of `lines_per_page` lines. Repagination never changes the
underlying text, only its line breaks — that is the reflow guarantee.

`Reader(book, theme)` holds `chapter_index` / `page_index`, rebuilds
pages for the current chapter on theme/width change, and offers
`next_page`, `prev_page`, `next_chapter`, `prev_chapter`,
`goto_chapter(id_or_index)`, `goto_toc(title)`, `current_page_text()`
(theme-rendered), and `progress` = characters before the current page
/ total book characters, as a float in [0, 1]. Searching within a book
(`search_in_book`) is a case-insensitive substring scan per chapter.

## Library (`Library`, `Book`)

`Book` is a dataclass: `path`, `title`, `author`, `language`,
`identifier`, `chapters` (list of `Chapter`: `id`, `title`, `href`,
`text`), `toc` (list of `TocEntry`), `cover_href`, `stylesheets`.
`total_chars` and `chapter_by_id` are helpers.

`Library` keeps an insertion-ordered dict keyed by the book's absolute
path. `import_epub(path)` parses and stores; `import_text(path)` wraps
a `.txt` file as one chapter. `list_books(sort_by="title"|"author")`
sorts case-insensitively; `filter_books(author=, language=, query=)`
filters by substring (query matches title/author/language). 
`search_all(query)` scans every chapter of every book, case-insensitive,
and returns `SearchResult(book_title, chapter_title, offset, snippet)`
with ~40 characters of context either side, whitespace-collapsed.
Empty query returns no results (never "everything").

## Themes (`Theme`, `render_page`)

`Theme` dataclass: `name`, `font` (stored, not rendered), `font_size`
(default 16), `margins` (chars trimmed each side, default 2),
`line_spacing` (extra blank lines between lines, default 0),
`foreground`/`background` ANSI codes. Presets:
`light` (default fg, default bg), `dark` (bright-white on black),
`sepia` (yellow-ish fg). `effective_width(base_width)` =
`max(20, base_width - 2*margins - (font_size-16)*2)` — larger fonts
narrow the column, which is the terminal analogue of reflow.
`render_page(lines, theme, use_ansi)` joins lines with the spacing and,
if ANSI is on, wraps the block in the theme's colour codes.
`save_settings`/`load_settings` persist a theme as JSON
(`settings.json` in the data directory); unknown/missing files fall
back to the light preset.

## Annotations (`AnnotationStore`)

One JSON file (`annotations.json` in the data directory) holding, per
book path: `bookmarks` and `highlights`. Bookmark: chapter id, char
offset, excerpt (first ~60 chars of the chapter at the offset), label.
Highlight: chapter id, start, end, exact text, colour
(`yellow`/`green`/`pink`/`blue`, free strings accepted), optional note.
`resolve_highlight(book, highlight)` verifies the stored text at the
offset; if it mismatches, it re-searches the chapter text for the exact
string and returns the corrected span, or `None` if the text is gone.
This is what makes anchors reflow-proof: they are text-anchored, and
repagination changes only line breaks, never offsets. Save/load are
atomic-ish (write temp file, then replace).

## Dictionary / Wikipedia

`DICTIONARY` is a small literal dict (about 35 common words). 
`lookup_word(word)` lowercases/strips punctuation and returns
`(definition | None)`; callers render "not found" themselves so the
API stays honest. `wikipedia_summary(term, opener=None)` GETs
`https://en.wikipedia.org/api/rest_v1/page/summary/<term>` with a
10 s timeout and returns the `extract` field, or `None` on any HTTP /
network / JSON failure — never raises for a missing article. Tests
inject a fake opener; no test hits the network.

## CLI (`main`)

`argparse` subcommands, all keyboard-only: `import`, `list`
(`--sort`, `--author`, `--language`, `--query`), `toc`, `read`
(`--chapter`, `--page`, `--width`, `--theme`), `search`, `bookmark`,
`bookmarks`, `highlight`, `highlights`, `note`, `theme`, `lookup`,
`wikipedia`. The CLI is a thin shell over the library classes; all
behaviour lives in importable functions so tests exercise the API, not
the shell. Default data directory: `~/.local/share/ebook-reader`
(overridable with `--data-dir`); the library itself is the set of
imported files, re-parsed on each run (annotations/settings persist).

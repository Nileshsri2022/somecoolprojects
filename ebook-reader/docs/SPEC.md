# SPEC — Ebook Reader

Source: https://codingchallenges.fyi/challenges/challenge-ebook-reader
(read 2026-10-25; page live, not a 404)

## What the challenge asks for

Build an ebook reader that opens EPUB files, manages a library, and gives a
comfortable reading experience with annotations, dictionary lookups and
customisable themes. Steps, as written on the page:

- **Step 0 — Setup / test content.** Pick a platform/stack that can handle
  ZIP archives, XML, styled text and UI. Get 3–4 free EPUBs (Project
  Gutenberg / Standard Ebooks, well-formatted EPUB 3).
- **Step 1 — Open and read an EPUB.** Unpack the ZIP, follow the manifest /
  reading order (spine), render each chapter as readable styled text,
  page/scroll through it, show title and author, navigate via the table of
  contents, reflow on resize. Test: read a whole book, TOC jumps work,
  reflow works, a second different book works (nothing hardcoded).
- **Step 2 — Library and search.** Import books, show cover image and
  metadata (title, author, language), sort/filter the collection, full-text
  search indexed across every book's content, returning book title and
  location in the text.
- **Step 3 — Themes / typography.** Adjust font, font size, colours,
  margins, line spacing, background colour. Theme overrides the book's
  stylesheets without breaking them; at least light and dark themes;
  settings persist across close/reopen and apply to other books.
- **Step 4 — Highlights, bookmarks, notes.** Select text, highlight in
  different colours, attach notes, set bookmarks. All persist across
  close/reopen. Anchors must be to the text itself, not screen position,
  so they survive reflow.
- **Step 5 — Dictionary / Wikipedia.** Selecting a word shows a definition;
  dictionary lookups work offline; Wikipedia lookup via the public API
  for extra context, in an overlay/popup that does not lose the reading
  place.
- **Step 6 — Keyboard navigation and screen readers.** Every feature
  reachable without a mouse, logical tab order, labelled/role-marked
  controls; test with VoiceOver / NVDA / Orca.
- **Going Further (not required):** text-to-speech with sentence
  highlighting, OPDS / Calibre integration, PDF support, reading-position
  sync across devices.

## What this build does (terminal core)

Python 3 standard library only, one main file `ebook_reader.py`:

- Step 0: no platform UI is chosen; the reader is a terminal/CLI program.
  Test books are synthetic EPUBs built by the test suite (EPUB 2 + NCX
  and EPUB 3 + nav variants), plus any real `.epub` dropped into a library
  directory. No books are downloaded here (no network dependency in tests).
- Step 1: `parse_epub()` reads `META-INF/container.xml`, then the OPF
  package document (metadata, manifest, spine), resolves the spine order,
  converts each XHTML chapter to plain text, and exposes title/author/
  language/identifier, chapters and a table of contents. `Reader`
  paginates, moves by page/chapter, jumps to a TOC entry, and reports
  reading progress (0–100%).
- Step 2: `Library` imports `.epub` (and plain `.txt` as a one-chapter
  convenience, see Divergences), lists books, sorts by title/author,
  filters by author/language/free-text, and searches all books'
  full text, returning book title, chapter title, character offset and
  a context snippet for every match.
- Step 3: `Theme` presets `light`, `dark`, `sepia` plus font name,
  font size, margins and line spacing. In a terminal, "font size" is
  realised as the wrapping width (larger size = fewer characters per
  line) and line spacing as blank lines between lines; colours are ANSI
  codes. Themes are persisted to `settings.json` in the data directory
  and reloaded on open. The book's own CSS is read from the package
  (stylesheet hrefs are recorded) but is NOT rendered — see Divergences.
- Step 4: `AnnotationStore` (JSON file per library) holds bookmarks,
  highlights (with colour) and notes. A highlight is anchored by
  chapter id + character offset + the exact highlighted text; on load
  the anchor is verified, and if the offset no longer matches (e.g. the
  file changed), the stored text is re-searched in that chapter, so
  anchors survive repagination/reflow. Listing all bookmarks and
  annotations for a book is supported.
- Step 5: `lookup_word()` consults a small built-in offline dictionary
  (common words) and returns a clear "not found" result otherwise.
  `wikipedia_summary()` calls the public Wikipedia REST summary API
  via `urllib` with a timeout; it accepts an injectable opener so tests
  never touch the network. Neither lookup moves the reader position.
- Step 6: the whole program is keyboard-driven by construction (CLI
  subcommands, no mouse path at all). There is no GUI widget tree, so
  there is no tab order or ARIA/screen-reader announcement to test —
  see Scope limits. All output is plain text (optionally ANSI-coloured),
  which screen readers can consume from a terminal.

## Deliberate divergences

1. **No GUI.** The page says "choose a platform… good tools for displaying
   rich text". This build chooses the terminal instead of a desktop/web
   GUI. There is no window to resize, no cover-image rendering, no
   mouse selection, no overlay popup. Reflow is demonstrated by
   repaginating at a different width; the joined text is unchanged.
2. **Book styling flattened.** XHTML is converted to plain text: headings
   become their own lines, paragraphs are separated by blank lines, list
   items get a "- " prefix. Bold/italic/underline and the book's CSS
   rules are not visually reproduced in the terminal. Structure (chapter
   breaks, headings, paragraph breaks) is preserved; inline styling is not.
3. **Plain-text import is an addition.** `.txt` files import as a
   single-chapter book. The page specifies EPUB only; this is a
   convenience, not a substitute for EPUB parsing, and it is labelled as
   such in the README.
4. **Cover images are recorded, not displayed.** If the OPF manifest
   marks a cover item, its href is stored on `Book.cover_href`; the
   terminal does not render the image bytes.
5. **Offline dictionary is small.** It covers common words only; an
   uncommon word returns "not found" rather than a fabricated
   definition. A full offline dictionary file is not bundled.
6. **Font name is stored, not rendered.** A terminal cannot switch fonts
   per book; `Theme.font` is persisted and reported, and only size /
   spacing / margins / colours affect terminal output.

## NOT built (honestly)

- No graphical user interface, window resizing, mouse text selection,
  or overlay popups.
- No CSS rendering engine (book stylesheets are listed, not applied).
- No text-to-speech, OPDS/Calibre browsing, PDF support, or
  cross-device reading-position sync (all "Going Further" items).
- No screen-reader testing with VoiceOver/NVDA/Orca (no GUI to test).
- No DRM-protected EPUBs: encrypted/obfuscated content is not decrypted.
- No download of Gutenberg/Standard Ebooks titles in this build; bring
  your own `.epub` files to the library directory.

## Success criteria

- `python3 -m unittest discover -s tests -v` passes with 0 failures.
- A synthetic EPUB 2 (NCX TOC) and a synthetic EPUB 3 (nav TOC) both
  parse: correct title/author, spine order, chapter text, TOC jumps.
- Search finds a phrase in one book and in multiple books, with chapter
  and snippet, and finds nothing for an absent phrase.
- A highlight + note + bookmark survive a save/reload cycle and still
  resolve after repagination at a different width.
- Theme settings survive a save/reload cycle.
- `lookup_word()` returns a definition for a known word and a clean
  not-found result for an unknown word, without moving the reader.

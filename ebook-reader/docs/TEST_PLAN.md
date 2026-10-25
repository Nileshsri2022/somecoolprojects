# TEST_PLAN — Ebook Reader

Runner: `python3 -m unittest discover -s tests -v` from
`ebook-reader/`. Standard library `unittest` only. No network, no
real books: the suite builds synthetic EPUBs in `tempfile` directories
with `zipfile` (one EPUB 2 + NCX, one EPUB 3 + nav, one minimal EPUB
with missing author/language, one corrupt ZIP, one EPUB whose spine
references a missing file).

Coverage map (all in `tests/test_ebook_reader.py`):

- EPUB 2 parsing: title, author, language, spine order (chapter order
  follows spine, not manifest order), chapter text extraction
  (headings/paragraphs/lists, script/style dropped), NCX TOC titles and
  chapter mapping, cover href recorded.
- EPUB 3 parsing: nav-document TOC, metadata fallback when author is
  missing (""), chapter title fallback to filename.
- Error handling: corrupt ZIP raises `EpubError`; missing spine file
  raises `EpubError`; non-EPUB path raises `EpubError`.
- Pagination/reflow: same text paginated at width 80 and width 40
  yields different page counts but identical joined text; page size
  respected; empty text yields zero pages.
- Reader navigation: next/prev page clamps at book ends, next/prev
  chapter moves correctly, `goto_toc` jumps to the right chapter,
  `progress` is 0 at the start, in (0,1) mid-book, and increases
  monotonically; search within a book finds chapter + offset, and
  misses return [].
- Library: import of both EPUB variants; sort by title and by author;
  filter by author, language and free-text query; search across books
  finds a phrase present in one book, a phrase present in both books,
  and returns [] for an absent phrase; empty query returns [].
- Themes: light/dark/sepia presets differ; larger font size narrows
  the effective width; line spacing inserts blank lines; settings
  survive save/load; corrupt settings file falls back to light.
- Annotations: bookmark/highlight/note round-trip through save/load;
  highlight resolves at its stored offset; after repagination at a
  different width the same highlight still resolves to the same text;
  a highlight whose stored text was moved resolves by re-search;
  a highlight for deleted text resolves to `None`; listing returns
  only that book's annotations.
- Dictionary: known word returns a definition; unknown word returns
  `None`; lookup is case-insensitive and punctuation-tolerant; lookup
  does not move the reader's position.
- Wikipedia: with an injected fake opener, returns the extract; with
  a failing opener, returns `None` (no exception). No test performs a
  real HTTP request.
- CLI smoke: `python3 ebook_reader.py --help` exits 0; `list` on an
  empty data dir exits 0 with no traceback.

Manual checks (not automated, need a real book): drop a genuine
Project Gutenberg / Standard Ebooks `.epub` into a library dir and run
`python3 ebook_reader.py import <file>`, `toc`, and `read --width 80`;
confirm title/author/TOC look right and the first chapters read cleanly.

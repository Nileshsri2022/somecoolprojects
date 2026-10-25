# TEST_PLAN — Markdown To PDF Editor

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

All tests use `tempfile.TemporaryDirectory`; no test writes into
the repo, and no test needs a GUI, browser, or network. Text
extraction uses `pdftotext` when it is on PATH (it is on this
machine, `/usr/bin/pdftotext`); when it is absent, the PDF tests
fall back to checking that the raw PDF bytes contain the
expected literal strings (the writer emits plain Tj strings for
ASCII, so this is a real check, not a tautology).

## Coverage map (page step -> test)

- Step 0 / CLI: missing input file exits non-zero and writes no
  output; bad colour / font / page / size exit non-zero; unknown
  subcommand exits non-zero; `convert` default output name is
  the input basename with `.pdf`.
- Step 1 / parser: headings H1–H6 and `#no-space` as paragraph;
  bold `**` and `__`; italic `*` and `_`; bold+italic nesting;
  unmatched delimiters left literal; inline code not re-scanned
  for bold; links parsed (text + url); images parsed as image
  spans; unordered (`-`, `*`, `+`) and ordered lists; nested
  lists; fenced code blocks (language ignored, fences not in
  output); blockquote; hr; paragraph separation on blank lines.
- Step 2 / preview: HTML contains `h1`, `strong`, `em`, `code`,
  `a href`, `ul`/`ol`/`li`, `pre`, `blockquote`, `hr`; HTML
  escapes `<`/`&` in source text; style block reflects `--bg`,
  `--fg`, `--font`, `--font-size`.
- Step 3 / customisation: PDF page size is A4 by default and
  Letter with `--page letter` (checked via the MediaBox in the
  raw PDF); background colour appears as a fill rect; larger
  `--font-size` produces larger heading font operators in the
  content stream; unknown font rejected.
- Step 4 / PDF: file starts with `%PDF-`, ends with `%%EOF`,
  xref offsets point at real `N 0 obj` headers; `pdftotext`
  output contains heading, paragraph, bold, list-item and code
  text for a sample document; a long document paginates to
  more than one page; code-block text is extractable; link text
  is extractable and the image placeholder line is extractable.
- Editor loop: driven over StringIO — `append`, `insert`,
  `replace`, `delete`, `print` listing, `pdf` callback fired,
  unknown command reported without crashing, `quit` returns
  the final lines.
- Watch: not covered by a sleeping test (flaky by nature);
  covered indirectly because watch calls the same `convert()`
  the CLI tests exercise, and its mtime-change detection is a
  two-line function (`_file_changed`) tested directly.

## Success criteria (verifiable, per ponytail rules)

1. `python3 -m unittest discover -s tests -v` — all tests pass.
2. `python3 md2pdf.py convert sample.md --preview sample.html`
   on a document exercising every syntax above produces a PDF
   whose `pdftotext` output contains every line of that
   document's plain text, and an HTML preview with the same
   content.
3. A 200-line document produces a multi-page PDF with a valid
   xref table (checked by the xref test, not by eye).

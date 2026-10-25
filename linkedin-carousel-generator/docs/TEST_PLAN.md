# TEST_PLAN — LinkedIn Carousel Generator

Run: `python3 -m unittest discover -s tests -v` from the project
directory. Standard library `unittest` only; no network, no browser.

## Coverage map (challenge step -> tests)

- Step 1 (preview, 1080 square): HTML output contains one section
  per slide, each styled 1080 x 1080 px; title and body text present
  and HTML-escaped.
- Step 2 (profile): author/handle appear on every slide in both
  outputs; avatar JPEG is embedded as an XObject in the PDF.
- Step 3 (colours/font/size): theme colours appear in PDF operators
  and HTML styles; font name appears in the PDF font object;
  invalid hex / unknown font / bad size are CLI errors.
- Step 4 (add + navigate slides): `---` splitting, title/body
  parsing, `# ` stripping, bullet preservation, slide order,
  HTML prev/next controls and counter, PDF page count = slide count.
- Step 5 (per-slide background image + transparency): `!bg` parsing
  with default and explicit opacity, opacity value in the PDF
  graphics state, JPEG embedded full-bleed, PNG rejected for PDF
  with a clear error, missing image file rejected.
- Step 6 (PDF export): output starts with `%PDF-`, ends with
  `%%EOF`, xref offsets point at real objects (verified by parsing
  the trailer offsets), one `/Type /Page` per slide, footer
  `N / total` on each page, text content present per slide.

## Pure-function tests (no I/O)

- `parse_hex`: valid with/without `#`, rejects short/long/non-hex.
- `parse_deck`: single slide, multi-slide, heading stripping,
  empty slides dropped, empty input raises, `!bg` directive parsed
  and not rendered, bad opacity raises.
- `wrap_text`: short text unwrapped, long text wraps within the
  width estimate, over-long word hard-split, empty text -> [].
- `layout_slide`: footer text, title before body in y order,
  coordinates inside the 1080 x 1080 page, author line present only
  when author set, page index/total correct.

## Integration tests (CLI level, temp dirs)

- Build PDF + HTML from a sample deck; both files exist and pass
  the checks above; PDF page count matches slide count.
- CLI error cases exit non-zero and write no output file: missing
  input, empty deck, bad colour, unknown font, missing image.
- A tiny real JPEG (1x1, generated in the test from bytes, not
  from an external file) embeds and round-trips through the PDF.

## Success criteria

All tests pass. A sample deck builds a PDF that a PDF reader can
open (header/trailer/xref structure verified in tests; manual open
in a viewer is optional and was not required for the verdict).

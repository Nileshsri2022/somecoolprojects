# Ebook Reader

A terminal ebook reader core for EPUB files — parse, paginate, navigate,
search a library, theme the output, and keep text-anchored bookmarks,
highlights and notes. Python 3 standard library only.

Built for the Coding Challenges "Build Your Own Ebook Reader" challenge
(https://codingchallenges.fyi/challenges/challenge-ebook-reader).
See `docs/SPEC.md` for the step-by-step mapping, `docs/DESIGN.md` for
how it works, and `docs/TEST_PLAN.md` for what the tests cover.

## Scope, honestly

This is the **local/terminal core, not a GUI reader app**. There is no
window, no mouse selection, no rendered cover image, and no CSS
rendering engine: book styling (bold/italic/CSS rules) is flattened to
plain text, while structure (chapters, headings, paragraphs, lists) is
preserved. Themes change terminal colours, wrapping width (font size),
margins and line spacing, and persist across runs. Not built: GUI,
text-to-speech, OPDS/Calibre, PDF support, cross-device sync, DRM
decryption, screen-reader GUI testing. Full list in `docs/SPEC.md`.

## Run

```bash
python3 ebook_reader.py --help
python3 ebook_reader.py import ~/books/pride-and-prejudice.epub
python3 ebook_reader.py list --sort title
python3 ebook_reader.py toc --book <path-or-title-substring>
python3 ebook_reader.py read --book <path-or-title-substring> --width 80
python3 ebook_reader.py search "call me Ishmael"
python3 ebook_reader.py bookmark --book <book> --chapter 0 --offset 120 --label "start here"
python3 ebook_reader.py highlight --book <book> --chapter 0 --start 0 --end 42 --colour yellow
python3 ebook_reader.py theme --set dark
python3 ebook_reader.py lookup serendipity
python3 ebook_reader.py wikipedia "Jane Austen"
```

Data (annotations + theme settings) lives in
`~/.local/share/ebook-reader/` by default; pass `--data-dir <dir>` to
override. Books are re-parsed from their files on each run; only
annotations and settings persist.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

No network access is needed or used by the tests; synthetic EPUBs are
built in temporary directories by the suite itself.

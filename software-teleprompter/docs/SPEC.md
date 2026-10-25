# Software Teleprompter — SPEC

Source challenge: https://codingchallenges.fyi/challenges/challenge-teleprompter
(read 2026-10-25; page returned full text, not a 404.)

## What it is

A terminal teleprompter core in Python 3 (standard library only).
It loads a script, formats it, and scrolls it at an adjustable speed
(words per minute) with pause/resume and mirroring. An interactive
curses UI is included for live use; all scrolling/timing logic lives
in headless classes that are fully unit-tested without a terminal.

**Terminal-only, plainly stated:** this is NOT a GUI app, NOT a web
app, and NOT a mobile app. There is no graphical window, no deployed
URL, and no font rendering. See "Deliberate divergences" below.

## Challenge steps — status

| Step | Challenge asks | Status in this build |
|---|---|---|
| Step 0 | Choose app type + stack | Done: terminal app, Python 3 stdlib only (`teleprompter.py`) |
| Step 1 | Enter/paste text, show it to the user | Done: `--file`, `--url`, stdin, or typed/pasted text; `--dump` prints the formatted script; curses UI shows it |
| Step 2 | Set font face + size for all text; newlines; controls below the text; ideally Markdown headings/emphasis | Done, adapted (see divergences): `font_face` + `font_size` settings for all text, newlines preserved, lightweight Markdown (headings upper-cased, `**bold**`/`*italic*`/`` `code` `` markers stripped, text kept) |
| Step 3 | Adjustable left/right margins + line spacing, controls below the text | Done: `--left-margin`, `--right-margin`, `--line-spacing`; curses keys adjust them live |
| Step 4 | Set scroll speed; start/stop scrolling via button or space bar (when text box not selected) | Done: speed in WPM (`--wpm`, `+`/`-` keys); space bar toggles pause/resume in the curses UI; `Player.start/stop/toggle` headlessly |
| Step 5 | Mirror the text vertically via a button; scrolling must still work | Done: `--mirror vertical` reverses line order; `--mirror horizontal` (true beam-splitter flip, reverses each line) and `both` also supported; `m` toggles in the UI; scrolling works over the mirrored line list (tested) |
| Step 6 | Import text from an external source: a URL, e.g. Markdown from a GitHub repo, and from a Google Doc via the Google Docs API | Partly done: URL import (`--url`, plain HTTP(S) fetch, stdlib `urllib`) and local-file import are implemented and tested. Google Docs API import is NOT built (see below) |
| Going Further | Ship/deploy; upload text/Word/PDF documents; listen to the speaker and scroll at delivery speed | NOT built (see below) |

## Behaviour specified

- Script loading: plain text; blank lines separate paragraphs and are
  preserved through formatting (a paragraph break survives wrapping).
- Formatting order: Markdown processing → word-wrap → margins →
  line-spacing blanks → mirroring. Margins are applied after
  horizontal mirroring so the left margin stays on the left.
- Wrapping width: `terminal_width - left_margin - right_margin`,
  scaled by font size (see DESIGN.md). Minimum effective width 20.
- Font size: integer points, valid range 8–72 (outside raises
  `ValueError`). Default 24.
- Margins: integers ≥ 0 (negative raises `ValueError`). Defaults 4/4.
- Line spacing: integer count of extra blank lines inserted between
  wrapped lines, 0–3 (outside raises `ValueError`). Default 0, i.e.
  single-spaced; 1 = double-spaced.
- Scroll speed: WPM, valid range 10–600 (outside raises `ValueError`).
  Default 150 WPM. Lines-per-second is derived, not set directly:
  `lines_per_second = wpm / average_words_per_nonblank_line`
  (10 words/line assumed for an empty script). This keeps the WPM
  figure meaningful for scripts of different line lengths.
- Playback: `offset` is fractional lines; `step(dt)` advances it by
  `lines_per_second * dt` only while playing; it clamps at the last
  line and stops (`at_end()` true) rather than running past the end.
  `visible_lines(height)` returns the viewport slice at the current
  offset. Pause/resume does not reset the offset. `reset()` returns
  to the top; `seek(line)` clamps into range.
- Mirroring: `none` (default), `horizontal` (each line reversed),
  `vertical` (line order reversed), `both`. Unknown mode raises
  `ValueError`.
- Import: file import reads UTF-8 text; URL import fetches with a
  15 s timeout and decodes as UTF-8 (replacing undecodable bytes).
  A failed fetch raises `ImportError` (wrapping the underlying error)
  — it never silently substitutes placeholder text.
- Interactive keys (curses UI): `Space` pause/resume, `+`/`-` faster/
  slower (±10 WPM), `m` cycle mirror mode, `h`/`l` shrink/grow left
  margin, `q` quit. `Ctrl-C` also exits cleanly.

## Deliberate divergences (terminal adaptation)

1. **No GUI/web/mobile UI and no real font rendering.** A terminal
   cannot render font faces or point sizes as glyphs. `font_face`
   is stored, validated as a non-empty string, and shown in the
   status line, but it does not change how characters look.
   `font_size` does have a visible terminal effect: it scales the
   wrap width (larger font ⇒ fewer characters per line), which is
   the terminal analogue of scaling text. No claim is made that
   glyphs are resized.
2. **No sliders/buttons.** Controls are CLI flags plus curses keys
   (listed above), not on-screen sliders or buttons.
3. **Markdown is lightweight, not full CommonMark.** Headings
   (`#`–`######`) are upper-cased and kept on their own line;
   `**bold**`, `*italic*`, `_italic_`, and `` `code` `` markers are
   stripped, keeping the inner text. Lists, links, images, tables,
   and code blocks are NOT specially rendered; link text is kept,
   URLs in `[text](url)` are dropped to just `text`.
4. **Mirror wording.** The page says "mirror the text vertically".
   That is implemented literally as `vertical` (line order
   reversed). Because a real beam-splitter teleprompter flips
   horizontally, `horizontal` is offered as well; neither is
   presented as the page's only meaning.
5. **URL import is generic HTTP(S), not GitHub- or Google-specific.**
   Any reachable plain-text/Markdown URL works, including a raw
   GitHub URL. There is no GitHub API client and no Google Docs
   API client.

## NOT built (honestly, not silently skipped)

- Google Docs API import (needs OAuth credentials and the Google
  client libraries; out of scope for a stdlib-only terminal core).
- Document upload: MS Word (.docx) and PDF parsing (needs
  third-party libraries and binary parsing; plain-text file import
  is the supported path).
- Speech-following scrolling (listening to the speaker and matching
  delivery speed; needs audio capture + speech recognition).
- Deployment / GitHub release packaging (no web app to deploy; the
  program is run directly with `python3 teleprompter.py`).
- Per-word / per-character formatting, colours, or rich text
  (terminal output here is plain text; no ANSI colour styling of
  individual words).

## Usage

```sh
# Show the formatted script without scrolling
python3 teleprompter.py --file script.txt --dump

# Import from a URL and scroll at 180 WPM in the interactive UI
python3 teleprompter.py --url https://example.com/script.md --wpm 180

# Non-interactive timed playback (prints the viewport, for pipes/tests)
python3 teleprompter.py --file script.txt --play --seconds 10

# Pipe a script in
cat script.txt | python3 teleprompter.py --dump
```

## Files

- `teleprompter.py` — the whole program (core + CLI + curses UI)
- `tests/test_teleprompter.py` — unittest suite
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md` — this spec
- `example_script.txt` — a short sample script for trying it out

# Software Teleprompter

Terminal teleprompter core in Python 3 (standard library only),
built for the Coding Challenges "Build Your Own Software
Teleprompter" challenge:
https://codingchallenges.fyi/challenges/challenge-teleprompter

**Terminal-only, plainly stated:** this is not a GUI app and not a
web app. There is no graphical window, no deployed URL, and no real
font rendering — a terminal cannot render font faces or point sizes
as glyphs. `font_face` is stored and shown; `font_size` scales the
wrap width (larger font ⇒ fewer characters per line). All scrolling
and timing logic is headless and unit-tested.

## Features (challenge steps 0–5, plus file/URL import)

- Load a script from a file, a URL, or stdin; type/paste text in.
- Format it: margins, line spacing, font size scaling, lightweight
  Markdown (headings upper-cased, `**bold**`/`*italic*`/`` `code` ``
  markers stripped, link text kept).
- Scroll at an adjustable speed in WPM, with pause/resume.
- Mirror horizontally (beam-splitter flip), vertically (line order
  reversed, as the challenge page words it), or both — scrolling
  still works when mirrored.
- Interactive curses UI: `Space` pause/resume, `+`/`-` speed,
  `m` cycle mirror, `h`/`l` left margin, `q` quit.

## NOT built

Google Docs API import, Word/PDF upload, speech-following scrolling,
and deployment — see `docs/SPEC.md` for the honest scope statement.

## Usage

```sh
# Show the formatted script without scrolling
python3 teleprompter.py --file example_script.txt --dump

# Interactive scrolling UI at 180 WPM
python3 teleprompter.py --file example_script.txt --wpm 180

# Import from a URL
python3 teleprompter.py --url https://example.com/script.md --wpm 180

# Non-interactive timed playback
python3 teleprompter.py --file example_script.txt --play --seconds 10

# Pipe a script in
cat example_script.txt | python3 teleprompter.py --dump
```

## Tests

```sh
python3 -m unittest discover -s tests -v
```

See `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md`.

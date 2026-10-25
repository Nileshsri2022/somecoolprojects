# Software Teleprompter — DESIGN

## Stack

Python 3 standard library only. No third-party packages, so the
program runs anywhere `python3` exists. `curses` (stdlib, Unix) is
used only by the interactive UI and is imported lazily, so the core
and the tests run on any platform, including where curses is absent.

## Module layout (`teleprompter.py`, single file)

```
TeleprompterSettings   dataclass: font_face, font_size, left_margin,
                       right_margin, line_spacing, mirror, wpm.
                       Validates ranges in __post_init__.
Script                 holds raw text; load_text / load_file /
                       load_url classmethods; markdown_lines()
                       (lightweight Markdown -> plain lines);
                       average_words_per_line().
render_lines(script, settings, width)
                       pure function: markdown -> wrap -> margins ->
                       line-spacing blanks -> mirror. Returns a
                       list[str]. All formatting decisions live here
                       so tests never need a terminal.
Player                 playback state over a rendered line list:
                       offset (float), playing flag, wpm,
                       lines_per_second, start/stop/toggle/step/
                       visible_lines/ seek/reset/progress/at_end.
run_curses(stdscr, script, settings)
                       interactive UI: draws viewport + status line,
                       handles keys, ticks with a 50 ms timeout.
main(argv)             argparse CLI: --file/--url/stdin input,
                       formatting flags, --dump, --play, else curses.
```

## Key decisions

- **Core/UI split.** `Script`, `render_lines`, and `Player` know
  nothing about curses or stdout. The UI is a thin loop over them.
  This is what makes headless testing possible and honest: the
  tested code is the code that scrolls.
- **Wrapping.** `textwrap.wrap` per paragraph line (paragraphs are
  split on blank lines first, so a blank line in the source stays a
  paragraph break and is never merged into the previous paragraph).
  Long words are broken (`break_long_words=True`) so a single long
  token cannot overflow the viewport.
- **Font-size scaling.** `effective_width = int(base_width * 24 /
  font_size)`, clamped to `[20, base_width]`, where `base_width =
  width - left_margin - right_margin` and 24 is the default font
  size (scale factor 1). Larger font ⇒ narrower lines ⇒ fewer words
  per line ⇒ slower line advance at the same WPM, which matches the
  intuition that bigger text scrolls "more slowly" per line.
- **WPM → lines/second.** `lps = wpm / avg_words_per_nonblank_line`
  (fallback 10.0 for empty scripts). A script with long lines
  therefore advances fewer lines per second than one with short
  lines at the same WPM — the WPM figure, not a raw line rate, is
  the user-facing speed. Changing WPM mid-playback recomputes the
  rate immediately.
- **Fractional offset.** `step(dt)` adds `lps * dt` to a float
  offset; `visible_lines` floors it. This gives smooth speed
  control independent of tick rate (the curses loop ticks at 50 ms
  but any `dt` works).
- **Mirroring order.** Mirroring is the last render step and works
  on the final line list, so scrolling (which is just an offset
  into that list) is automatically correct for every mirror mode —
  there is no separate mirrored-scroll code path to drift.
- **Import errors are loud.** `load_url` wraps `URLError`/`OSError`
  in `ImportError` with the original message; `load_file` lets
  `FileNotFoundError` propagate. Nothing returns placeholder text
  on failure.
- **Markdown scope.** Only headings and inline emphasis/code
  markers are handled, with two small regexes. This is deliberate:
  full Markdown needs a parser; the challenge's "ideally" wording
  makes this a stretch goal, and the subset implemented is stated
  in SPEC.md rather than oversold.

## What was not abstracted

No separate modules: at ~400 lines the program does not justify
splitting. No config file format: settings come from CLI flags
only. No persistence of scripts or settings between runs.

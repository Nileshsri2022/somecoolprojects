# wheel-of-names — SPEC

Source challenge page (read first, before any code):
https://codingchallenges.fyi/challenges/challenge-wheel
— "Build Your Own Wheel of Names".

Slug note: the first guess `challenge-wheel-of-names` returned HTTP 404.
The correct slug, found via the site's graphics tag page
(https://codingchallenges.fyi/challenges/tags/graphics/), is
`challenge-wheel`. No other page content was substituted: the steps
below are that page's steps, plus the substack mirror's identical
step wording was used only as a cross-check, not as the source.

## Page steps implemented

- Step Zero: language/project choice — Python 3, standard library
  only, single main file `wheel.py`.
- Step 1: user enters a list of names. Here: one name per line
  (file, `--names` list, or the interactive prompt). Blank lines
  are dropped; surrounding whitespace is stripped.
- Step 2: names can be shuffled and sorted (commands/flags for
  each; see README).
- Step 3: draw the wheel with the names on it. Each name gets an
  equal segment of the circle in the default (uniform) mode, and
  the segment sizes change as names are added/removed. Each
  segment gets a colour different from its two neighbours (the
  palette cycles, and consecutive palette entries are distinct).
  The name text is placed inside its segment; very long names
  are truncated in the SVG rendering only (see DESIGN).
- Step 4: spin the wheel, animate it spinning and slowing down,
  then display a winner. Here: a terminal spin animation
  (names cycle past a pointer, slowing with an ease-out cubic
  curve) plus a static HTML/SVG snapshot of the final wheel.
  The winner is decided first, by uniform random choice, and the
  animation lands on it — the animation never re-decides the
  result.
- Step 5 (advanced mode): the user can specify the colour and
  the size of each segment, via a per-entry weight (size) and
  colour. Uniform mode is the special case where every weight
  is 1 and no colour is given.

## Going Further (not built)

- Deploying, saving/sharing wheels, and a Discord bot. Out of
  scope for this build; the HTML snapshot is a plain file that
  can be opened or shared as-is, but there is no save/load
  wheel format beyond the plain name list / `--entry` flags.

## Behavioural contract

- Empty wheel: `segments()` and `spin()` raise `ValueError`.
  There is nothing to draw or pick from.
- One name: that name always wins; its segment is the full
  360 degrees.
- Duplicate names are allowed as separate entries (each gets
  its own segment, so duplicates raise that name's odds, exactly
  as adding the same name twice to a real wheel would).
- Removing a name removes its first occurrence only, matching
  by exact (case-sensitive) string.
- Sorting is case-insensitive (`str.casefold`) and stable, so
  `bob` sorts next to `Bob` without reordering equal-fold names
  arbitrarily.
- Weights must be finite and > 0; a custom colour, if given,
  must be `#RRGGBB`. Violations raise `ValueError` at entry
  construction, not at spin time.
- Spinning is uniform over entries in uniform mode (each entry
  probability 1/N) and proportional to weight in advanced mode.
  With a seeded `random.Random`, a spin is fully reproducible.

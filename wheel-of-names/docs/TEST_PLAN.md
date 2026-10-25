# wheel-of-names — TEST_PLAN

Run: `python3 -m unittest discover -s tests -v` from the
project directory. All tests are pure (seeded RNG, no
terminal, no sleep, no files except via temp paths for the
file-parsing helpers) — the animation's sleep is never
invoked by tests; `spin_frames()` is tested instead.

## Cases (all in tests/test_wheel.py)

Parsing / list management (Steps 1–2):
- `parse_names`: one per line, strips whitespace, drops
  blanks, keeps order and duplicates.
- `parse_names` on empty/blank-only text returns [].
- `parse_entry_line`: plain name, `name|weight`, and
  `name|weight|#color` forms; bad weight / bad colour /
  empty name raise ValueError.
- `add_name` appends, returns a new list, does not mutate
  the input; `add_name` with a blank name raises ValueError.
- `remove_name` removes the first exact match only, leaves
  other duplicates, returns a new list; removing an absent
  name leaves the list unchanged.
- `shuffle_names` with a seeded RNG is deterministic
  (same seed, same order), is a permutation of the input,
  and does not mutate the input.
- `sort_names` is case-insensitive and stable, and does
  not mutate the input.

Segments (Step 3):
- Uniform segments: sweeps sum to 360 (within 1e-9),
  starts are cumulative from 0, each sweep is 360/N.
- Single entry: one segment, sweep 360.
- Empty entries: `segments()` raises ValueError.
- Neighbour colours differ for default palettes at N = 2,
  3, 8, 9 (the N % 8 == 1 wrap case), and 17.
- Weighted segments: sweeps proportional to weights and
  sum to 360; a custom colour overrides the palette.
- Bad weight (0, negative, NaN/inf) and bad colour at
  `Entry` construction raise ValueError.

Spin (Step 4):
- `winner_for_angle`: boundaries — angle 0 is segment 0,
  an exact segment start belongs to the segment that
  starts there, angle 359.9 is the last segment, and
  angles are normalised (360 -> 0, -10 -> 350).
- `spin` with a seeded RNG is reproducible (same seed,
  same winner/index/total/final) and the winner is the
  entry at the returned index.
- `spin` consistency: `winner_for_angle((-final) mod 360)`
  equals the spin's index, for uniform and weighted wheels.
- `spin` turns are in [5, 10] and `total >= final`.
- `spin` on an empty wheel raises ValueError.
- Weighted spin is reproducible with a seed and its winner
  is always a valid entry (statistical proportionality is
  not asserted — one seeded draw cannot prove a
  distribution; the weighted segment geometry above is
  what makes proportionality true by construction).
- `spin_frames`: first frame 0, last frame equals the
  total, frames are non-decreasing, count matches the
  requested steps, and intermediate frames follow the
  ease-out cubic curve.

Rendering (Steps 3–4):
- `render_svg` contains every entry name (truncated form
  for long names), every segment colour, one wedge path
  per segment, a pointer marker, and a centre hub.
- `render_svg` with a rotation rotates the wedges (the
  rotation appears in the SVG group transform).
- `render_html` wraps the SVG in a document containing the
  winner name when one is given.
- Long names (>18 chars) are truncated with an ellipsis
  in the SVG but the full name is preserved in the Entry.

CLI parsing:
- `parse_args` accepts `--names`, `--seed`, `--html`,
  `--fast`, `--shuffle`, `--sort`; a `--names` value that
  parses to no names is rejected by `build_wheel` with
  ValueError (not by argparse, so the function stays
  testable without sys.exit).
- `build_wheel` from `--entry` strings honours weight and
  colour, and `--remove` drops the named entry.

Not tested (by design):
- The actual terminal animation timing (`time.sleep`
  calls in `animate_spin`) and the interactive prompt loop
  (stdin/stdout) — both are thin shells over the tested
  pure functions.
- Browser rendering of the HTML file — the SVG is
  well-formed text, checked by string assertions.

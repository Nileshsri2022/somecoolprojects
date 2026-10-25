# wheel-of-names — DESIGN

Assumptions, stated before coding (ponytail: think first,
simplicity first, minimum code, nothing speculative).

## Representation

One dataclass, `Entry`, holds a wheel entry:

```
name: str
weight: float = 1.0   # segment size; uniform when all are 1
color: str | None = None  # "#RRGGBB" override, else palette
```

A `Wheel` is a thin wrapper around `list[Entry]` with
`add` / `remove` / `shuffle` / `sort` methods; the module-level
functions (`parse_names`, `add_name`, `remove_name`,
`shuffle_names`, `sort_names`, `segments`, `spin`, ...) are the
real logic and are pure (they return new lists / values and
never touch the terminal), so every one of them is unit-testable
without I/O. The `Wheel` methods just delegate to them. No
separate Segment-drawing class: a segment is a small dataclass
(`Segment`: entry, index, start_deg, sweep_deg, color).

## Geometry (the one convention tests depend on)

Angles are degrees, clockwise, measured from the top of the
wheel, where the pointer sits. Segment `i` spans
`[start_deg, start_deg + sweep_deg)` in wheel coordinates:

- Uniform mode: `sweep_deg = 360 / N`, `start_deg = i * sweep`.
- Weighted mode: `sweep_deg = 360 * weight_i / sum(weights)`,
  starts accumulate from 0.

A wheel rotation `R` (clockwise, degrees) moves segment
boundaries with it, so the pointer at the top reads the wheel
angle `p = (-R) mod 360`. `winner_for_angle(p, segs)` returns
the segment containing `p` (last segment wins on the exact
360/0 boundary, which normalisation makes unreachable except
as 0). `spin()` works backwards from this: it picks the
winner index first (uniform, or weighted via `rng.choices`
in weighted mode — see below), picks a landing angle `p`
inside the winner's segment (uniformly at random within the
segment, so no segment edge is favoured), then sets
`R = (-p) mod 360` and `total = turns * 360 + R` with
`turns` uniform in [5, 10]. Therefore
`winner_for_angle((-spin.final_deg) mod 360) == spin.index`
always holds, and tests assert exactly that.

## Spin fairness and seeded RNG

- Uniform mode: `rng.randrange(N)` — every entry 1/N.
- Weighted mode: `rng.choices(range(N), weights=...)` with
  one draw — probability proportional to weight. (One draw
  via `choices` is used instead of hand-rolling a cumulative
  sum, because it is the stdlib primitive for exactly this.)
- Every spin function takes `rng=None` (defaults to the
  module `random` module for real use); tests pass a seeded
  `random.Random`, making a spin byte-for-byte reproducible.
- The landing angle inside the winner's segment is drawn
  with `rng.random()` after the winner draw, so the seeded
  sequence still reproduces exactly, but the winner draw and
  the landing draw are separate, documented draws.

## Colours

`PALETTE` is 8 distinct, high-contrast colours. A segment's
colour is its custom colour if given, else
`PALETTE[index % len(PALETTE)]` — with one adjustment for
the last segment: plain cycling would make the wrap-around
pair (last, first) share a colour whenever `N % 8 == 1`
(e.g. N = 9: segment 8 would take `PALETTE[0]` like segment
0). So for the last segment, `segments()` walks the palette
from the cycled position until it finds a colour different
from both the first segment's colour and the previous
segment's colour (with 8 palette entries such a colour
always exists). That guarantees every neighbouring pair,
including the wrap pair, differs in default mode for every
N > 1. Custom colours are the documented exception: a user
who paints two neighbours the same colour gets the same
colour — that is their explicit choice, and tests only
assert neighbour-difference for the default palette.
(For N = 2, both segments get different palette entries,
which is correct: two neighbours, twice over.)

## Rendering choice: terminal animation + static HTML/SVG

No GUI is allowed by this project's brief, so the page's
"visualised, seen spinning" requirement is met two ways:

1. Terminal spin animation: `animate_spin()` steps through
   `spin_frames()` — rotations interpolated with the
   ease-out cubic `1 - (1-t)^3` (fast start, slow finish,
   exactly the easing the page's spirit asks for) — printing
   the name currently under the pointer on one line, with a
   real `time.sleep` between frames. Animation is the only
   impure part; `spin_frames()` itself is pure and tested.
2. Static HTML/SVG snapshot: `render_svg()` / `render_html()`
   draw the wheel at its final rotation, with a pointer
   triangle at the top, segment wedges (SVG arc paths, angles
   converted from top-clockwise degrees to SVG x/y via
   `x = cx + r*sin(a)`, `y = cy - r*cos(a)`), the name text
   at 65% radius rotated to the segment's mid-angle, and a
   centre hub. `--html out.html` writes it; opening it in a
   browser shows the final wheel and the winner banner. The
   SVG has no JavaScript and no animation — the terminal
   animation is the animated view, and duplicating it in JS
   would be speculative extra code.

Text fit (Step 3): SVG labels are truncated to 18 characters
with an ellipsis if longer, and the font size shrinks as the
segment count grows (20pt for <=4 names, 16 for <=8, 12 for
<=16, 9 above that). The full name is always shown in the
terminal result and in the HTML winner banner, so truncation
never loses information — it only keeps labels inside wedges.

## CLI shape (thin shell only)

`main(argv)` parses flags and delegates; it never contains
spin logic. Flags: `--names a,b,c`, `--file path` (one name
per line; a line may also be `name|weight|#color` for advanced
entries), `--entry "Name[:weight[:#color]]"` (repeatable),
`--remove NAME` (repeatable), `--shuffle`, `--sort`,
`--seed N`, `--spin` (default action when names are given),
`--fast` (skip the animation, print the winner at once),
`--html PATH` (write the SVG snapshot of the final wheel),
`--list` (print the entries and exit). With no arguments at
all, `main` runs a small interactive prompt loop (`add`,
`remove`, `list`, `shuffle`, `sort`, `spin`, `html`, `quit`)
reading from stdin — the terminal equivalent of the page's
text box plus buttons. Bad flags / bad entries fail via
argparse / ValueError before any spin happens.

## What is deliberately not built

- No persistence format beyond the plain name list: saving
  wheels is a Going Further item, not a numbered step.
- No network, no Discord bot, no deployment.
- No colour picker UI: colours are `#RRGGBB` strings, which
  is the terminal equivalent of the page's advanced mode.

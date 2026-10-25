#!/usr/bin/env python3
"""Wheel of Names — terminal wheel with an HTML/SVG snapshot.

Build Your Own Wheel of Names (codingchallenges.fyi,
challenge-wheel): enter names, shuffle/sort them, draw a
wheel with one segment per name, spin it with a slowing
animation, and display a winner. Advanced mode: per-entry
weight (segment size) and colour.

Python 3 standard library only. All spin/selection logic is
pure and takes an optional seeded ``random.Random`` so tests
can reproduce a spin exactly; only ``animate_spin``,
``main`` and the interactive prompt touch the terminal.
"""

import argparse
import html
import math
import random
import re
import sys
import time
from dataclasses import dataclass

PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8",
    "#f58231", "#911eb4", "#42d4f4", "#f032e6",
]

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_MAX_LABEL = 18


@dataclass(frozen=True)
class Entry:
    """One wheel entry: a name, a size weight, an optional colour."""

    name: str
    weight: float = 1.0
    color: str | None = None

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("entry name must not be blank")
        if not isinstance(self.weight, (int, float)) or not math.isfinite(self.weight):
            raise ValueError(f"weight must be a finite number, got {self.weight!r}")
        if self.weight <= 0:
            raise ValueError(f"weight must be > 0, got {self.weight!r}")
        if self.color is not None and not _COLOR_RE.match(self.color):
            raise ValueError(f"color must be #RRGGBB, got {self.color!r}")


@dataclass(frozen=True)
class Segment:
    """One drawn slice: entry, position, and resolved colour."""

    entry: Entry
    index: int
    start_deg: float
    sweep_deg: float
    color: str


@dataclass(frozen=True)
class SpinResult:
    """Outcome of a spin: winner first, animation geometry second."""

    winner: Entry
    index: int
    total_deg: float  # full rotation travelled, incl. whole turns
    final_deg: float  # total_deg mod 360, the resting rotation
    turns: int


# ---------------------------------------------------------------- names

def parse_names(text):
    """One name per line: strip whitespace, drop blank lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_entry_line(line):
    """Parse one file/flag entry: ``name`` or ``name|weight`` or
    ``name|weight|#color``. A missing weight means 1, a missing
    colour means the palette. Raises ValueError on bad input."""
    parts = [p.strip() for p in line.split("|")]
    if not parts or not parts[0]:
        raise ValueError(f"empty entry: {line!r}")
    if len(parts) > 3:
        raise ValueError(f"too many '|' fields in entry: {line!r}")
    weight = 1.0
    if len(parts) >= 2 and parts[1] != "":
        try:
            weight = float(parts[1])
        except ValueError:
            raise ValueError(f"bad weight in entry: {line!r}") from None
    color = parts[2] if len(parts) == 3 and parts[2] != "" else None
    return Entry(parts[0], weight, color)


def parse_flag_entry(spec):
    """Parse a --entry spec: ``Name``, ``Name:weight`` or
    ``Name:weight:#color`` (colon form, so '|' file lines and
    flag entries do not collide)."""
    parts = spec.split(":")
    if len(parts) > 3 or not parts[0].strip():
        raise ValueError(f"bad --entry spec: {spec!r}")
    weight = parts[1] if len(parts) >= 2 and parts[1] != "" else "1"
    color = parts[2] if len(parts) == 3 and parts[2] != "" else ""
    line = parts[0].strip() + "|" + weight
    if color:
        line += "|" + color
    return parse_entry_line(line)


def add_name(entries, name):
    """Return a new list with ``name`` appended (input untouched)."""
    entry = Entry(name.strip())
    return list(entries) + [entry]


def remove_name(entries, name):
    """Return a new list minus the first entry exactly equal to
    ``name``; unchanged if no entry matches."""
    out = list(entries)
    for i, entry in enumerate(out):
        if entry.name == name:
            del out[i]
            break
    return out


def shuffle_names(entries, rng=None):
    """Return a new list in shuffled order (input untouched)."""
    rng = rng or random
    out = list(entries)
    rng.shuffle(out)
    return out


def sort_names(entries):
    """Return a new list sorted case-insensitively, stably."""
    return sorted(entries, key=lambda e: e.name.casefold())


# ---------------------------------------------------------------- wheel

def segments(entries):
    """Segments for ``entries``: sweeps sum to 360, starts are
    cumulative from 0 (top, clockwise). Default colours cycle
    the palette, with the last segment adjusted so it differs
    from both its predecessor and the first segment (see
    docs/DESIGN.md). Raises ValueError on an empty wheel."""
    entries = list(entries)
    if not entries:
        raise ValueError("cannot draw a wheel with no names")
    total = sum(e.weight for e in entries)
    segs = []
    start = 0.0
    for i, entry in enumerate(entries):
        sweep = 360.0 * entry.weight / total
        if entry.color is not None:
            color = entry.color
        elif i < len(entries) - 1:
            color = PALETTE[i % len(PALETTE)]
        else:
            # Last segment: avoid a wrap-around colour clash.
            first = PALETTE[0]
            prev = segs[-1].color if segs else None
            color = next(
                c for c in (PALETTE[(len(entries) - 1 + k) % len(PALETTE)]
                            for k in range(len(PALETTE)))
                if c != first and c != prev
            ) if len(entries) > 1 else PALETTE[0]
        segs.append(Segment(entry, i, start, sweep, color))
        start += sweep
    return segs


def winner_for_angle(angle_deg, segs):
    """Index of the segment containing wheel angle ``angle_deg``
    (degrees clockwise from the top, normalised). An exact
    segment start belongs to the segment starting there."""
    if not segs:
        raise ValueError("cannot pick a winner from an empty wheel")
    angle = angle_deg % 360.0
    for seg in segs:
        if seg.start_deg <= angle < seg.start_deg + seg.sweep_deg:
            return seg.index
    return segs[-1].index  # floating-point guard at the 360 edge


def spin(entries, rng=None, min_turns=5, max_turns=10):
    """Spin the wheel: pick the winner first, then a resting
    rotation that puts the pointer on it. Uniform mode uses
    randrange; weighted mode uses one choices() draw so odds
    are proportional to weight. Returns a SpinResult; the
    pointer angle for the result is ``(-final_deg) % 360``."""
    rng = rng or random
    segs = segments(entries)
    weighted = any(e.weight != 1.0 for e in entries)
    if weighted:
        index = rng.choices(range(len(segs)),
                            weights=[e.weight for e in entries])[0]
    else:
        index = rng.randrange(len(segs))
    seg = segs[index]
    # Landing angle inside the winner's segment, uniformly.
    pointer = seg.start_deg + rng.random() * seg.sweep_deg
    turns = rng.randint(min_turns, max_turns)
    final = (-pointer) % 360.0
    return SpinResult(seg.entry, index, turns * 360.0 + final, final, turns)


def spin_frames(result, steps=60):
    """Pure animation curve: ``steps``+1 rotations from 0 to the
    spin total, eased with ease-out cubic (fast start, slow
    finish). No sleeping here — the caller paces the frames."""
    total = result.total_deg
    return [total * (1.0 - (1.0 - t / steps) ** 3) for t in range(steps + 1)]


# ---------------------------------------------------------------- render

def _polar(cx, cy, radius, angle_deg):
    """Point at ``angle_deg`` clockwise from the top."""
    rad = math.radians(angle_deg)
    return cx + radius * math.sin(rad), cy - radius * math.cos(rad)


def _label(name):
    if len(name) > _MAX_LABEL:
        return name[: _MAX_LABEL - 1] + "…"
    return name


def _font_size(n):
    if n <= 4:
        return 20
    if n <= 8:
        return 16
    if n <= 16:
        return 12
    return 9


def render_svg(entries, rotation_deg=0.0, winner=None):
    """SVG document (as a string) of the wheel at ``rotation_deg``,
    pointer at the top, centre hub. Names are truncated labels;
    the full winner name, if given, is shown in the caption."""
    segs = segments(entries)
    cx = cy = 200
    radius = 180
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="460" viewBox="0 0 400 460">',
        # Pointer at the top.
        '<polygon points="200,2 188,28 212,28" fill="#222" id="pointer"/>',
        f'<g transform="rotate({rotation_deg:.2f} 200 200)">',
    ]
    for seg in segs:
        start = seg.start_deg
        end = start + seg.sweep_deg
        x1, y1 = _polar(cx, cy, radius, start)
        x2, y2 = _polar(cx, cy, radius, end)
        large = 1 if seg.sweep_deg > 180 else 0
        if seg.sweep_deg >= 360:
            parts.append(f'<circle cx="200" cy="200" r="180" fill="{seg.color}"/>')
        else:
            parts.append(
                f'<path d="M 200 200 L {x1:.1f} {y1:.1f} '
                f'A 180 180 0 {large} 1 {x2:.1f} {y2:.1f} Z" '
                f'fill="{seg.color}" stroke="white" stroke-width="2"/>'
            )
        mid = start + seg.sweep_deg / 2
        tx, ty = _polar(cx, cy, radius * 0.62, mid)
        parts.append(
            f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{_font_size(len(segs))}" '
            f'font-family="sans-serif" text-anchor="middle" dominant-baseline="middle" '
            f'transform="rotate({mid:.1f} {tx:.1f} {ty:.1f})" fill="#111">'
            f'{html.escape(_label(seg.entry.name))}</text>'
        )
    parts.append('</g>')
    parts.append('<circle cx="200" cy="200" r="32" fill="white" stroke="#222" stroke-width="2"/>')
    parts.append('<circle cx="200" cy="200" r="8" fill="#222"/>')
    if winner is not None:
        parts.append(
            f'<text x="200" y="440" font-size="22" font-family="sans-serif" '
            f'text-anchor="middle" font-weight="bold">Winner: {html.escape(winner.name)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(entries, rotation_deg=0.0, winner=None):
    """Standalone HTML document embedding the SVG wheel."""
    title = "Wheel of Names"
    body = render_svg(entries, rotation_deg, winner)
    names = "".join(f"<li>{html.escape(e.name)}</li>\n" for e in entries)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>\n"
        f"<h1>{title}</h1>\n{body}\n<ul>\n{names}</ul>\n"
        "</body></html>\n"
    )


def animate_spin(entries, result, steps=60, delay=0.05, out=None):
    """Terminal spin animation: print the name under the pointer
    as the wheel slows, then the winner. ``delay`` may be 0."""
    out = out if out is not None else sys.stdout
    segs = segments(entries)
    for rotation in spin_frames(result, steps):
        pointer = (-rotation) % 360.0
        name = segs[winner_for_angle(pointer, segs)].entry.name
        out.write(f"\r▶ {name}   ")
        out.flush()
        if delay:
            time.sleep(delay)
    out.write(f"\r★ Winner: {result.winner.name} ★\n")
    out.flush()


# ---------------------------------------------------------------- CLI

class Wheel:
    """Thin mutable wrapper over the pure functions."""

    def __init__(self, entries=()):
        self.entries = list(entries)

    def add(self, name):
        self.entries = add_name(self.entries, name)

    def remove(self, name):
        self.entries = remove_name(self.entries, name)

    def shuffle(self, rng=None):
        self.entries = shuffle_names(self.entries, rng)

    def sort(self):
        self.entries = sort_names(self.entries)

    def segments(self):
        return segments(self.entries)

    def spin(self, rng=None):
        return spin(self.entries, rng)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Wheel of Names")
    parser.add_argument("--names", help="comma-separated names")
    parser.add_argument("--file", help="file with one name per line "
                        "(lines may be name|weight|#color)")
    parser.add_argument("--entry", action="append", default=[],
                        help="advanced entry Name[:weight[:#color]], repeatable")
    parser.add_argument("--remove", action="append", default=[],
                        help="remove this name (first match), repeatable")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--sort", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--spin", action="store_true",
                        help="spin (default when names are given)")
    parser.add_argument("--fast", action="store_true",
                        help="skip the spin animation")
    parser.add_argument("--html", metavar="PATH",
                        help="write an HTML/SVG snapshot of the final wheel")
    parser.add_argument("--list", action="store_true",
                        help="print the entries and exit")
    return parser.parse_args(argv)


def build_wheel(args):
    """Build a Wheel from parsed args. Raises ValueError if no
    usable names result (argparse handles flag syntax itself)."""
    entries = []
    if args.names:
        entries.extend(Entry(n) for n in parse_names(args.names.replace(",", "\n")))
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(parse_entry_line(line))
    for spec in args.entry:
        entries.append(parse_flag_entry(spec))
    wheel = Wheel(entries)
    for name in args.remove:
        wheel.remove(name)
    if args.shuffle:
        wheel.shuffle()
    if args.sort:
        wheel.sort()
    if not wheel.entries:
        raise ValueError("no names given: use --names, --file or --entry")
    return wheel


def interactive():
    """Prompt loop: the terminal equivalent of the page's text
    box plus Shuffle / Sort / Spin buttons."""
    wheel = Wheel()
    print("Wheel of Names — type 'help' for commands.")
    while True:
        try:
            line = input("wheel> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        cmd, rest = cmd.lower(), rest.strip()
        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print("add NAME | remove NAME | list | shuffle | sort | "
                      "spin [--fast] | html PATH | quit")
            elif cmd == "add":
                wheel.add(rest)
            elif cmd == "remove":
                wheel.remove(rest)
            elif cmd == "list":
                for e in wheel.entries:
                    print(f"- {e.name} (weight {e.weight}"
                          f"{', ' + e.color if e.color else ''})")
            elif cmd == "shuffle":
                wheel.shuffle()
                print("shuffled.")
            elif cmd == "sort":
                wheel.sort()
                print("sorted.")
            elif cmd == "spin":
                result = wheel.spin()
                if rest == "--fast":
                    print(f"★ Winner: {result.winner.name} ★")
                else:
                    animate_spin(wheel.entries, result)
            elif cmd == "html":
                if not rest:
                    print("usage: html PATH")
                    continue
                with open(rest, "w", encoding="utf-8") as fh:
                    fh.write(render_html(wheel.entries))
                print(f"wrote {rest}")
            else:
                print(f"unknown command: {cmd} (type 'help')")
        except ValueError as exc:
            print(f"error: {exc}")
    return 0


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if len(sys.argv) == 1 and argv is None:
        return interactive()
    if argv is not None and not argv:
        return interactive()
    try:
        wheel = build_wheel(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for e in wheel.entries:
            print(e.name)
        return 0
    rng = random.Random(args.seed) if args.seed is not None else None
    result = wheel.spin(rng)
    if args.fast:
        print(f"★ Winner: {result.winner.name} ★")
    else:
        animate_spin(wheel.entries, result)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(wheel.entries, result.final_deg, result.winner))
        print(f"wrote {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Terminal sort visualiser — Python 3 standard library only.

Instruments bubble, selection, insertion, merge and quick sort so
each emits an ordered list of steps (compare / swap / overwrite /
pivot / done), each step carrying a snapshot of the array after
that step. Steps can be replayed (see replay_steps) and rendered
as ASCII bar charts (see render_array / render_frame).

Usage:
    python3 sort_visualiser.py --values 5,3,8 --algorithm bubble
    python3 sort_visualiser.py --algorithm quick --size 12 --seed 7
    python3 sort_visualiser.py --list
"""

import argparse
import random
import sys
import time
from dataclasses import dataclass, field

ALGORITHMS = ("bubble", "selection", "insertion", "merge", "quick")


@dataclass
class Step:
    """One instrumented operation. ``array`` is a snapshot AFTER it."""

    kind: str  # "compare" | "swap" | "overwrite" | "pivot" | "done"
    indices: tuple = ()
    array: list = field(default_factory=list)
    value: object = None  # for "overwrite": the value written


@dataclass
class SortResult:
    algorithm: str
    original: list
    sorted_values: list
    steps: list
    comparisons: int = 0
    swaps: int = 0
    overwrites: int = 0


class _Tracer:
    """Collects steps and counters while an algorithm mutates a list."""

    def __init__(self, values):
        self.a = list(values)
        self.steps = []
        self.comparisons = 0
        self.swaps = 0
        self.overwrites = 0

    def compare(self, i, j):
        self.comparisons += 1
        self.steps.append(Step("compare", (i, j), list(self.a)))

    def swap(self, i, j):
        if i == j:
            return
        self.a[i], self.a[j] = self.a[j], self.a[i]
        self.swaps += 1
        self.steps.append(Step("swap", (i, j), list(self.a)))

    def overwrite(self, i, value):
        self.a[i] = value
        self.overwrites += 1
        self.steps.append(Step("overwrite", (i,), list(self.a), value))

    def pivot(self, i):
        self.steps.append(Step("pivot", (i,), list(self.a)))

    def finish(self):
        self.steps.append(Step("done", (), list(self.a)))
        return SortResult(
            algorithm="",
            original=[],
            sorted_values=list(self.a),
            steps=self.steps,
            comparisons=self.comparisons,
            swaps=self.swaps,
            overwrites=self.overwrites,
        )


def _bubble(t):
    a, n = t.a, len(t.a)
    for end in range(n - 1, 0, -1):
        swapped = False
        for j in range(end):
            t.compare(j, j + 1)
            if a[j] > a[j + 1]:
                t.swap(j, j + 1)
                swapped = True
        if not swapped:
            break


def _selection(t):
    a, n = t.a, len(t.a)
    for i in range(n - 1):
        low = i
        for j in range(i + 1, n):
            t.compare(j, low)
            if a[j] < a[low]:
                low = j
        t.swap(i, low)


def _insertion(t):
    # Adjacent-swap form: each element bubbles left while smaller
    # than its predecessor (see DESIGN.md for why, not shift form).
    a, n = t.a, len(t.a)
    for i in range(1, n):
        j = i
        while j > 0:
            t.compare(j - 1, j)
            if a[j - 1] > a[j]:
                t.swap(j - 1, j)
                j -= 1
            else:
                break


def _merge(t):
    a = t.a

    def sort(lo, hi):
        if hi - lo <= 1:
            return
        mid = (lo + hi) // 2
        sort(lo, mid)
        sort(mid, hi)
        merged = []
        i, j = lo, mid
        while i < mid and j < hi:
            t.compare(i, j)
            if a[i] <= a[j]:  # left wins ties: stable
                merged.append(a[i])
                i += 1
            else:
                merged.append(a[j])
                j += 1
        merged.extend(a[i:mid])
        merged.extend(a[j:hi])
        for k, value in enumerate(merged):
            t.overwrite(lo + k, value)

    sort(0, len(a))


def _quick(t):
    a = t.a

    def partition(lo, hi):
        pivot = a[hi]
        t.pivot(hi)
        i = lo
        for j in range(lo, hi):
            t.compare(j, hi)
            if a[j] <= pivot:
                t.swap(i, j)
                i += 1
        t.swap(i, hi)
        return i

    def sort(lo, hi):
        if lo < hi:
            p = partition(lo, hi)
            sort(lo, p - 1)
            sort(p + 1, hi)

    sort(0, len(a) - 1)


_RUNNERS = {
    "bubble": _bubble,
    "selection": _selection,
    "insertion": _insertion,
    "merge": _merge,
    "quick": _quick,
}


def sort_with_steps(values, algorithm):
    """Sort ``values`` with ``algorithm``; return a SortResult."""
    if algorithm not in _RUNNERS:
        raise ValueError(
            f"unknown algorithm {algorithm!r} (choose from {', '.join(ALGORITHMS)})"
        )
    t = _Tracer(values)
    _RUNNERS[algorithm](t)
    result = t.finish()
    result.algorithm = algorithm
    result.original = list(values)
    return result


def replay_steps(values, steps):
    """Apply only the mutating steps, in order; return the result.

    The step-sequence consistency invariant is:
    replay_steps(original, steps) == sorted(original), and every
    step snapshot equals replaying the mutating steps up to it.
    """
    a = list(values)
    for step in steps:
        if step.kind == "swap":
            i, j = step.indices
            a[i], a[j] = a[j], a[i]
        elif step.kind == "overwrite":
            (i,) = step.indices
            a[i] = step.value
    return a


def render_array(values, highlight=(), max_width=40):
    """One row per element: marker, index, value, '#' bar."""
    if not values:
        return ""
    highlight = set(highlight)
    top = max(values) if max(values) > 0 else 0
    lines = []
    for i, value in enumerate(values):
        marker = "*" if i in highlight else " "
        bar_len = round(value / top * max_width) if top > 0 and value > 0 else 0
        lines.append(f"{marker} {i:>2} {value:>3} {'#' * bar_len}")
    return "\n".join(lines)


def render_frame(result, step_index, max_width=40):
    """Header + bar chart for steps[step_index]."""
    step = result.steps[step_index]
    header = (
        f"{result.algorithm}  step {step_index + 1}/{len(result.steps)}"
        f"  {step.kind} {list(step.indices)}"
    )
    body = render_array(step.array, highlight=step.indices, max_width=max_width)
    return header + ("\n" + body if body else "")


def summary(result):
    return (
        f"algorithm: {result.algorithm}\n"
        f"input: {' '.join(map(str, result.original))}\n"
        f"sorted: {' '.join(map(str, result.sorted_values))}\n"
        f"comparisons: {result.comparisons}  "
        f"swaps: {result.swaps}  "
        f"overwrites: {result.overwrites}  "
        f"steps: {len(result.steps)}"
    )


def parse_values(text):
    try:
        return [int(part) for part in text.split(",") if part.strip() != ""]
    except ValueError:
        raise ValueError(f"non-integer value in --values {text!r}")


def build_parser():
    p = argparse.ArgumentParser(description="Terminal sort visualiser.")
    p.add_argument("--algorithm", default="bubble",
                   help=f"one of: {', '.join(ALGORITHMS)}")
    p.add_argument("--values", default=None,
                   help="comma-separated integers, e.g. 5,3,8 (takes "
                        "precedence over --size)")
    p.add_argument("--size", type=int, default=10, help="random array size")
    p.add_argument("--max", type=int, default=20, dest="max_value",
                   help="largest random value (values are 1..max)")
    p.add_argument("--seed", type=int, default=None, help="random seed")
    p.add_argument("--mode", default="animate",
                   choices=("animate", "step", "all", "stats"),
                   help="animate: redraw with delay; step: Enter per "
                        "frame; all: print all frames; stats: summary only")
    p.add_argument("--delay", type=float, default=0.2,
                   help="seconds between frames in animate mode")
    p.add_argument("--max-width", type=int, default=40,
                   help="bar width for the largest value")
    p.add_argument("--list", action="store_true",
                   help="list algorithms and exit")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.list:
        print("\n".join(ALGORITHMS))
        return 0
    if args.algorithm not in ALGORITHMS:
        print(f"error: unknown algorithm {args.algorithm!r}",
              file=sys.stderr)
        return 2
    if args.size < 0 or args.max_value < 1 or args.delay < 0:
        print("error: --size must be >= 0, --max >= 1, --delay >= 0",
              file=sys.stderr)
        return 2
    if args.values is not None:
        try:
            values = parse_values(args.values)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        rng = random.Random(args.seed)
        values = [rng.randint(1, args.max_value) for _ in range(args.size)]
    result = sort_with_steps(values, args.algorithm)

    if args.mode == "stats":
        print(summary(result))
        return 0
    if args.mode == "step":
        for i in range(len(result.steps)):
            print(render_frame(result, i, args.max_width))
            if i + 1 < len(result.steps):
                try:
                    input("Enter for next step (EOF to stop)... ")
                except EOFError:
                    break
        print(summary(result))
        return 0
    if args.mode == "all":
        for i in range(len(result.steps)):
            print(render_frame(result, i, args.max_width))
            print()
        print(summary(result))
        return 0
    # animate
    for i in range(len(result.steps)):
        print("\033[2J\033[H", end="")  # clear screen, home cursor
        print(render_frame(result, i, args.max_width))
        if i + 1 < len(result.steps):
            time.sleep(args.delay)
    print(summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

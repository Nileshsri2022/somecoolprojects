"""Tests for wheel.py — all pure, seeded RNG, no terminal."""

import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wheel import (Entry, Wheel, add_name, animate_spin, build_wheel,
                   parse_args, parse_entry_line, parse_flag_entry,
                   parse_names, remove_name, render_html, render_svg,
                   segments, shuffle_names, sort_names, spin,
                   spin_frames, winner_for_angle)


def entries(*names):
    return [Entry(n) for n in names]


class TestParsing(unittest.TestCase):
    def test_parse_names_strips_and_drops_blanks(self):
        self.assertEqual(parse_names(" Alice \n\nBob\n  Carol  \n"),
                         ["Alice", "Bob", "Carol"])

    def test_parse_names_empty(self):
        self.assertEqual(parse_names("  \n\n"), [])

    def test_parse_entry_line_forms(self):
        self.assertEqual(parse_entry_line("Alice"), Entry("Alice", 1.0, None))
        self.assertEqual(parse_entry_line("Bob|2.5"), Entry("Bob", 2.5, None))
        self.assertEqual(parse_entry_line("Carol|1|#e6194b"),
                         Entry("Carol", 1.0, "#e6194b"))

    def test_parse_entry_line_bad(self):
        for bad in ("", "   ", "Bob|abc", "Bob|1|red", "Bob|1|#12345",
                    "a|b|c|d"):
            with self.assertRaises(ValueError, msg=bad):
                parse_entry_line(bad)

    def test_parse_flag_entry(self):
        self.assertEqual(parse_flag_entry("Alice:2:#e6194b"),
                         Entry("Alice", 2.0, "#e6194b"))
        self.assertEqual(parse_flag_entry("Bob"), Entry("Bob", 1.0, None))
        with self.assertRaises(ValueError):
            parse_flag_entry("Bob:0")

    def test_add_name_new_list_and_blank_rejected(self):
        orig = entries("Alice")
        out = add_name(orig, " Bob ")
        self.assertEqual([e.name for e in out], ["Alice", "Bob"])
        self.assertEqual([e.name for e in orig], ["Alice"])
        with self.assertRaises(ValueError):
            add_name(orig, "   ")

    def test_remove_first_match_only(self):
        orig = entries("Alice", "Bob", "Alice")
        out = remove_name(orig, "Alice")
        self.assertEqual([e.name for e in out], ["Bob", "Alice"])
        self.assertEqual([e.name for e in orig], ["Alice", "Bob", "Alice"])
        self.assertEqual(remove_name(orig, "Zed"), orig)

    def test_shuffle_seeded_deterministic_permutation(self):
        orig = entries("a", "b", "c", "d", "e")
        first = shuffle_names(orig, random.Random(7))
        second = shuffle_names(orig, random.Random(7))
        self.assertEqual([e.name for e in first], [e.name for e in second])
        self.assertEqual(sorted(e.name for e in first), ["a", "b", "c", "d", "e"])
        self.assertEqual([e.name for e in orig], ["a", "b", "c", "d", "e"])

    def test_sort_casefold_stable(self):
        orig = entries("banana", "Apple", "apple", "Cherry")
        out = sort_names(orig)
        self.assertEqual([e.name for e in out],
                         ["Apple", "apple", "banana", "Cherry"])
        self.assertEqual([e.name for e in orig],
                         ["banana", "Apple", "apple", "Cherry"])


class TestSegments(unittest.TestCase):
    def test_uniform_sums_and_starts(self):
        segs = segments(entries("a", "b", "c", "d"))
        self.assertAlmostEqual(sum(s.sweep_deg for s in segs), 360.0)
        self.assertEqual([s.start_deg for s in segs], [0.0, 90.0, 180.0, 270.0])
        self.assertTrue(all(s.sweep_deg == 90.0 for s in segs))

    def test_single_entry_full_circle(self):
        segs = segments(entries("Solo"))
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].sweep_deg, 360.0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            segments([])

    def test_neighbour_colours_differ(self):
        for n in (2, 3, 8, 9, 17):
            segs = segments([Entry(f"n{i}") for i in range(n)])
            for i, seg in enumerate(segs):
                nxt = segs[(i + 1) % n]
                self.assertNotEqual(seg.color, nxt.color,
                                    msg=f"n={n} segments {i} and {(i + 1) % n}")

    def test_weighted_proportions_and_custom_colour(self):
        segs = segments([Entry("a", 1.0), Entry("b", 3.0, "#123456")])
        self.assertAlmostEqual(segs[0].sweep_deg, 90.0)
        self.assertAlmostEqual(segs[1].sweep_deg, 270.0)
        self.assertEqual(segs[1].color, "#123456")

    def test_bad_entry_construction(self):
        for kwargs in ({"name": ""}, {"name": "x", "weight": 0},
                       {"name": "x", "weight": -1},
                       {"name": "x", "weight": float("nan")},
                       {"name": "x", "weight": float("inf")},
                       {"name": "x", "color": "red"},
                       {"name": "x", "color": "#12345"}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                Entry(**kwargs)


class TestSpin(unittest.TestCase):
    def test_winner_for_angle_boundaries(self):
        segs = segments(entries("a", "b", "c", "d"))
        self.assertEqual(winner_for_angle(0, segs), 0)
        self.assertEqual(winner_for_angle(90, segs), 1)
        self.assertEqual(winner_for_angle(359.9, segs), 3)
        self.assertEqual(winner_for_angle(360, segs), 0)
        self.assertEqual(winner_for_angle(-10, segs), 3)

    def test_spin_reproducible_and_consistent(self):
        wheel = entries("Alice", "Bob", "Carol", "Dave")
        r1 = spin(wheel, random.Random(42))
        r2 = spin(wheel, random.Random(42))
        self.assertEqual(r1, r2)
        self.assertEqual(r1.winner, wheel[r1.index])
        segs = segments(wheel)
        self.assertEqual(winner_for_angle((-r1.final_deg) % 360, segs), r1.index)
        self.assertTrue(5 <= r1.turns <= 10)
        self.assertGreaterEqual(r1.total_deg, r1.final_deg)

    def test_spin_weighted_reproducible_and_consistent(self):
        wheel = [Entry("a", 1.0), Entry("b", 3.0)]
        r1 = spin(wheel, random.Random(3))
        r2 = spin(wheel, random.Random(3))
        self.assertEqual(r1, r2)
        segs = segments(wheel)
        self.assertEqual(winner_for_angle((-r1.final_deg) % 360, segs), r1.index)

    def test_spin_empty_raises(self):
        with self.assertRaises(ValueError):
            spin([], random.Random(1))

    def test_spin_frames(self):
        result = spin(entries("a", "b"), random.Random(9))
        frames = spin_frames(result, steps=10)
        self.assertEqual(len(frames), 11)
        self.assertEqual(frames[0], 0.0)
        self.assertEqual(frames[-1], result.total_deg)
        self.assertTrue(all(b >= a for a, b in zip(frames, frames[1:])))
        # Ease-out cubic at t=0.5: 1 - (0.5)^3 = 0.875 of total.
        self.assertAlmostEqual(frames[5], result.total_deg * 0.875)


class TestRender(unittest.TestCase):
    def test_svg_contains_names_colours_pointer_hub(self):
        svg = render_svg(entries("Alice", "Bob", "Carol"))
        for name in ("Alice", "Bob", "Carol"):
            self.assertIn(name, svg)
        self.assertEqual(svg.count("<path"), 3)
        self.assertIn('id="pointer"', svg)
        self.assertIn('<circle cx="200" cy="200" r="32"', svg)

    def test_svg_rotation_and_single_circle(self):
        svg = render_svg(entries("Solo"), rotation_deg=45.0)
        self.assertIn("rotate(45.00", svg)
        self.assertIn("<circle", svg)
        svg2 = render_svg(entries("a", "b"), rotation_deg=0.0)
        self.assertIn("rotate(0.00", svg2)

    def test_svg_truncates_long_names(self):
        long_name = "A" * 30
        svg = render_svg(entries(long_name, "Bob"))
        self.assertNotIn(long_name, svg)
        self.assertIn("…", svg)

    def test_html_wraps_svg_and_winner(self):
        html_doc = render_html(entries("Alice", "Bob"), winner=Entry("Bob"))
        self.assertIn("<svg", html_doc)
        self.assertIn("Winner: Bob", html_doc)
        self.assertIn("<li>Alice</li>", html_doc)


class TestCli(unittest.TestCase):
    def test_parse_args(self):
        args = parse_args(["--names", "a,b", "--seed", "3", "--fast",
                           "--html", "out.html", "--shuffle"])
        self.assertEqual(args.names, "a,b")
        self.assertEqual(args.seed, 3)
        self.assertTrue(args.fast and args.shuffle)
        self.assertEqual(args.html, "out.html")

    def test_build_wheel_names_and_entry_and_remove(self):
        args = parse_args(["--names", "Alice,Bob,Carol",
                           "--entry", "Dave:2:#e6194b",
                           "--remove", "Bob"])
        wheel = build_wheel(args)
        self.assertEqual([e.name for e in wheel.entries],
                         ["Alice", "Carol", "Dave"])
        self.assertEqual(wheel.entries[-1].weight, 2.0)
        self.assertEqual(wheel.entries[-1].color, "#e6194b")

    def test_build_wheel_empty_rejected(self):
        args = parse_args(["--names", " , , "])
        with self.assertRaises(ValueError):
            build_wheel(args)

    def test_wheel_wrapper(self):
        wheel = Wheel(entries("b", "a"))
        wheel.sort()
        self.assertEqual([e.name for e in wheel.entries], ["a", "b"])
        wheel.shuffle(random.Random(1))
        self.assertEqual(sorted(e.name for e in wheel.entries), ["a", "b"])
        result = wheel.spin(random.Random(1))
        self.assertIn(result.winner.name, ("a", "b"))


if __name__ == "__main__":
    unittest.main()

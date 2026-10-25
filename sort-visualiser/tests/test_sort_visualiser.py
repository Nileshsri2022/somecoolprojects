import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sort_visualiser import (  # noqa: E402
    ALGORITHMS,
    parse_values,
    render_array,
    render_frame,
    replay_steps,
    sort_with_steps,
)

CASES = [
    [],
    [1],
    [1, 2, 3, 4, 5],
    [5, 4, 3, 2, 1],
    [3, 1, 4, 1, 5, 9, 2, 6, 5, 3],
    [-3, 0, -1, 5, 2, -3],
    random.Random(42).sample(range(100), 20),
]

MAIN = os.path.join(os.path.dirname(__file__), "..", "sort_visualiser.py")


class TestCorrectnessAndSteps(unittest.TestCase):
    def test_sorts_and_replays_for_every_algorithm_and_case(self):
        for algo in ALGORITHMS:
            for case in CASES:
                with self.subTest(algo=algo, case=case):
                    r = sort_with_steps(case, algo)
                    self.assertEqual(r.sorted_values, sorted(case))
                    self.assertEqual(replay_steps(case, r.steps),
                                     sorted(case))
                    # Last step is done, snapshot is sorted.
                    self.assertEqual(r.steps[-1].kind, "done")
                    self.assertEqual(r.steps[-1].array, sorted(case))
                    # Counters match the step list.
                    kinds = [s.kind for s in r.steps]
                    self.assertEqual(r.comparisons, kinds.count("compare"))
                    self.assertEqual(r.swaps, kinds.count("swap"))
                    self.assertEqual(r.overwrites, kinds.count("overwrite"))
                    # Every snapshot == replaying mutating steps to it.
                    for k, step in enumerate(r.steps):
                        self.assertEqual(
                            replay_steps(case, r.steps[: k + 1]), step.array)

    def test_step_semantics(self):
        for algo in ALGORITHMS:
            r = sort_with_steps([5, 2, 8, 2, 9], algo)
            prev = list(r.original)
            for step in r.steps:
                if step.kind == "compare" or step.kind == "pivot":
                    self.assertEqual(step.array, prev)
                elif step.kind == "swap":
                    i, j = step.indices
                    expect = list(prev)
                    expect[i], expect[j] = expect[j], expect[i]
                    self.assertEqual(step.array, expect)
                    self.assertNotEqual(i, j)
                elif step.kind == "overwrite":
                    (i,) = step.indices
                    expect = list(prev)
                    expect[i] = step.value
                    self.assertEqual(step.array, expect)
                    self.assertEqual(step.array[i], step.value)
                prev = step.array

    def test_bubble_early_exit(self):
        r = sort_with_steps([1, 2, 3, 4, 5], "bubble")
        self.assertEqual(r.comparisons, 4)
        self.assertEqual(r.swaps, 0)

    def test_merge_is_stable(self):
        # Decorated pairs: equal values must keep original order.
        pairs = [(2, 0), (1, 1), (2, 2), (1, 3), (2, 4)]
        r = sort_with_steps(pairs, "merge")
        self.assertEqual(r.sorted_values, sorted(pairs))
        # Stability: second elements for value 1, then value 2, in order.
        self.assertEqual([i for _, i in r.sorted_values], [1, 3, 0, 2, 4])

    def test_unknown_algorithm(self):
        with self.assertRaises(ValueError):
            sort_with_steps([3, 1], "bogus")

    def test_parse_values(self):
        self.assertEqual(parse_values("5,3,8"), [5, 3, 8])
        with self.assertRaises(ValueError):
            parse_values("5,x,8")


class TestRendering(unittest.TestCase):
    def test_render_array(self):
        out = render_array([1, 4, 2], highlight=(1,), max_width=8)
        lines = out.split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("*", lines[1])
        self.assertNotIn("*", lines[0])
        self.assertIn("1", lines[0])
        self.assertEqual(lines[1].count("#"), 8)  # largest -> full width
        self.assertEqual(render_array([]), "")

    def test_render_frame_header(self):
        r = sort_with_steps([3, 1, 2], "bubble")
        header = render_frame(r, 0).split("\n")[0]
        self.assertIn("bubble", header)
        self.assertIn("step 1/", header)
        self.assertIn(r.steps[0].kind, header)


class TestCLI(unittest.TestCase):
    def run_cli(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, MAIN, *args], input=stdin,
            capture_output=True, text=True, timeout=30)

    def test_list(self):
        p = self.run_cli("--list")
        self.assertEqual(p.returncode, 0)
        for algo in ALGORITHMS:
            self.assertIn(algo, p.stdout)

    def test_stats_mode(self):
        p = self.run_cli("--values", "5,3,8", "--algorithm", "bubble",
                         "--mode", "stats")
        self.assertEqual(p.returncode, 0)
        self.assertIn("sorted: 3 5 8", p.stdout)

    def test_all_mode_prints_frames(self):
        p = self.run_cli("--values", "3,1,2", "--algorithm", "selection",
                         "--mode", "all")
        self.assertEqual(p.returncode, 0)
        self.assertIn("selection", p.stdout)
        self.assertIn("#", p.stdout)
        self.assertIn("sorted: 1 2 3", p.stdout)

    def test_values_take_precedence_over_size(self):
        p = self.run_cli("--values", "2,1", "--size", "99",
                         "--mode", "stats")
        self.assertEqual(p.returncode, 0)
        self.assertIn("input: 2 1", p.stdout)

    def test_step_mode_ends_on_eof(self):
        p = self.run_cli("--values", "2,1", "--mode", "step", stdin="")
        self.assertEqual(p.returncode, 0)
        self.assertIn("sorted: 1 2", p.stdout)

    def test_bad_algorithm_and_bad_values_fail(self):
        self.assertNotEqual(
            self.run_cli("--algorithm", "bogus").returncode, 0)
        self.assertNotEqual(
            self.run_cli("--values", "5,x").returncode, 0)


if __name__ == "__main__":
    unittest.main()

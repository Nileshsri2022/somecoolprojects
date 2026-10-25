"""Tests for gitviz. Fixture repos are created in temp dirs with system git.

Never reads the user's real repositories.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gitviz  # noqa: E402


def make_repo(path, commits):
    """Create a git repo at path with commits: list of (date_str, name, email)."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Fixture"],
                   check=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "fix@example.com"],
                   check=True)
    for i, (day, name, email) in enumerate(commits):
        fname = os.path.join(path, f"file{i}.txt")
        with open(fname, "w") as handle:
            handle.write(f"content {i}\n")
        subprocess.run(["git", "-C", path, "add", "."], check=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=f"{day}T12:00:00",
                   GIT_COMMITTER_DATE=f"{day}T12:00:00",
                   GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
        subprocess.run(["git", "-C", path, "commit", "-q", "-m", f"c{i}"],
                       check=True, env=env)
    return path


D = date


class TestFindRepos(unittest.TestCase):
    def test_challenge_example(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("ccwc", "ccsh", "ccredis"):
                make_repo(os.path.join(root, name), [])
                # make_repo inits an empty repo (no commits); still a repo dir.
            os.makedirs(os.path.join(root, "docs"))
            found = gitviz.find_repos(root)
            self.assertEqual(
                sorted(os.path.join(root, n) for n in ("ccwc", "ccsh", "ccredis")),
                found)

    def test_nested_repo_not_double_counted(self):
        with tempfile.TemporaryDirectory() as root:
            outer = make_repo(os.path.join(root, "outer"), [])
            make_repo(os.path.join(outer, "inner"), [])
            self.assertEqual([outer], gitviz.find_repos(root))

    def test_git_file_counts(self):
        with tempfile.TemporaryDirectory() as root:
            worktree = os.path.join(root, "wt")
            os.makedirs(worktree)
            with open(os.path.join(worktree, ".git"), "w") as handle:
                handle.write("gitdir: /elsewhere\n")
            self.assertIn(worktree, gitviz.find_repos(root))

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as root:
            real = make_repo(os.path.join(root, "real"), [])
            linkdir = os.path.join(root, "link")
            os.symlink(real, linkdir)
            self.assertEqual([real], gitviz.find_repos(root))

    def test_no_repos(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "plain"))
            self.assertEqual([], gitviz.find_repos(root))


class TestRepoCommits(unittest.TestCase):
    def test_parse_and_pipe_in_name(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(os.path.join(root, "r"), [
                ("2026-10-20", "A|B", "ab@example.com"),
                ("2026-10-20", "A|B", "ab@example.com"),
                ("2026-10-21", "C", "c@example.com"),
            ])
            commits = gitviz.repo_commits(repo)
            self.assertEqual(3, len(commits))
            # git log is newest-first; sort before asserting contents.
            self.assertEqual(
                (D(2026, 10, 20), "A|B", "ab@example.com"),
                sorted(commits)[0])

    def test_empty_repo_no_crash(self):
        with tempfile.TemporaryDirectory() as root:
            repo = make_repo(os.path.join(root, "r"), [])
            self.assertEqual([], gitviz.repo_commits(repo))


class TestFilterAggregate(unittest.TestCase):
    COMMITS = [
        (D(2026, 10, 20), "Alice", "alice@example.com"),
        (D(2026, 10, 20), "Alice", "alice@example.com"),
        (D(2026, 10, 21), "Bob", "bob@example.com"),
        (D(2026, 10, 25), "Alice", "alice@example.com"),  # future vs window end
    ]

    def test_window_inclusive_and_future_excluded(self):
        out = gitviz.filter_commits(self.COMMITS, D(2026, 10, 20), D(2026, 10, 21), None)
        self.assertEqual(3, len(out))

    def test_author_substring_name_and_email(self):
        self.assertEqual(2, len(gitviz.filter_commits(
            self.COMMITS, D(2026, 10, 20), D(2026, 10, 21), "ALICE")))
        self.assertEqual(1, len(gitviz.filter_commits(
            self.COMMITS, D(2026, 10, 20), D(2026, 10, 21), "bob@")))

    def test_author_tuple_matches_either(self):
        out = gitviz.filter_commits(
            self.COMMITS, D(2026, 10, 1), D(2026, 10, 31), ("Alice", "bob@example.com"))
        self.assertEqual(4, len(out))

    def test_aggregate(self):
        counts = gitviz.aggregate_by_day(self.COMMITS)
        self.assertEqual(2, counts[D(2026, 10, 20)])
        self.assertNotIn(D(2026, 10, 22), counts)


class TestHeatAndGrid(unittest.TestCase):
    def test_heat_boundaries(self):
        expected = {0: 0, 1: 1, 2: 1, 3: 2, 5: 2, 6: 3, 9: 3, 10: 4, 50: 4}
        for count, level in expected.items():
            self.assertEqual(level, gitviz.heat_level(count), f"count={count}")

    def test_grid_padding_and_placement(self):
        # 2026-10-21 is a Wednesday. Window Wed..Thu must pad back to Sun 18th.
        counts = {D(2026, 10, 21): 3}
        weeks, gs, ge = gitviz.build_week_grid(counts, D(2026, 10, 21), D(2026, 10, 22))
        self.assertEqual(D(2026, 10, 18), gs)  # Sunday
        self.assertEqual(D(2026, 10, 24), ge)  # Saturday
        self.assertEqual(1, len(weeks))
        self.assertEqual([None, None, None, 3, 0, None, None], weeks[0])

    def test_single_day_window_is_full_week(self):
        weeks, _gs, _ge = gitviz.build_week_grid({}, D(2026, 10, 25), D(2026, 10, 25))
        self.assertEqual(1, len(weeks))
        self.assertEqual(7, len(weeks[0]))


class TestStreaks(unittest.TestCase):
    def test_longest_with_gap(self):
        counts = {D(2026, 10, d): 1 for d in (1, 2, 3, 5, 6)}
        self.assertEqual(3, gitviz.longest_streak(counts, D(2026, 10, 1), D(2026, 10, 7)))

    def test_current_ending_today(self):
        counts = {D(2026, 10, d): 1 for d in (24, 25)}
        self.assertEqual(2, gitviz.current_streak(counts, D(2026, 10, 25)))

    def test_current_ending_yesterday_counts(self):
        counts = {D(2026, 10, d): 1 for d in (23, 24)}
        self.assertEqual(2, gitviz.current_streak(counts, D(2026, 10, 25)))

    def test_current_broken(self):
        counts = {D(2026, 10, 20): 1}
        self.assertEqual(0, gitviz.current_streak(counts, D(2026, 10, 25)))


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.counts = {D(2026, 10, 20): 12, D(2026, 10, 21): 1}
        self.stats = gitviz.compute_stats(
            [(D(2026, 10, 20), "Alice", "a@x.com")] * 12 +
            [(D(2026, 10, 21), "Alice", "a@x.com")],
            self.counts, D(2026, 10, 20), D(2026, 10, 21), D(2026, 10, 21))

    def test_text_has_legend_and_darkest_block(self):
        out = gitviz.render_text("T", self.counts, D(2026, 10, 20), D(2026, 10, 21),
                                 self.stats)
        self.assertIn("█", out)
        self.assertIn("Less", out)
        self.assertIn("Total commits: 13", out)

    def test_html_escapes_and_tooltips(self):
        evil = {"<script>alert(1)</script>": 5}
        out = gitviz.render_html("T", self.counts, D(2026, 10, 20), D(2026, 10, 21),
                                 self.stats, evil)
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("12 contributions on 2026-10-20", out)

    def test_json_round_trips(self):
        out = gitviz.render_json(D(2026, 10, 20), D(2026, 10, 21), self.stats,
                                 {"repoA": 13})
        payload = json.loads(out)
        self.assertEqual(13, payload["total"])
        self.assertEqual(13, payload["per_repo"]["repoA"])
        self.assertEqual("2026-10-20", payload["busiest_day"])


class TestCLI(unittest.TestCase):
    def test_end_to_end_json_filters_by_author(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(os.path.join(root, "r1"), [
                ("2026-10-20", "Alice", "alice@example.com"),
                ("2026-10-20", "Alice", "alice@example.com"),
                ("2026-10-21", "Bob", "bob@example.com"),
            ])
            make_repo(os.path.join(root, "r2"), [
                ("2026-10-21", "Alice", "alice@example.com"),
            ])
            # Window must cover the fixture dates: use a huge --days value
            # relative to today is fragile, so instead assert via main() with
            # --days large enough to reach 2026-10-20 from any near date.
            # Fixture dates are in the past relative to the 2026-10-25 run date,
            # so 3650 days safely covers them.
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = gitviz.main([root, "--days", "3650", "--author", "alice",
                                    "--format", "json"])
            self.assertEqual(0, code)
            payload = json.loads(buf.getvalue())
            self.assertEqual(3, payload["total"])  # Alice only, both repos
            self.assertEqual(2, len(payload["per_repo"]))

    def test_per_repo_text_names_repos(self):
        with tempfile.TemporaryDirectory() as root:
            r1 = make_repo(os.path.join(root, "r1"), [("2026-10-20", "A", "a@x.com")])
            make_repo(os.path.join(root, "r2"), [("2026-10-20", "A", "a@x.com")])
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = gitviz.main([root, "--days", "3650", "--all",
                                    "--per-repo"])
            self.assertEqual(0, code)
            self.assertIn(r1, buf.getvalue())

    def test_missing_root_exits_nonzero(self):
        self.assertNotEqual(0, gitviz.main(["/definitely/not/a/real/dir",
                                            "--format", "json"]))

    def test_days_zero_exits_nonzero(self):
        self.assertNotEqual(0, gitviz.main([".", "--days", "0"]))


class TestCurrentUserDoesNotCrash(unittest.TestCase):
    def test_returns_none_or_tuple(self):
        result = gitviz.current_user()
        self.assertTrue(result is None or isinstance(result, tuple))


if __name__ == "__main__":
    unittest.main()

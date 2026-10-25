# TEST_PLAN — Git Contributions Visualisation Tool

Run: `python3 -m unittest discover -s tests -v` from the project
directory. All tests use `tempfile.TemporaryDirectory`; no test
reads the user's real repositories, home directory, or git config
(except one test that asserts `current_user()` returns `None` or a
tuple without crashing — it does not assert a specific identity).

## Fixture strategy

Tests create real fixture git repositories with the system `git`
binary (available in this environment: git 2.43.0). Commits are made
with explicit `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` and explicit
author name/email, so dates are deterministic. A helper
`make_repo(path, commits)` builds a repo from a list of
`(date, author_name, author_email)` tuples. If `git` were absent,
these fixture tests would fail loudly rather than silently pass —
that is intentional; synthetic log fixtures are NOT used, because
the tool's repo-reading path is exactly what needs testing.

## Coverage

1. `find_repos`: finds repos among non-repo siblings (the challenge's
   ccwc/ccsh/ccredis/docs example); ignores `.git` internals; does
   not descend into a found repo (nested repo not double-counted);
   detects a `.git` file (worktree-style); skips symlinked dirs.
2. `repo_commits`: parses dates/names/emails; empty repo (no
   commits) yields no commits and no crash; author with a `|` in
   the name is not split (unit-separator format).
3. `filter_commits`: window boundaries inclusive; future dates
   excluded; author substring match on name and on email,
   case-insensitive; no filter keeps all.
4. `aggregate_by_day`: multiple commits on one day sum; days with
   no commits are absent (grid renders them as zero).
5. `heat_level`: boundary values 0, 1, 2, 3, 5, 6, 9, 10.
6. `build_week_grid`: window padded to Sunday/Saturday; out-of-
   window cells are `None`; a single-day window still yields a
   full week column; counts land in the correct weekday row.
7. Streaks: longest streak with a gap; current streak ending today,
   ending yesterday (still counts), and broken (0 when neither
   today nor yesterday has a commit).
8. Rendering: text output contains the legend, month labels, and
   the darkest block for a 10+ day; HTML output escapes a `<script>`
   string in a repo path/author name and contains the tooltip
   format; JSON output round-trips with ISO dates and correct
   totals.
9. End-to-end CLI: run `main()` (via `runpy`-style invocation of
   `gitviz.py` as a subprocess) against a temp tree with two
   repos, `--days` window, `--author` filter, and `--format json`;
   assert the reported total equals the fixture commits in window
   for that author only; assert `--per-repo` text output names
   both repos; assert a nonexistent root exits non-zero.

## Manual checks performed before reporting done

- Full unittest suite green (count reported in the final report).
- CLI smoke run against a temp fixture tree (not a real repo):
  text, HTML, and JSON outputs eyeballed for a sane grid and stats.
- `find . -name __pycache__` clean before finishing; no servers
  started at any point.

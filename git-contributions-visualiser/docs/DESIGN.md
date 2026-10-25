# DESIGN — Git Contributions Visualisation Tool

## Files

- `gitviz.py` — the whole tool (stdlib only). Pure functions are kept
  separate from I/O so the test suite can exercise logic without
  touching real repositories.
- `tests/test_gitviz.py` — unittest suite. Fixture repositories are
  created in `tempfile` directories with the system `git` binary
  (see TEST_PLAN.md); no user repository is ever read by the tests.
- `docs/SPEC.md`, `docs/DESIGN.md`, `docs/TEST_PLAN.md`,
  `README.md`.

## Pipeline

```
walk root ──> find_repos() ──> for each repo: git log ──> commits
   (skip .git,          (author date, name, email)
    no symlink follow,
    outer repo wins)
commits ──> filter by window + contributor ──> aggregate_by_day()
        ──> per-repo / per-contributor counters
        ──> build_week_grid() ──> render_text() / render_html() / render_json()
        ──> streaks: longest_streak(), current_streak()
```

## Key functions (in `gitviz.py`)

- `find_repos(root)` — `os.walk` with `followlinks=False`. A
  directory is a repo if it contains a `.git` directory or file
  (worktrees/submodules use a `.git` *file*), or if it looks like a
  bare repo (`HEAD`, `objects/`, `refs/` present). On finding a repo,
  its subdirectories are pruned from the walk.
- `current_user()` — runs `git config user.name` and
  `git config user.email` (global config of the invoking user). If
  both are empty, returns `None` (caller warns and includes all).
- `repo_commits(repo)` — runs
  `git -C <repo> log --format=%ad%x1f%an%x1f%ae --date=short`
  (unit-separator delimited; robust against `|` or spaces in
  names). A repo whose log fails (e.g. empty repo, no commits) is
  skipped with a warning on stderr, not a crash. Malformed lines
  are skipped.
- `filter_commits(commits, start, end, author)` — date window
  inclusive; author filter is a case-insensitive substring match
  against name or email, or `None` for "all".
- `aggregate_by_day(commits)` — `Counter` keyed by `datetime.date`.
- `heat_level(count)` — 0→0, 1–2→1, 3–5→2, 6–9→3, 10+→4.
- `build_week_grid(counts, start, end)` — pads `start` back to the
  preceding Sunday and `end` forward to the following Saturday;
  returns a list of week columns, each a list of 7 cells
  (`None` for out-of-window days, else the count). Month labels for
  the text/HTML headers are derived from the first day of each week
  column that starts a new month.
- `longest_streak(counts, start, end)` — longest run of consecutive
  days with count ≥ 1 inside the window.
- `current_streak(counts, today)` — run of consecutive commit days
  ending today; if today has no commit, the run ending yesterday
  counts (a streak is not "broken" by the current day being
  incomplete); if neither today nor yesterday has a commit, 0.
- `render_text(...)` — rows Sunday→Saturday, two-character cells
  (`· `, `░ `, `▒ `, `▓ `, `█ `), month header row, weekday labels
  (Sun/Mon/... only on the left for Sun, Wed, Sat to stay compact
  — actually all seven labels are printed, one per row, for
  readability), legend, and a stats block.
- `render_html(...)` — self-contained HTML, CSS grid of 12px
  squares, GitHub-like greens (`#ebedf0`, `#9be9a8`, `#40c463`,
  `#30a14e`, `#216e39`), `title` tooltips with "N contributions on
  YYYY-MM-DD", month labels, stats table. All user-controlled text
  (repo paths, author names) is passed through `html.escape`.
- `render_json(...)` — `{"window": ..., "total": ..., "per_repo":
  {...}, "per_contributor": {...}, "per_day": {...},
  "busiest_day": ..., "longest_streak": ...,
  "current_streak": ...}` with ISO dates.
- `main(argv)` — argparse; `--days` must be ≥ 1; `--format` is
  `text|html|json`; `--output` writes to a file (text/html/json as
  appropriate) instead of stdout; `--per-repo` adds a graph per
  repo to text/html output (JSON always contains per-repo totals).

## Error handling

- Missing root directory → error exit 2 with a clear message.
- `git` not on PATH → error exit 2 (checked once, up front).
- A single repo failing to read → warning on stderr, other repos
  still processed. Exit code stays 0 if at least the scan ran.
- `--days 0` or negative → argparse error (exit 2).
- `--author` and `--all` together → argparse error (mutually
  exclusive group).

## Testability

All aggregation, grid, streak, and rendering logic is pure and
takes explicit dates, so tests never depend on "today". Only
`find_repos`, `repo_commits`, and `current_user` touch the disk or
subprocesses, and tests drive those against temp fixture repos.

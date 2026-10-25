# Git Contributions Visualisation Tool

A Coding Challenge #62 build: visualise local git contribution history
as a GitHub-style contributions graph.

Challenge source (read directly):
<https://codingchallenges.substack.com/p/coding-challenge-62-git-contributions>
— also listed on codingchallenges.fyi under the `gui` tag. Full step
record, divergences, and scope limits: see `docs/SPEC.md`.

## What it does

- Walks a root folder, finds every directory containing a git
  repository (a `.git` dir/file, or a bare repo), skipping non-repos,
  `.git` internals, nested repos, and symlinks.
- Reads commit history via the system `git` binary (author date,
  author name/email) — it does **not** implement git, and it does
  **not** use the GitHub API. Only local clones are counted.
- Aggregates commits by day over the last N days (default 30) for a
  contributor (default: your configured git user; `--all` for
  everyone; `--author TEXT` for a substring match).
- Renders a week-column heatmap (Sundays on top, like GitHub) plus
  totals, per-repo and per-contributor counts, busiest day, longest
  streak, and current streak.

## Usage

```sh
python3 gitviz.py [ROOT] [--days N] [--author TEXT | --all]
                  [--format text|html|json] [--output FILE] [--per-repo]
```

Examples:

```sh
python3 gitviz.py ~/projects --days 90
python3 gitviz.py ~/projects --days 30 --all --format html --output graph.html
python3 gitviz.py ~/projects --author alice --format json
python3 gitviz.py ~/projects --per-repo   # a graph per repository too
```

Requirements: Python 3 (stdlib only) and `git` on PATH.

## Outputs

- `text` (default): terminal heatmap using `· ░ ▒ ▓ █`
  (0, 1–2, 3–5, 6–9, 10+ commits/day).
- `html`: self-contained static page (coloured squares, tooltips,
  stats tables). No JavaScript, no server, no external assets.
- `json`: per-day counts, per-repo and per-contributor totals,
  streaks.

## What is NOT built (plainly)

- No desktop GUI app and no web server — CLI + static HTML only
  (the challenge explicitly allows a CLI tool).
- No GitHub API access, no remote fetching/cloning.
- No hand-rolled `.git` parser; no result caching (every run
  re-reads `git log`).
- No per-contributor graphs (per-contributor totals only).

## Tests

```sh
python3 -m unittest discover -s tests -v
```

26 tests, all passing. Fixture repositories are created in temp
directories with system git; no real user repository is ever read
by the tests. See `docs/TEST_PLAN.md`.

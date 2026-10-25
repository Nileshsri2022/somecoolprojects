# SPEC — Git Contributions Visualisation Tool

## Challenge source (resolved)

- Canonical challenge text read in full: **Coding Challenge #62 — Git
  Contributions Visualisation Tool**, John Crickett, published
  2024-05-18.
- Resolved challenge URL (Substack, read directly):
  <https://codingchallenges.substack.com/p/coding-challenge-62-git-contributions>
- Site index confirmation: the challenge also appears on the
  codingchallenges.fyi tag page for `gui`
  (<https://codingchallenges.fyi/challenges/tags/gui>, "Build Your Own
  Git Contributions Visualisation Tool — This challenge is to build
  your own version of the GitHub contributions graph"). A follow-on
  fetch of that fyi challenge page itself was rate-limited upstream
  (HTTP 429) and was NOT retried, so no fyi challenge-page URL is
  claimed here. The spec below is taken from the Substack text, which
  is the same challenge (#62) and was read end to end. No URL was
  guessed.
- Tags on codingchallenges.fyi: beginner, cli, gui.

## What the challenge asks for

Build a tool that creates a graphical visualisation of the commits
made by a user, in the style of the GitHub contributions graph.
The challenge's steps (paraphrased faithfully; the original text
numbers no steps after "Step Zero"):

1. **Step Zero — setup.** IDE/editor and language of choice. The
   challenge explicitly allows a CLI tool, a desktop tool, or a local
   analyser that pushes data to a remote server for web rendering.
   The choice is the builder's.
2. **Find git repositories.** Given a directory tree, find the folders
   that contain a Git repository (i.e. a `.git` entry). Example from
   the challenge: `ccwc`, `ccsh`, `ccredis` contain a repo, `docs`
   does not.
3. **Analyse one repository.** Determine how many commits there have
   been in the previous 30 days **by the current user**. The challenge
   suggests using a library to parse a repo, or, for the experienced,
   building on the Build-Your-Own-Git-Client challenge to parse the
   repository directly.
4. **User-configurable root and window.** Allow the user to specify
   the starting location for the search (the root folder) and the
   number of days to go back when generating the visualisation.
5. **Stats per repository.** Calculate all the stats for each
   repository. The challenge explicitly suggests a test suite for
   this step, to check the logic gathers stats correctly and
   correctly identifies the contributor.
6. **Render the graph.** Render the contribution graph for the
   specified time period, similar to the GitHub contribution graph;
   creative alternatives are explicitly allowed.
7. **Going further (optional, not required):** per-repository graph,
   stats for each contributor, caching results so only new commits
   since the last date are recalculated (with edge cases handled).

## This implementation

- Language: Python 3, standard library only. One main file:
  `gitviz.py`. No third-party packages, no GitHub API, no network.
- Input source: **local git repositories on disk**, found by walking
  a root directory. Commit data is read by invoking the system `git`
  binary (`git -C <repo> log`) — this is NOT a re-implementation of
  git, and NOT the Build-Your-Own-Git-Client project. See
  "Divergences" below.
- Outputs produced:
  - Terminal ASCII/Unicode heatmap (default): GitHub-style grid,
    weeks as columns, Sunday–Saturday as rows, with a legend and a
    stats summary. Heat levels use `· ░ ▒ ▓ █`.
  - Static HTML file (`--format html`): a self-contained page with
    the same week-column grid rendered as coloured squares
    (GitHub-style greens), plus the stats table. No JavaScript, no
    external assets, no server.
  - JSON (`--format json`): machine-readable per-day counts, per-repo
    and per-contributor totals, and streaks.
- Contributor identity: a commit counts for a contributor if its
  author name OR author email matches the filter. By default the
  filter is the current user's git identity (`git config user.name`
  / `user.email` from the environment running the tool); if that
  cannot be determined, all contributors are included and a warning
  is printed. `--all` includes every contributor; `--author TEXT`
  matches by substring against name or email (case-insensitive).
- Dates: author date (`%ad`, `--date=short`), i.e. the date the
  commit was authored, in the repository's local date. The window is
  the last N days inclusive of today (default 30, matching the
  challenge's "previous 30 days"). Commits dated in the future are
  ignored.
- Heat levels (commits on one day): 0 → blank, 1–2 → light,
  3–5 → medium-light, 6–9 → medium-dark, 10+ → darkest. These
  thresholds are this implementation's choice; the challenge does
  not specify thresholds.
- Week grid: weeks start on Sunday (GitHub convention). The grid is
  padded back to the Sunday on or before the window start, and
  forward to the Saturday on or after today, so every column is a
  full week. Days outside the window are rendered blank, not zero.
- Stats computed: total commits in window, commits per repository,
  commits per contributor, commits per day, busiest day, longest
  streak (consecutive days with ≥1 commit inside the window),
  current streak (consecutive days ending today, or yesterday if
  today has no commit yet — GitHub-style: a streak ending yesterday
  still counts, it is reported as "current streak" only when it
  reaches today or yesterday; see DESIGN.md).
- CLI: `python3 gitviz.py [ROOT] [--days N] [--author TEXT | --all]
  [--format text|html|json] [--output FILE] [--per-repo]`
  `ROOT` defaults to the current directory. `--per-repo` renders a
  separate graph per repository in addition to the combined graph
  (this covers the challenge's "per repository graph" extension).

## Divergences and scope limits (honest)

1. **CLI + static HTML, not a desktop GUI.** The challenge allows a
   CLI tool explicitly ("building it as a CLI tool, desktop tool or
   even as a local analyser..."). No Tkinter/desktop GUI and no web
   server are built. The HTML output is a static file, not a served
   app.
2. **System `git`, not a from-scratch repo parser.** The challenge
   offers a library as the beginner route and a hand-rolled parser
   only as the "more experienced" option. This build takes the
   library-equivalent route via the system `git` binary. It does
   NOT parse `.git` objects itself, and does NOT implement git.
   Consequence: the tool requires `git` on PATH; without it, it
   exits with a clear error instead of silently producing empty
   graphs.
3. **No GitHub API, no remote data.** Only local repositories are
   scanned. Contributions on GitHub (or any host) that are not in a
   local clone are not counted. This is never claimed otherwise.
4. **No caching.** The "cache the results" extension is NOT built:
   every run re-reads `git log`. This is deliberate (stateless,
   always correct) and is recorded here, not silently omitted.
5. **Author date, not committer date.** GitHub's graph uses
   committer/author dates with its own rules; this tool uses author
   date only, documented here.
6. **No bare-repo special-casing beyond `.git` detection.** A bare
   repository directory (no `.git` subdirectory, but itself a git
   dir) is detected only if it contains `HEAD` + `objects/` +
   `refs/`; otherwise it is skipped. Nested repositories inside a
   found repository are not descended into (the outer repo wins),
   and `.git` directories themselves are never descended into.
7. **Symlinks are not followed** while walking, to avoid loops.
8. **Merge commits count as one commit** each, like any commit; no
   special merge handling. Empty-window output is an empty graph
   with zero stats, not an error.
9. **Timezone handling is minimal:** dates are taken as the
   repository's local `YYYY-MM-DD` author date; no conversion
   between timezones is performed.

## What is NOT built

- No desktop GUI application, no web server, no remote rendering.
- No GitHub API access, no fetching/cloning of remote repositories.
- No hand-rolled `.git` object parser, no git implementation.
- No result caching / incremental recalculation.
- No per-contributor graphs (per-contributor *totals* are reported;
  the "stats for each contributor" extension is only partly covered).
- No streak gamification beyond the two streak numbers (no badges,
  points, or leaderboards).

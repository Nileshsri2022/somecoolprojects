#!/usr/bin/env python3
"""gitviz — Git Contributions Visualisation Tool.

Scans a directory tree for local git repositories, aggregates commit
history by day for a configurable window and contributor, and renders
a GitHub-style contributions graph as terminal text, static HTML, or
JSON. Python 3 standard library only; commit data is read via the
system `git` binary (this tool does not implement git and does not
talk to any remote API).

Usage:
    python3 gitviz.py [ROOT] [--days N] [--author TEXT | --all]
                      [--format text|html|json] [--output FILE]
                      [--per-repo]
"""

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta

# Heat level thresholds: (max commits for level, glyph, html colour).
LEVELS = [
    ("· ", "#ebedf0"),
    ("░ ", "#9be9a8"),
    ("▒ ", "#40c463"),
    ("▓ ", "#30a14e"),
    ("█ ", "#216e39"),
]
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ---------------------------------------------------------------- discovery

def _looks_like_bare_repo(path):
    """True if path itself is a bare repo dir (HEAD + objects + refs)."""
    return (
        os.path.isfile(os.path.join(path, "HEAD"))
        and os.path.isdir(os.path.join(path, "objects"))
        and os.path.isdir(os.path.join(path, "refs"))
    )


def find_repos(root):
    """Return sorted list of repo paths under root.

    A directory is a repo if it contains a `.git` dir or file
    (worktrees use a file), or if it looks like a bare repo.
    Found repos are not descended into; `.git` dirs are never
    descended into; symlinks are not followed.
    """
    repos = []
    for dirpath, dirnames, _filenames in os.walk(root, followlinks=False):
        # Never descend into .git internals.
        if ".git" in dirnames:
            dirnames.remove(".git")
        if os.path.exists(os.path.join(dirpath, ".git")) or _looks_like_bare_repo(dirpath):
            repos.append(dirpath)
            # Outer repo wins: do not descend into it.
            dirnames[:] = []
            continue
        # Prune symlinked subdirectories (os.walk lists them in dirnames).
        dirnames[:] = [
            d for d in dirnames
            if not os.path.islink(os.path.join(dirpath, d))
        ]
    return sorted(repos)


def current_user():
    """Return (name, email) from the invoking user's git config, or None."""
    def _cfg(key):
        try:
            out = subprocess.run(
                ["git", "config", key], capture_output=True, text=True,
                timeout=30,
            )
            value = out.stdout.strip()
            return value or None
        except (OSError, subprocess.SubprocessError):
            return None
    name, email = _cfg("user.name"), _cfg("user.email")
    if name is None and email is None:
        return None
    return (name or "", email or "")


# ------------------------------------------------------------------- reading

def repo_commits(repo):
    """Return list of (date, author_name, author_email) for a repo.

    Uses author date (%ad, short form). A repo with no commits, or a
    failing log, yields [] (warning on stderr for the failing case).
    Fields are unit-separator delimited so '|' in a name is safe.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "log", "--format=%ad%x1f%an%x1f%ae",
             "--date=short"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"warning: could not read {repo}: {exc}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        # Empty repo (no commits yet) is normal, not an error.
        if "does not have any commits yet" not in proc.stderr:
            print(f"warning: git log failed for {repo}: "
                  f"{proc.stderr.strip()}", file=sys.stderr)
        return []
    commits = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        date_str, name, email = parts
        try:
            year, month, day = (int(p) for p in date_str.split("-"))
            day_date = date(year, month, day)
        except ValueError:
            continue
        commits.append((day_date, name, email))
    return commits


# -------------------------------------------------------------- aggregation

def filter_commits(commits, start, end, author):
    """Keep commits in [start, end] matching author (None = all).

    Author match is a case-insensitive substring match against the
    author name or email.
    """
    if author is None:
        needles = []
    elif isinstance(author, (tuple, list)):
        needles = [a.lower() for a in author if a]
    else:
        needles = [author.lower()]
    out = []
    for day_date, name, email in commits:
        if not (start <= day_date <= end):
            continue
        if needles and not any(n in name.lower() or n in email.lower()
                               for n in needles):
            continue
        out.append((day_date, name, email))
    return out


def aggregate_by_day(commits):
    """Counter mapping date -> commit count."""
    counts = Counter()
    for day_date, _name, _email in commits:
        counts[day_date] += 1
    return counts


def heat_level(count):
    """0..4 heat level for a day's commit count."""
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


def _pad_to_week(start, end):
    """Expand [start, end] to the Sunday on/before start .. Saturday on/after end.

    Python weekday(): Monday=0..Sunday=6. Days since Sunday for a date
    is (weekday + 1) % 7.
    """
    grid_start = start - timedelta(days=(start.weekday() + 1) % 7)
    grid_end = end + timedelta(days=(6 - (end.weekday() + 1) % 7) % 7)
    return grid_start, grid_end


def build_week_grid(counts, start, end):
    """Return (weeks, grid_start, grid_end).

    weeks is a list of week columns; each column is 7 cells (Sun..Sat)
    holding a commit count, or None for days outside [start, end].
    """
    grid_start, grid_end = _pad_to_week(start, end)
    weeks = []
    day = grid_start
    while day <= grid_end:
        column = []
        for _ in range(7):
            column.append(counts.get(day, 0) if start <= day <= end else None)
            day += timedelta(days=1)
        weeks.append(column)
    return weeks, grid_start, grid_end


def month_labels(weeks, grid_start):
    """Month label for each week column ('' unless the week starts a new month)."""
    labels = []
    prev_month = None
    for i, _col in enumerate(weeks):
        week_start = grid_start + timedelta(days=7 * i)
        month = week_start.strftime("%b")
        # Label the column if its first in-window day starts a new month,
        # or if the week contains the 1st of a month.
        firsts = [week_start + timedelta(days=k) for k in range(7)]
        shown = next((d.strftime("%b") for d in firsts if d.day == 1), None)
        label = shown if shown is not None and shown != prev_month else ""
        if shown is not None:
            prev_month = shown
        labels.append(label)
    return labels


def longest_streak(counts, start, end):
    """Longest run of consecutive days with >=1 commit inside [start, end]."""
    best = run = 0
    day = start
    while day <= end:
        if counts.get(day, 0) > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
        day += timedelta(days=1)
    return best


def current_streak(counts, today):
    """Consecutive commit days ending today, or yesterday if today is empty.

    Returns 0 if neither today nor yesterday has a commit.
    """
    end = today if counts.get(today, 0) > 0 else today - timedelta(days=1)
    if counts.get(end, 0) <= 0:
        return 0
    streak = 0
    day = end
    while counts.get(day, 0) > 0:
        streak += 1
        day -= timedelta(days=1)
    return streak


def compute_stats(commits, counts, start, end, today):
    """Summary dict for a (possibly filtered) commit list."""
    per_repo = Counter()
    per_contributor = Counter()
    for _d, name, email in commits:
        per_contributor[f"{name} <{email}>" if name or email else "(unknown)"] += 1
    busiest = max(counts.items(), key=lambda kv: kv[1], default=None)
    return {
        "total": len(commits),
        "per_contributor": dict(sorted(per_contributor.items())),
        "per_day": {d.isoformat(): counts[d] for d in sorted(counts)},
        "busiest_day": busiest[0].isoformat() if busiest else None,
        "busiest_day_commits": busiest[1] if busiest else 0,
        "longest_streak": longest_streak(counts, start, end),
        "current_streak": current_streak(counts, today),
    }


# ---------------------------------------------------------------- rendering

def render_text(title, counts, start, end, stats):
    """GitHub-style text heatmap plus stats block."""
    weeks, grid_start, _grid_end = build_week_grid(counts, start, end)
    labels = month_labels(weeks, grid_start)
    lines = [title, ""]
    header = "     " + "".join(f"{label:<3}"[:3] for label in labels)
    lines.append(header)
    for row in range(7):
        cells = []
        for col in weeks:
            value = col[row]
            cells.append("   " if value is None else LEVELS[heat_level(value)][0])
        lines.append(f"{WEEKDAYS[row]:<4} " + "".join(cells))
    lines.append("")
    lines.append("Less " + " ".join(level[0].strip() for level in LEVELS) + " More")
    lines.append("")
    lines.append(f"Total commits: {stats['total']}")
    lines.append(f"Longest streak: {stats['longest_streak']} days")
    lines.append(f"Current streak: {stats['current_streak']} days")
    if stats["busiest_day"]:
        lines.append(f"Busiest day: {stats['busiest_day']} "
                     f"({stats['busiest_day_commits']} commits)")
    if stats["per_contributor"]:
        lines.append("By contributor:")
        for contributor, total in stats["per_contributor"].items():
            lines.append(f"  {total:>4}  {contributor}")
    return "\n".join(lines) + "\n"


def render_html(title, counts, start, end, stats, per_repo):
    """Self-contained static HTML heatmap (no JS, no external assets)."""
    weeks, grid_start, _grid_end = build_week_grid(counts, start, end)
    labels = month_labels(weeks, grid_start)
    squares = []
    for ci, col in enumerate(weeks):
        for row in range(7):
            day = grid_start + timedelta(days=7 * ci + row)
            value = col[row]
            if value is None:
                squares.append('<span class="day empty"></span>')
            else:
                colour = LEVELS[heat_level(value)][1]
                squares.append(
                    f'<span class="day" style="background:{colour}" '
                    f'title="{value} contribution{"s" if value != 1 else ""} '
                    f'on {day.isoformat()}"></span>'
                )
    month_row = "".join(
        f'<span class="month">{html.escape(label)}</span>' for label in labels
    )
    repo_rows = "".join(
        f"<tr><td>{html.escape(repo)}</td><td>{total}</td></tr>"
        for repo, total in sorted(per_repo.items())
    )
    contributor_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{total}</td></tr>"
        for name, total in sorted(stats["per_contributor"].items())
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: sans-serif; }}
.grid {{ display: grid; grid-template-rows: repeat(7, 12px); grid-auto-flow: column;
  grid-auto-columns: 12px; gap: 3px; }}
.day {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; }}
.day.empty {{ background: transparent; }}
.month {{ display: inline-block; width: 15px; font-size: 12px; }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>{start.isoformat()} to {end.isoformat()} &mdash; {stats['total']} commits,
longest streak {stats['longest_streak']} days,
current streak {stats['current_streak']} days.</p>
<div class="months">{month_row}</div>
<div class="grid">{''.join(squares)}</div>
<p>Less &#9633; &#9632; More (greener = more commits)</p>
<h2>By repository</h2>
<table><tr><th>Repository</th><th>Commits</th></tr>{repo_rows}</table>
<h2>By contributor</h2>
<table><tr><th>Contributor</th><th>Commits</th></tr>{contributor_rows}</table>
</body></html>
"""


def render_json(start, end, stats, per_repo):
    """Machine-readable summary."""
    payload = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "total": stats["total"],
        "per_repo": dict(sorted(per_repo.items())),
        "per_contributor": stats["per_contributor"],
        "per_day": stats["per_day"],
        "busiest_day": stats["busiest_day"],
        "busiest_day_commits": stats["busiest_day_commits"],
        "longest_streak": stats["longest_streak"],
        "current_streak": stats["current_streak"],
    }
    return json.dumps(payload, indent=2) + "\n"


# ---------------------------------------------------------------------- CLI

def build_parser():
    parser = argparse.ArgumentParser(
        description="Visualise git contribution history as a GitHub-style graph.")
    parser.add_argument("root", nargs="?", default=".",
                        help="root folder to search for git repositories (default: .)")
    parser.add_argument("--days", type=int, default=30,
                        help="number of days to look back, including today (default: 30)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--author", metavar="TEXT",
                       help="only count commits whose author name/email contains TEXT")
    group.add_argument("--all", action="store_true",
                       help="count all contributors (default: current git user only)")
    parser.add_argument("--format", choices=["text", "html", "json"], default="text",
                        help="output format (default: text)")
    parser.add_argument("--output", metavar="FILE",
                        help="write output to FILE instead of stdout")
    parser.add_argument("--per-repo", action="store_true",
                        help="also render a separate graph per repository (text/html)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.days < 1:
        print("error: --days must be at least 1", file=sys.stderr)
        return 2
    if shutil.which("git") is None:
        print("error: 'git' not found on PATH; gitviz reads local repos via git",
              file=sys.stderr)
        return 2
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"error: root directory not found: {args.root}", file=sys.stderr)
        return 2

    today = date.today()
    end = today
    start = today - timedelta(days=args.days - 1)

    if args.all:
        author_filter = None
    elif args.author:
        author_filter = args.author
    else:
        user = current_user()
        if user is None:
            print("warning: no git user.name/user.email configured; "
                  "counting all contributors", file=sys.stderr)
            author_filter = None
        else:
            # Match if either the configured name or email matches.
            author_filter = tuple(part for part in user if part)

    repos = find_repos(root)
    all_commits = []
    per_repo = {}
    per_repo_commits = {}
    for repo in repos:
        commits = filter_commits(repo_commits(repo), start, end, author_filter)
        per_repo[repo] = len(commits)
        per_repo_commits[repo] = commits
        all_commits.extend(commits)

    counts = aggregate_by_day(all_commits)
    stats = compute_stats(all_commits, counts, start, end, today)
    title = f"Contributions: {start.isoformat()} to {end.isoformat()} ({len(repos)} repos)"

    if args.format == "json":
        output = render_json(start, end, stats, per_repo)
    elif args.format == "html":
        output = render_html(title, counts, start, end, stats, per_repo)
        if args.per_repo:
            for repo in repos:
                repo_counts = aggregate_by_day(per_repo_commits[repo])
                repo_stats = compute_stats(
                    per_repo_commits[repo], repo_counts, start, end, today)
                output += "\n<!-- per-repo -->\n" + render_html(
                    repo, repo_counts, start, end, repo_stats, {repo: len(per_repo_commits[repo])})
    else:
        output = render_text(title, counts, start, end, stats)
        if repos:
            output += "\nBy repository:\n"
            for repo in sorted(per_repo):
                output += f"  {per_repo[repo]:>4}  {repo}\n"
        if args.per_repo:
            for repo in repos:
                repo_counts = aggregate_by_day(per_repo_commits[repo])
                repo_stats = compute_stats(
                    per_repo_commits[repo], repo_counts, start, end, today)
                output += "\n" + render_text(repo, repo_counts, start, end, repo_stats)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

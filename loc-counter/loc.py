#!/usr/bin/env python3
"""loc.py — count blank, comment, and code lines in a directory tree.

Build Your Own LOC Counter (codingchallenges.fyi, challenge
`challenge-loc-counter`). Python 3 standard library only.

Usage:
    python3 loc.py <directory>            per-language summary (default)
    python3 loc.py --files <directory>    per-file breakdown
    python3 loc.py --json <directory>     JSON output
A single file path is also accepted in place of a directory.
See docs/SPEC.md for the full spec and docs/DESIGN.md for the
classification rules.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    """One row of the language table (challenge Step 6)."""

    name: str
    line_comment: str | None = None
    block_start: str | None = None
    block_end: str | None = None
    kind: str = "code"  # "code", "markdown", or "text"


# Extension (lowercased, with dot) -> Language. Adding a language
# is adding rows here; no other code changes.
_C = lambda name: Language(name, "//", "/*", "*/")  # noqa: E731
_HASH = lambda name: Language(name, "#")  # noqa: E731
LANGUAGES = {
    ".py": _HASH("Python"),
    ".pyi": _HASH("Python"),
    ".c": _C("C"),
    ".h": _C("C Header"),
    ".cpp": _C("C++"),
    ".cc": _C("C++"),
    ".cxx": _C("C++"),
    ".hpp": _C("C++"),
    ".java": _C("Java"),
    ".js": _C("JavaScript"),
    ".ts": _C("TypeScript"),
    ".go": _C("Go"),
    ".rs": _C("Rust"),
    ".sh": _HASH("Shell"),
    ".bash": _HASH("Shell"),
    ".rb": _HASH("Ruby"),
    ".md": Language("Markdown", kind="markdown"),
    ".txt": Language("Text", kind="text"),
}


@dataclass
class FileCounts:
    path: str  # as displayed: relative to the scanned root
    language: str
    lines: int = 0
    blanks: int = 0
    comments: int = 0
    code: int = 0

    def as_dict(self):
        return {
            "path": self.path,
            "language": self.language,
            "lines": self.lines,
            "blanks": self.blanks,
            "comments": self.comments,
            "code": self.code,
        }


def _scan_line(line, lang, in_block):
    """Scan one code-language line.

    Returns (has_code, has_comment, in_block_after). A single-line
    string literal is skipped over so comment markers inside it do
    not start a comment; the literal itself counts as code.
    """
    has_code = False
    has_comment = False
    i = 0
    n = len(line)
    while i < n:
        if in_block:
            end = line.find(lang.block_end, i)
            if end == -1:
                has_comment = True
                i = n
            else:
                has_comment = True
                i = end + len(lang.block_end)
                in_block = False
            continue
        if lang.line_comment and line.startswith(lang.line_comment, i):
            has_comment = True
            break
        if lang.block_start and line.startswith(lang.block_start, i):
            has_comment = True
            i += len(lang.block_start)
            in_block = True
            continue
        ch = line[i]
        if ch in ("'", '"'):
            # Single-line string literal: skip to its closing quote.
            has_code = True
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == ch:
                    break
                j += 1
            i = j + 1 if j < n else n
            continue
        if not ch.isspace():
            has_code = True
        i += 1
    return has_code, has_comment, in_block


def _count_code_lines(lines, lang):
    """Return (blanks, comments, code) for a code-language file."""
    blanks = comments = code = 0
    in_block = False
    for line in lines:
        if line.strip() == "":
            blanks += 1
            continue
        has_code, has_comment, in_block = _scan_line(line, lang, in_block)
        if has_code:
            code += 1
        elif has_comment:
            comments += 1
        else:  # Unreachable for non-blank lines; kept for safety.
            code += 1
    return blanks, comments, code


def _count_markdown_lines(lines):
    """Fence delimiters and fenced lines count as code; prose too."""
    blanks = code = 0
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped == "":
            blanks += 1
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        code += 1
    return blanks, 0, code


def _count_text_lines(lines):
    blanks = sum(1 for line in lines if line.strip() == "")
    return blanks, 0, len(lines) - blanks


def count_file(path, display_path=None):
    """Count one file; return None if it is not a countable file."""
    _, ext = os.path.splitext(path)
    lang = LANGUAGES.get(ext.lower())
    if lang is None:
        return None
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data:
        return None  # binary file
    lines = data.decode("utf-8", errors="replace").splitlines()
    if lang.kind == "markdown":
        blanks, comments, code = _count_markdown_lines(lines)
    elif lang.kind == "text":
        blanks, comments, code = _count_text_lines(lines)
    else:
        blanks, comments, code = _count_code_lines(lines, lang)
    return FileCounts(
        path=display_path if display_path is not None else path,
        language=lang.name,
        lines=len(lines),
        blanks=blanks,
        comments=comments,
        code=code,
    )


def count_directory(root):
    """Walk root recursively; return sorted FileCounts, by path."""
    results = []
    if os.path.isfile(root):
        counted = count_file(root, os.path.basename(root))
        return [counted] if counted is not None else []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            full = os.path.join(dirpath, filename)
            counted = count_file(full, os.path.relpath(full, root))
            if counted is not None:
                results.append(counted)
    results.sort(key=lambda fc: fc.path)
    return results


def summarize(files):
    """Return (per-language dict, total dict) for a FileCounts list."""
    languages = {}
    total = {"files": 0, "lines": 0, "blanks": 0, "comments": 0, "code": 0}
    for fc in files:
        entry = languages.setdefault(
            fc.language,
            {"files": 0, "lines": 0, "blanks": 0, "comments": 0, "code": 0},
        )
        for key, value in (
            ("lines", fc.lines),
            ("blanks", fc.blanks),
            ("comments", fc.comments),
            ("code", fc.code),
        ):
            entry[key] += value
            total[key] += value
        entry["files"] += 1
        total["files"] += 1
    return languages, total


def _table(rows, headers):
    widths = [
        max(len(str(row[i])) for row in [headers] + rows) for i in range(len(headers))
    ]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    out = [fmt.format(*headers)]
    for row in rows:
        out.append(fmt.format(*[str(v) for v in row]))
    return "\n".join(out)


def format_summary(files):
    languages, total = summarize(files)
    rows = [
        [name, agg["files"], agg["lines"], agg["blanks"], agg["comments"], agg["code"]]
        for name, agg in sorted(languages.items())
    ]
    rows.append(
        ["Total", total["files"], total["lines"], total["blanks"],
         total["comments"], total["code"]]
    )
    return _table(rows, ["Language", "Files", "Lines", "Blanks", "Comments", "Code"])


def format_files(files):
    rows = [
        [fc.path, fc.lines, fc.blanks, fc.comments, fc.code] for fc in files
    ]
    _, total = summarize(files)
    rows.append(
        ["Total", total["lines"], total["blanks"], total["comments"], total["code"]]
    )
    return _table(rows, ["File", "Lines", "Blanks", "Comments", "Code"])


def to_json_dict(files):
    languages, total = summarize(files)
    return {
        "files": [fc.as_dict() for fc in files],
        "languages": languages,
        "total": total,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Count blank, comment, and code lines in a directory tree."
    )
    parser.add_argument("path", help="starting directory (or a single file)")
    parser.add_argument("--files", action="store_true",
                        help="per-file breakdown instead of per-language summary")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)
    if not os.path.exists(args.path):
        print(f"loc.py: no such file or directory: {args.path}", file=sys.stderr)
        return 2
    files = count_directory(args.path)
    if args.json:
        print(json.dumps(to_json_dict(files), indent=2, sort_keys=True))
    elif args.files:
        print(format_files(files))
    else:
        print(format_summary(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())

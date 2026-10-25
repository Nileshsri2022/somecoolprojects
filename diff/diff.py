#!/usr/bin/env python3
"""diff — Build Your Own diff Tool (Coding Challenges #13).

Compares two files line by line using a longest common subsequence
computed from scratch (see docs/DESIGN.md: DP LCS, not difflib,
not Myers) and prints only the changed lines:

    < line   line present only in the first file
    > line   line present only in the second file

Identical files print nothing. Exit status is 0 whether the files
are identical or different, 2 for the wrong number of arguments,
1 for an unreadable file. Python 3 standard library only.
"""

import sys


def _lcs_list(a, b):
    """Return one longest common subsequence of sequences a and b.

    Classic DP: dp[i][j] is the LCS length of a[:i] and b[:j].
    Backtracking prefers dropping an element of a on ties, so the
    result is deterministic. Time and space are O(len(a)*len(b)).
    """
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        ai = a[i]
        row, prev = dp[i + 1], dp[i]
        for j in range(n):
            if ai == b[j]:
                row[j + 1] = prev[j] + 1
            elif prev[j + 1] >= row[j]:
                row[j + 1] = prev[j + 1]
            else:
                row[j + 1] = row[j]
    out = []
    i, j = m, n
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            out.append(a[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    out.reverse()
    return out


def lcs(a, b):
    """Longest common subsequence of a and b.

    Works for two strings (returns a string) and for two lists of
    lines (returns a list of lines) — the challenge's Step 1 and
    Step 2 are the same function over different element types.
    """
    result = _lcs_list(a, b)
    if isinstance(a, str) and isinstance(b, str):
        return "".join(result)
    return result


def diff_lines(old, new):
    """Changed lines between line lists old and new, as < / > lines.

    Common prefix and suffix lines are in every LCS, so they are
    stripped first and DP runs only on the middle (Step 5 scale
    note in docs/DESIGN.md). Between consecutive LCS elements,
    skipped old lines are emitted as "< line" before skipped new
    lines as "> line"; LCS lines themselves are not emitted.
    """
    prefix = 0
    while (prefix < len(old) and prefix < len(new)
           and old[prefix] == new[prefix]):
        prefix += 1
    suffix = 0
    while (suffix < len(old) - prefix and suffix < len(new) - prefix
           and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]):
        suffix += 1
    mid_old = old[prefix:len(old) - suffix] if suffix else old[prefix:]
    mid_new = new[prefix:len(new) - suffix] if suffix else new[prefix:]
    common = _lcs_list(mid_old, mid_new)

    out = []
    i = j = 0
    for line in common:
        while mid_old[i] != line:
            out.append("< " + mid_old[i])
            i += 1
        while mid_new[j] != line:
            out.append("> " + mid_new[j])
            j += 1
        i += 1
        j += 1
    while i < len(mid_old):
        out.append("< " + mid_old[i])
        i += 1
    while j < len(mid_new):
        out.append("> " + mid_new[j])
        j += 1
    return out


def split_lines(text):
    """Split file text into lines: on \\n, one trailing \\r stripped.

    A missing final newline is not a difference, and an empty
    file is zero lines, not one empty line.
    """
    if text == "":
        return []
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def read_lines(path):
    """Read a UTF-8 file and return its lines (may raise OSError)."""
    with open(path, "r", encoding="utf-8") as f:
        return split_lines(f.read())


def main(argv):
    """CLI: diff.py ORIGINAL NEW. Returns the process exit code."""
    if len(argv) != 3:
        print("usage: diff.py ORIGINAL NEW", file=sys.stderr)
        return 2
    try:
        old = read_lines(argv[1])
        new = read_lines(argv[2])
    except OSError as exc:
        print(f"diff.py: {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 1
    for line in diff_lines(old, new):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

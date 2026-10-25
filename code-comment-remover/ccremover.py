#!/usr/bin/env python3
"""ccremover — remove comments from source files (CLI filter).

Supported languages: Python (#), JavaScript and C/C++ (// and /* */),
Go (// and /* */, with Go doc comments and //go: directives preserved).

Reads stdin or files, writes stripped source to stdout. Never modifies
an input file in place. See docs/SPEC.md for the full behaviour contract,
including the documented limits (nested block comments, JS regex
literals, template-literal ${} expressions, C++ raw strings).

Usage: ccremover.py [--lang python|js|c|go|auto] [FILE ...]
"""

import argparse
import sys

__version__ = "1.0.0"

# ---------------------------------------------------------------- errors

class UnterminatedComment(Exception):
    """A /* block comment with no closing */. ``line`` is 1-based."""

    def __init__(self, line):
        super().__init__("unterminated block comment starting on line %d" % line)
        self.line = line


class UsageError(Exception):
    """CLI / input error: reported on stderr, exit code 2."""


# ------------------------------------------------------- tool comments

PYTHON_TOOL_PREFIXES = (
    "noqa", "type:", "pylint:", "flake8:", "fmt:", "isort:",
    "mypy:", "coverage:", "pyright:", "ruff:",
)

C_TOOL_PREFIXES = ("go:", "+build")


def is_python_tool_comment(body):
    """body = comment text after '#', unstripped. True if a tool comment."""
    text = body.lstrip()
    return any(text.startswith(p) for p in PYTHON_TOOL_PREFIXES)


def is_c_tool_comment(marker, body):
    """marker is '//' or '/*'; body is text after the marker.

    A //go: directive counts only when 'go:' immediately follows '//'
    (no space), matching Go's own directive rule. ' +build' lines have
    a space after //, so the body is stripped before testing.
    """
    if marker == "//":
        if body.startswith("go:"):
            return True
        return body.lstrip().startswith("+build")
    # Block comments: strip and test (covers /* +build ... */ if used).
    text = body.lstrip()
    return any(text.startswith(p) for p in C_TOOL_PREFIXES)


# ---------------------------------------------------------------- python

_PREFIX_LETTERS = set("rRbBfFuU")
_QUOTES = ("'", '"')


def _scan_python_string(line, i, quote, raw):
    """Scan a single-line (non-triple) string starting at line[i]==quote.

    Returns (text, next_i). Unterminated at end of line: returns the
    rest of the line (tolerant behaviour, see SPEC.md).
    """
    out = [quote]
    i += 1
    while i < len(line):
        ch = line[i]
        if not raw and ch == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2])
            i += 2
            continue
        out.append(ch)
        i += 1
        if ch == quote:
            break
    return "".join(out), i


def strip_python(text, keep_tool_comments=True):
    """Remove # comments from Python source ``text``. Returns new text."""
    lines = _split_lines(text)
    out_lines = []
    triple = None  # None or (quote_char, raw_bool)
    for line in lines:
        if line.strip() == "" and triple is None:
            # Originally blank line: preserved (it is not a comment).
            out_lines.append("")
            continue
        out = []
        i = 0
        tool_line = False
        while i < len(line):
            if triple is not None:
                quote, raw = triple
                if not raw and line[i] == "\\" and i + 1 < len(line):
                    out.append(line[i:i + 2])
                    i += 2
                    continue
                if line.startswith(quote * 3, i):
                    out.append(quote * 3)
                    i += 3
                    triple = None
                    continue
                out.append(line[i])
                i += 1
                continue
            ch = line[i]
            if ch == "#":
                body = line[i + 1:]
                if keep_tool_comments and is_python_tool_comment(body):
                    tool_line = True
                break  # rest of line is a comment, kept or dropped
            # String prefix + quote, e.g. r"..." / f'''...''' / br'...'.
            # Guard: a prefix must not be the tail of an identifier.
            if ch in _PREFIX_LETTERS and (
                    i == 0 or not (line[i - 1].isalnum() or line[i - 1] == "_")):
                j = i
                while j < len(line) and line[j] in _PREFIX_LETTERS:
                    j += 1
                if j < len(line) and line[j] in _QUOTES:
                    prefix = line[i:j]
                    quote = line[j]
                    raw = "r" in prefix.lower()
                    if line.startswith(quote * 3, j):
                        out.append(prefix + quote * 3)
                        triple = (quote, raw)
                        i = j + 3
                        continue
                    text, i = _scan_python_string(line, j, quote, raw)
                    out.append(prefix + text)
                    continue
            if ch in _QUOTES:
                if line.startswith(ch * 3, i):
                    out.append(ch * 3)
                    triple = (ch, False)
                    i += 3
                    continue
                text, i = _scan_python_string(line, i, ch, False)
                out.append(text)
                continue
            out.append(ch)
            i += 1
        if tool_line:
            out_lines.append(line.rstrip())
        else:
            joined = "".join(out)
            if joined.strip() == "":
                # Comment-only line (or empty line inside a triple
                # string, handled by the blank branch only when not in
                # a string; an empty string-content line is '' and is
                # preserved by emitting '' — same result either way,
                # except a string-content line of only whitespace is
                # preserved below via the triple check).
                if triple is not None or line.strip() == "":
                    out_lines.append(joined)
                # else: dropped comment-only line, no output line
            else:
                out_lines.append(joined.rstrip())
    return _join_lines(out_lines)


# -------------------------------------------------------------- c-style

# quote -> (multiline, escapes)
C_QUOTES = {
    "js": {"'": (False, True), '"': (False, True), "`": (True, True)},
    "c": {"'": (False, True), '"': (False, True)},
    "go": {'"': (False, True), "`": (True, False), "'": (False, True)},
}

DECLARATION_WORDS = ("package", "func", "type", "var", "const")


def _split_lines(text):
    """Split text into lines, normalising CRLF/CR to LF.

    A trailing newline does not produce a phantom final line.
    """
    if text == "":
        return []
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalised.split("\n")
    if normalised.endswith("\n"):
        lines.pop()
    return lines


def _join_lines(out_lines):
    if not out_lines:
        return ""
    return "\n".join(out_lines) + "\n"


def _first_word(code_text):
    """First identifier-like word of code text, or ''."""
    stripped = code_text.lstrip()
    word = []
    for ch in stripped:
        if ch.isalnum() or ch == "_":
            word.append(ch)
        else:
            break
    return "".join(word)


def _scan_cstyle_lines(text, lang):
    """Tokenise into per-line segment lists.

    Each line -> list of segments (kind, text, group_id) where kind is
    'code' or 'comment'. Block comments spanning lines share one
    group_id; each // comment starts a new group_id (consecutive //
    comment-only lines are merged into one group later).
    Raises UnterminatedComment for an unclosed block comment.
    """
    quotes = C_QUOTES[lang]
    lines = _split_lines(text)
    result = []
    in_block = False
    block_group = None
    block_start_line = 0  # 0-based
    in_string = None  # None or (quote, multiline, escapes)
    group_counter = 0
    for line_no, line in enumerate(lines):
        segments = []  # [kind, text, group_id]
        cur = []  # characters of current segment
        # A line that starts inside a block comment or a multi-line
        # string continues that segment kind from the previous line.
        if in_block:
            cur_kind = "comment"
            cur_group = block_group
        elif in_string is not None:
            cur_kind = "code"
            cur_group = None
        else:
            cur_kind = None
            cur_group = None

        def emit(kind, group):
            nonlocal cur, cur_kind, cur_group
            if cur:
                segments.append((cur_kind, "".join(cur), cur_group))
                cur = []
            cur_kind = kind
            cur_group = group

        def put(ch):
            cur.append(ch)

        i = 0
        while i < len(line):
            if in_block:
                if line.startswith("*/", i):
                    put("*")
                    put("/")
                    i += 2
                    in_block = False
                    # Switch back to code for what follows.
                    emit("code", None)
                    continue
                put(line[i])
                i += 1
                continue
            if in_string is not None:
                quote, multiline, escapes = in_string
                ch = line[i]
                if escapes and ch == "\\" and i + 1 < len(line):
                    put(line[i])
                    put(line[i + 1])
                    i += 2
                    continue
                put(ch)
                i += 1
                if ch == quote:
                    in_string = None
                continue
            # Normal code state.
            if line.startswith("//", i):
                emit("comment", group_counter)
                group_counter += 1
                put("/")
                put("/")
                i += 2
                # Rest of line is comment text.
                while i < len(line):
                    put(line[i])
                    i += 1
                break
            if line.startswith("/*", i):
                emit("comment", group_counter)
                block_group = group_counter
                group_counter += 1
                block_start_line = line_no
                in_block = True
                put("/")
                put("*")
                i += 2
                continue
            ch = line[i]
            if ch in quotes:
                multiline, escapes = quotes[ch]
                if cur_kind != "code":
                    emit("code", None)
                put(ch)
                i += 1
                if multiline:
                    in_string = (ch, True, escapes)
                else:
                    # Single-line string: scan to closing quote / EOL.
                    while i < len(line):
                        c2 = line[i]
                        if escapes and c2 == "\\" and i + 1 < len(line):
                            put(line[i])
                            put(line[i + 1])
                            i += 2
                            continue
                        put(c2)
                        i += 1
                        if c2 == ch:
                            break
                continue
            if cur_kind != "code":
                emit("code", None)
            put(ch)
            i += 1
        if cur:
            segments.append((cur_kind, "".join(cur), cur_group))
        # A line ending inside a block comment: its comment segment
        # keeps the block's group id (set when the block started).
        if in_block and segments and segments[-1][0] == "comment":
            pass  # group already correct
        result.append(segments)
        # A single-line string left unterminated ends at end of line.
        if in_string is not None and not in_string[1]:
            in_string = None
    if in_block:
        raise UnterminatedComment(block_start_line + 1)
    return lines, result


def strip_cstyle(text, lang, go_doc=True, keep_tool_comments=True):
    """Remove // and /* */ comments for a C-style language."""
    lines, token_lines = _scan_cstyle_lines(text, lang)
    # --- build groups -------------------------------------------------
    # group key -> {lines, segments: [(line_idx, seg_idx)]}
    groups = {}
    order = []
    # First pass: block groups (by group id) and line-comment groups.
    for line_idx, segments in enumerate(token_lines):
        for seg_idx, (kind, seg_text, group_id) in enumerate(segments):
            if kind != "comment":
                continue
            # A group is a block group if any of its segments starts
            # with /* (continuation lines do not, but share the id).
            key = group_id
            if key not in groups:
                groups[key] = {"lines": [], "segments": []}
                order.append(key)
            if line_idx not in groups[key]["lines"]:
                groups[key]["lines"].append(line_idx)
            groups[key]["segments"].append((line_idx, seg_idx))
    # Decide block-ness per group.
    for key in order:
        segs = groups[key]["segments"]
        texts = [token_lines[li][si][1] for li, si in segs]
        groups[key]["is_block"] = any(t.startswith("/*") for t in texts)
        groups[key]["text"] = "".join(texts)
    # Merge consecutive comment-only // lines into one group.
    # A // group is mergeable if its single line is comment-only and
    # it is not a block group. Merging is done by re-keying: walk lines
    # in order, and for a comment-only line whose only comment group is
    # a single-line // group, attach it to the previous line's // group
    # when the previous line is the immediately preceding line.
    merged = {}  # new key -> group dict
    merged_order = []
    line_to_merged = {}
    for line_idx, segments in enumerate(token_lines):
        has_code = any(
            kind == "code" and seg.strip() != ""
            for kind, seg, _ in segments)
        comment_groups = []
        for kind, _t, gid in segments:
            if kind == "comment" and gid not in comment_groups:
                comment_groups.append(gid)
        if (not has_code and len(comment_groups) == 1
                and not groups[comment_groups[0]]["is_block"]
                and line_idx > 0 and (line_idx - 1) in line_to_merged):
            prev_key = line_to_merged[line_idx - 1]
            merged[prev_key]["lines"].append(line_idx)
            merged[prev_key]["segments"].extend(groups[comment_groups[0]]["segments"])
            line_to_merged[line_idx] = prev_key
        else:
            for gid in comment_groups:
                if gid in merged and groups[gid]["is_block"]:
                    # Block group already placed (spans lines); skip dup.
                    continue
                if gid not in merged:
                    merged[gid] = {
                        "lines": list(groups[gid]["lines"]),
                        "segments": list(groups[gid]["segments"]),
                        "is_block": groups[gid]["is_block"],
                        "text": groups[gid]["text"],
                    }
                    merged_order.append(gid)
                # comment-only // line mapping for the next iteration:
                if not has_code and len(comment_groups) == 1:
                    line_to_merged[line_idx] = gid
    groups = merged
    order = merged_order

    # --- decide keep/drop per segment --------------------------------
    keep_segments = set()  # (line_idx, seg_idx)
    for key in order:
        group = groups[key]
        group_lines = group["lines"]
        is_comment_only = all(
            not any(kind == "code" and seg.strip() != ""
                    for kind, seg, _ in token_lines[li])
            for li in group_lines)
        # Tool comments: per segment for //, whole group for blocks.
        if group["is_block"]:
            body = group["text"][2:] if group["text"].startswith("/*") else group["text"]
            if keep_tool_comments and is_c_tool_comment("/*", body):
                for seg in group["segments"]:
                    keep_segments.add(seg)
                continue
        else:
            for li, si in group["segments"]:
                seg_text = token_lines[li][si][1]
                body = seg_text[2:]  # after //
                if keep_tool_comments and is_c_tool_comment("//", body):
                    keep_segments.add((li, si))
        # Go doc comments: comment-only groups directly above a
        # declaration line (no blank line between).
        if lang == "go" and go_doc and is_comment_only:
            next_idx = max(group_lines) + 1
            if next_idx < len(lines):
                code_text = "".join(
                    seg for kind, seg, _ in token_lines[next_idx]
                    if kind == "code")
                if _first_word(code_text) in DECLARATION_WORDS:
                    for seg in group["segments"]:
                        keep_segments.add(seg)
    # --- reassemble ----------------------------------------------------
    out_lines = []
    for line_idx, segments in enumerate(token_lines):
        if lines[line_idx].strip() == "":
            out_lines.append("")
            continue
        parts = []
        for seg_idx, (kind, seg_text, _gid) in enumerate(segments):
            if kind == "code" or (line_idx, seg_idx) in keep_segments:
                parts.append(seg_text)
        joined = "".join(parts)
        if joined.strip() == "":
            continue  # dropped comment-only line
        out_lines.append(joined.rstrip())
    return _join_lines(out_lines)

 


# ------------------------------------------------------------------ api

EXTENSION_LANGS = {
    ".py": "python",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
    ".c": "c", ".h": "c", ".cpp": "c", ".cc": "c",
    ".cxx": "c", ".hpp": "c", ".hh": "c",
    ".go": "go",
}


def strip_source(text, lang, go_doc=True, keep_tool_comments=True):
    """Strip comments from ``text`` in language ``lang``.

    lang is 'python', 'js', 'c', or 'go' (not 'auto').
    """
    if lang == "python":
        return strip_python(text, keep_tool_comments=keep_tool_comments)
    if lang in ("js", "c", "go"):
        return strip_cstyle(
            text, lang, go_doc=go_doc,
            keep_tool_comments=keep_tool_comments)
    raise UsageError("unknown language: %r" % (lang,))


def infer_lang(path):
    """Language for a file path from its extension, or None."""
    import os
    return EXTENSION_LANGS.get(os.path.splitext(path)[1].lower())


# ------------------------------------------------------------------ cli

def build_parser():
    parser = argparse.ArgumentParser(
        prog="ccremover",
        description="Remove comments from source files. "
                    "Reads stdin or files, writes stripped source to stdout.")
    parser.add_argument("files", nargs="*", help="input files (default: stdin)")
    parser.add_argument("--lang", default="auto",
                        choices=["auto", "python", "js", "c", "go"],
                        help="source language (default: auto from file "
                             "extension; required when reading stdin)")
    parser.add_argument("--go-doc", dest="go_doc", action="store_true",
                        default=True,
                        help="preserve Go doc comments (default: on)")
    parser.add_argument("--no-go-doc", dest="go_doc", action="store_false",
                        help="do not preserve Go doc comments")
    parser.add_argument("--keep-tool-comments", dest="keep_tool_comments",
                        action="store_true", default=True,
                        help="preserve tool/linter comments such as "
                             "# noqa and //go:generate (default: on)")
    parser.add_argument("--no-keep-tool-comments", dest="keep_tool_comments",
                        action="store_false",
                        help="do not preserve tool/linter comments")
    parser.add_argument("--version", action="version",
                        version="ccremover " + __version__)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not args.files:
            if args.lang == "auto":
                parser.error("reading from stdin requires --lang")
            text = sys.stdin.read()
            sys.stdout.write(strip_source(
                text, args.lang, go_doc=args.go_doc,
                keep_tool_comments=args.keep_tool_comments))
            return 0
        for path in args.files:
            lang = args.lang
            if lang == "auto":
                lang = infer_lang(path)
                if lang is None:
                    raise UsageError(
                        "cannot infer language for %r: "
                        "use --lang" % (path,))
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except OSError as exc:
                raise UsageError("cannot read %r: %s" % (path, exc.strerror or exc))
            except UnicodeDecodeError as exc:
                raise UsageError("cannot decode %r as UTF-8: %s" % (path, exc))
            sys.stdout.write(strip_source(
                text, lang, go_doc=args.go_doc,
                keep_tool_comments=args.keep_tool_comments))
        return 0
    except UsageError as exc:
        print("ccremover: error: %s" % exc, file=sys.stderr)
        return 2
    except UnterminatedComment as exc:
        print("ccremover: error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

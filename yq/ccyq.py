#!/usr/bin/env python3
"""ccyq - a small yq clone (jq for YAML), Coding Challenges challenge-yq.

Python 3 standard library only. The YAML parser is hand-written (there
is no YAML parser in the stdlib); PyYAML is not imported or vendored.
Supported subset and deliberate limits are documented in docs/SPEC.md.

Usage:
    python3 ccyq.py [FILTER] [FILE]
    python3 ccyq.py FILE          # print the whole document
    python3 ccyq.py FILTER        # YAML from stdin
    python3 ccyq.py               # stdin, identity filter
"""

import re
import sys

VERSION = "1.0.0"


class YQError(Exception):
    pass


# ---------------------------------------------------------------- scalars

_BOOL = {"true": True, "false": False,
         "True": True, "False": False,
         "TRUE": True, "FALSE": False}
_NULL = {"null", "Null", "NULL", "~", ""}

_INT_RE = re.compile(r"^[+-]?[0-9][0-9_]*$")
_HEX_RE = re.compile(r"^[+-]?0x[0-9a-fA-F_]+$")
_OCT_RE = re.compile(r"^[+-]?0o[0-7_]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(\.[0-9]+|[0-9][0-9_]*(\.[0-9_]*)?)([eE][+-]?[0-9]+)?$")


def parse_quoted(text, pos=0):
    """Parse a quoted scalar starting at text[pos]; return (value, end)."""
    quote = text[pos]
    out = []
    i = pos + 1
    while i < len(text):
        ch = text[i]
        if quote == "'":
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                return "".join(out), i + 1
            out.append(ch)
            i += 1
        else:
            if ch == "\\" and i + 1 < len(text):
                esc = text[i + 1]
                mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\",
                           "0": "\0"}
                if esc in mapping:
                    out.append(mapping[esc])
                else:
                    # Unknown escapes stay literal (backslash kept).
                    out.append("\\" + esc)
                i += 2
                continue
            if ch == '"':
                return "".join(out), i + 1
            out.append(ch)
            i += 1
    raise YQError("unterminated quoted string: %r" % text)


def parse_scalar_token(token):
    """Type one scalar token. Quoted tokens are always strings."""
    token = token.strip()
    if not token:
        return None
    if token[0] in "\"'":
        value, end = parse_quoted(token, 0)
        if token[end:].strip():
            raise YQError("trailing characters after quoted scalar: %r"
                          % token)
        return value
    if token in _NULL:
        return None
    if token in _BOOL:
        return _BOOL[token]
    if _HEX_RE.match(token):
        try:
            return int(token.replace("_", ""), 16)
        except ValueError:
            pass
    if _OCT_RE.match(token):
        try:
            return int(token.replace("_", ""), 8)
        except ValueError:
            pass
    if _INT_RE.match(token):
        try:
            return int(token.replace("_", ""))
        except ValueError:
            pass
    low = token.lower()
    if low in (".inf", "+.inf"):
        return float("inf")
    if low == "-.inf":
        return float("-inf")
    if low == ".nan":
        return float("nan")
    if _FLOAT_RE.match(token):
        try:
            return float(token.replace("_", ""))
        except ValueError:
            pass
    return token


def looks_typed(text):
    """True if a plain string would re-parse as a non-string scalar."""
    if text.strip() != text:
        return True
    return not isinstance(parse_scalar_token(text), str)


# ---------------------------------------------------------------- comments

def strip_comment(line):
    """Remove a trailing comment (a # preceded by whitespace, outside
    quotes). Apostrophes inside plain text do not open a quote: a quote
    only opens at the start of a scalar (after ':', '-', '[', '{', ','
    or start of line)."""
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_single:
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
        if ch in "\"'":
            prev = line[:i].rstrip()
            if not prev or prev[-1] in ":-[{,":
                if ch == "'":
                    in_single = True
                else:
                    in_double = True
        i += 1
    return line.rstrip()


# ---------------------------------------------------------------- flow values

class FlowParser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1

    def parse_value(self):
        self.skip_ws()
        if self.pos >= len(self.text):
            raise YQError("unexpected end of flow value")
        ch = self.text[self.pos]
        if ch == "[":
            self.pos += 1
            out = []
            self.skip_ws()
            if self.pos < len(self.text) and self.text[self.pos] == "]":
                self.pos += 1
                return out
            while True:
                out.append(self.parse_value())
                self.skip_ws()
                if self.pos >= len(self.text):
                    raise YQError("unterminated flow sequence")
                if self.text[self.pos] == ",":
                    self.pos += 1
                    continue
                if self.text[self.pos] == "]":
                    self.pos += 1
                    return out
                raise YQError("expected ',' or ']' in flow sequence")
        if ch == "{":
            self.pos += 1
            out = {}
            self.skip_ws()
            if self.pos < len(self.text) and self.text[self.pos] == "}":
                self.pos += 1
                return out
            while True:
                key = self.parse_key()
                self.skip_ws()
                if self.pos >= len(self.text) or self.text[self.pos] != ":":
                    raise YQError("expected ':' in flow mapping")
                self.pos += 1
                out[key] = self.parse_value()
                self.skip_ws()
                if self.pos >= len(self.text):
                    raise YQError("unterminated flow mapping")
                if self.text[self.pos] == ",":
                    self.pos += 1
                    continue
                if self.text[self.pos] == "}":
                    self.pos += 1
                    return out
                raise YQError("expected ',' or '}' in flow mapping")
        if ch in "\"'":
            value, end = parse_quoted(self.text, self.pos)
            self.pos = end
            return value
        start = self.pos
        while self.pos < len(self.text) and \
                self.text[self.pos] not in ",]}":
            self.pos += 1
        token = self.text[start:self.pos].strip()
        if token == "":
            raise YQError("empty value in flow collection")
        return parse_scalar_token(token)

    def parse_key(self):
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] in "\"'":
            value, end = parse_quoted(self.text, self.pos)
            self.pos = end
            return value
        start = self.pos
        while self.pos < len(self.text) and \
                self.text[self.pos] not in ",:}":
            self.pos += 1
        key = self.text[start:self.pos].strip()
        if not key:
            raise YQError("empty key in flow mapping")
        return key


def parse_flow(text):
    parser = FlowParser(text)
    value = parser.parse_value()
    parser.skip_ws()
    if parser.pos != len(text):
        raise YQError("trailing characters after flow value: %r" % text)
    return value


# ---------------------------------------------------------------- block parser

def line_indent(raw):
    # Any tab before the first non-space character is an error.
    prefix = raw[:len(raw) - len(raw.lstrip())]
    if "\t" in prefix:
        raise YQError("tab character in indentation")
    return len(raw) - len(raw.lstrip(" "))


def find_mapping_colon(text):
    """Index of the ':' ending a block mapping key, or -1. Quote and
    flow aware; the colon must be followed by space or end of line."""
    in_single = False
    in_double = False
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0 and \
                (i + 1 == len(text) or text[i + 1] in " \t"):
            return i
        i += 1
    return -1


def unquote_key(key_text):
    key_text = key_text.strip()
    if key_text and key_text[0] in "\"'":
        value, end = parse_quoted(key_text, 0)
        if key_text[end:].strip():
            raise YQError("trailing characters after quoted key: %r"
                          % key_text)
        return value
    return key_text


class BlockParser:
    def __init__(self, text):
        self.lines = text.split("\n")
        self.n = len(self.lines)

    def content(self, i):
        """(indent, comment-stripped text) for line i. The text is
        stripped of leading whitespace too: structural parsing always
        compares against the explicit indent value."""
        raw = self.lines[i]
        indent = line_indent(raw)
        return indent, strip_comment(raw).strip()

    def skip_blank(self, i):
        while i < self.n:
            indent, text = self.content(i)
            if text.strip() == "":
                i += 1
                continue
            return i
        return i

    def parse_document(self):
        i = self.skip_blank(0)
        if i >= self.n:
            return None
        indent, text = self.content(i)
        if text == "---":
            i = self.skip_blank(i + 1)
            if i >= self.n:
                return None
        value, i = self.parse_block(i, 0)
        i = self.skip_blank(i)
        if i < self.n:
            _, text = self.content(i)
            if text == "---":
                raise YQError("multi-document streams are not supported")
            if text == "...":
                return value
            raise YQError("unexpected trailing content: %r" % text)
        return value

    def parse_block(self, i, min_indent):
        i = self.skip_blank(i)
        if i >= self.n:
            return None, i
        indent, text = self.content(i)
        if indent < min_indent or text in ("---", "..."):
            return None, i
        if text == "-" or text.startswith("- "):
            return self.parse_sequence(i, indent)
        colon = find_mapping_colon(text)
        if colon >= 0:
            return self.parse_mapping(i, indent)
        # Bare scalar document (possibly flow).
        value = self.parse_inline_value(text)
        return value, i + 1

    def parse_inline_value(self, text):
        text = text.strip()
        if text.startswith(("[", "{")):
            return parse_flow(text)
        if text and text[0] in "&*!":
            raise YQError(
                "anchors, aliases and tags are not supported: %r" % text)
        return parse_scalar_token(text)

    def parse_block_scalar(self, i, parent_indent, header):
        """Consume a block scalar starting after line i-1 (the header
        line). Returns (value, next_index)."""
        style = header[0]
        chomp = "clip"
        explicit = None
        for ch in header[1:].strip():
            if ch == "-":
                chomp = "strip"
            elif ch == "+":
                chomp = "keep"
            elif ch.isdigit():
                explicit = int(ch)
            else:
                raise YQError("bad block scalar header: %r" % header)
        # Collect raw content lines: blank lines, or lines indented
        # more than the parent node.
        items = []  # (indent, text)
        j = i
        content_indent = None
        if explicit is not None:
            content_indent = parent_indent + explicit
        while j < self.n:
            raw = self.lines[j]
            if raw.strip() == "":
                items.append((None, ""))
                j += 1
                continue
            indent = line_indent(raw)
            if indent <= parent_indent:
                break
            if content_indent is None:
                content_indent = indent
            if indent < content_indent:
                raise YQError(
                    "block scalar line indented less than content indent")
            items.append((indent, raw[content_indent:].rstrip()))
            j += 1
        if content_indent is None:
            return "", j
        # Drop trailing blank lines, remembering how many there were.
        trailing_blanks = 0
        while items and items[-1][1] == "":
            items.pop()
            trailing_blanks += 1
        if style == "|":
            body = "\n".join(t for _, t in items)
        else:  # folded
            paragraphs = []
            current = []  # (indent, text)
            blanks = 0
            for indent, t in items:
                if t == "":
                    if current:
                        paragraphs.append((current, blanks))
                        current = []
                        blanks = 0
                    blanks += 1
                    if not paragraphs:
                        blanks = 1
                    continue
                if current and blanks == 0:
                    pass
                current.append((indent, t))
                blanks = 0
            if current:
                paragraphs.append((current, 0))
            rendered = []
            for k, (para, _b) in enumerate(paragraphs):
                parts = []
                for m, (indent, t) in enumerate(para):
                    if m == 0:
                        parts.append(t)
                    elif indent > content_indent or \
                            para[m - 1][0] > content_indent:
                        parts.append("\n" + t)
                    else:
                        parts.append(" " + t)
                rendered.append("".join(parts))
            # Re-join paragraphs: one blank line -> one newline, etc.
            body = ""
            for k, text_part in enumerate(rendered):
                if k == 0:
                    body = text_part
                else:
                    n_blanks = paragraphs[k][1] if paragraphs[k][1] else 1
                    body += "\n" * n_blanks + text_part
        if chomp == "strip":
            return body, j
        if chomp == "clip":
            return (body + "\n") if body else "", j
        # keep: final newline plus one per trailing blank line
        if not body:
            return "", j
        return body + "\n" * (1 + trailing_blanks), j

    def parse_mapping(self, i, indent, first_text=None, first_index=None):
        result = {}
        pending = first_text
        while True:
            if pending is not None:
                text = pending
                pending = None
                # i already points past the virtual line; cur_i is the
                # virtual line's own index (for continuation scanning).
                cur_i = first_index if first_index is not None else i - 1
            else:
                i = self.skip_blank(i)
                if i >= self.n:
                    break
                ind, text = self.content(i)
                if ind < indent:
                    break
                if ind > indent:
                    raise YQError(
                        "unexpected indentation: %r" % text)
                if text in ("---", "..."):
                    break
                if text == "-" or text.startswith("- "):
                    break
                cur_i = i
            colon = find_mapping_colon(text)
            if colon < 0:
                raise YQError("expected 'key: value', got: %r" % text)
            key = unquote_key(text[:colon])
            if key == "<<" or key.startswith("?"):
                raise YQError(
                    "merge keys and complex keys are not supported")
            value_text = text[colon + 1:].strip()
            if value_text and value_text[0] in "&*!":
                raise YQError(
                    "anchors, aliases and tags are not supported: %r"
                    % value_text)
            if value_text and value_text[0] in ">|":
                value, nxt = self.parse_block_scalar(
                    cur_i + 1, indent, value_text)
                result[key] = value
                i = nxt
                continue
            if value_text == "":
                j = self.skip_blank(cur_i + 1)
                if j >= self.n:
                    result[key] = None
                    i = j
                    continue
                ind2, text2 = self.content(j)
                if ind2 > indent:
                    value, nxt = self.parse_block(j, ind2)
                    result[key] = value
                    i = nxt
                    continue
                if ind2 == indent and (text2 == "-" or
                                       text2.startswith("- ")):
                    value, nxt = self.parse_sequence(j, ind2)
                    result[key] = value
                    i = nxt
                    continue
                result[key] = None
                i = cur_i + 1
                continue
            # Inline value, possibly a multi-line plain scalar.
            if value_text.startswith(("[", "{")):
                value = parse_flow(value_text)
                i = cur_i + 1
            elif value_text[0] in "\"'":
                value, end = parse_quoted(value_text, 0)
                if value_text[end:].strip():
                    raise YQError(
                        "trailing characters after quoted scalar: %r"
                        % value_text)
                i = cur_i + 1
            else:
                parts = [value_text]
                nxt = cur_i + 1
                while True:
                    k = self.skip_blank(nxt)
                    if k >= self.n:
                        break
                    ind3, text3 = self.content(k)
                    if ind3 > indent and text3 not in ("---", "...") \
                            and not (text3 == "-" or
                                     text3.startswith("- ")):
                        parts.append(text3.strip())
                        nxt = k + 1
                        continue
                    break
                value = parse_scalar_token(" ".join(parts))
                i = nxt
            result[key] = value
        return result, i

    def parse_sequence(self, i, indent, first_text=None, first_index=None):
        result = []
        pending = first_text
        while True:
            if pending is not None:
                text = pending
                pending = None
                cur_i = first_index if first_index is not None else i - 1
            else:
                i = self.skip_blank(i)
                if i >= self.n:
                    break
                ind, text = self.content(i)
                if ind < indent:
                    break
                if ind > indent:
                    raise YQError(
                        "unexpected indentation: %r" % text)
                if text in ("---", "..."):
                    break
                if not (text == "-" or text.startswith("- ")):
                    break
                cur_i = i
            item_text = text[1:].strip()
            if item_text == "":
                j = self.skip_blank(cur_i + 1)
                if j >= self.n:
                    result.append(None)
                    i = j
                    continue
                ind2, _ = self.content(j)
                if ind2 <= indent:
                    result.append(None)
                    i = cur_i + 1
                    continue
                value, nxt = self.parse_block(j, ind2)
                result.append(value)
                i = nxt
                continue
            if item_text[0] in ">|":
                value, nxt = self.parse_block_scalar(
                    cur_i + 1, indent, item_text)
                result.append(value)
                i = nxt
                continue
            colon = find_mapping_colon(item_text)
            if colon >= 0:
                value, nxt = self.parse_mapping(
                    cur_i + 1, indent + 2, first_text=item_text,
                    first_index=cur_i)
                result.append(value)
                i = nxt
                continue
            if item_text == "-" or item_text.startswith("- "):
                value, nxt = self.parse_sequence(
                    cur_i + 1, indent + 2, first_text=item_text,
                    first_index=cur_i)
                result.append(value)
                i = nxt
                continue
            if item_text.startswith(("[", "{")):
                result.append(parse_flow(item_text))
                i = cur_i + 1
                continue
            if item_text[0] in "&*!":
                raise YQError(
                    "anchors, aliases and tags are not supported: %r"
                    % item_text)
            if item_text[0] in "\"'":
                value, end = parse_quoted(item_text, 0)
                if item_text[end:].strip():
                    raise YQError(
                        "trailing characters after quoted scalar: %r"
                        % item_text)
                result.append(value)
                i = cur_i + 1
                continue
            # Plain scalar, possibly continued on more-indented lines.
            parts = [item_text]
            nxt = cur_i + 1
            while True:
                k = self.skip_blank(nxt)
                if k >= self.n:
                    break
                ind3, text3 = self.content(k)
                if ind3 > indent and text3 not in ("---", "...") \
                        and not (text3 == "-" or
                                 text3.startswith("- ")):
                    # A following mapping key at deeper indent would
                    # belong to a nested block, not to this scalar;
                    # but a scalar item has no nested block, so a
                    # deeper line can only be a continuation. The one
                    # exception is a mapping continuation of an
                    # inline map, handled above, not here.
                    parts.append(text3.strip())
                    nxt = k + 1
                    continue
                break
            result.append(parse_scalar_token(" ".join(parts)))
            i = nxt
        return result, i


def parse_yaml(text):
    return BlockParser(text).parse_document()


# ---------------------------------------------------------------- filters

# A step is a tuple: ("key", name, optional) | ("index", n, optional)
#                   | ("iterate", optional) | ("collect", filter)
# A stage is a list of steps; a filter is a list of stages.


def split_pipes(text):
    parts = []
    depth = 0
    in_single = False
    in_double = False
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth < 0:
                raise YQError("unbalanced brackets in filter")
        elif ch == "|" and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    if in_single or in_double:
        raise YQError("unterminated quote in filter")
    if depth != 0:
        raise YQError("unbalanced brackets in filter")
    parts.append(text[start:])
    return parts


def find_matching_bracket(text, pos):
    depth = 0
    in_single = False
    in_double = False
    i = pos
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise YQError("unbalanced '[' in filter")


def parse_stage(stage):
    stage = stage.strip()
    if not stage:
        raise YQError("empty filter stage (check for a stray '|')")
    if stage.startswith("[") and stage != "[]":
        end = find_matching_bracket(stage, 0)
        if end == len(stage) - 1:
            inner = stage[1:-1].strip()
            inner_filter = parse_filter(inner) if inner else []
            return [("collect", inner_filter)]
    steps = []
    i = 0
    n = len(stage)
    # A stage may start with '[' (iterate) without a leading dot.
    if stage.startswith("["):
        end = find_matching_bracket(stage, 0)
        inner = stage[1:end].strip()
        if inner != "":
            raise YQError("stage must start with '.' or '[]'")
        steps.append(("iterate", False))
        i = end + 1
        if i < n and stage[i] == "?":
            steps[-1] = ("iterate", True)
            i += 1
        if i >= n:
            return steps
        if stage[i] != "." and stage[i] != "[":
            raise YQError("unexpected character in filter: %r" % stage[i])
    elif stage[0] != ".":
        raise YQError("filter stage must start with '.'")
    # Unified loop: '.' introduces a name (or a following bracket);
    # '[' introduces a bracket step. The leading '.' is consumed by
    # the loop itself, so '.a.b', '.a.[b]' and '.' all parse.
    while i < n:
        ch = stage[i]
        if ch == ".":
            i += 1
            if i >= n:
                break
            if stage[i] == "[":
                continue  # bracket branch below handles it
            m = re.match(r"[A-Za-z_][A-Za-z0-9_-]*", stage[i:])
            if not m:
                raise YQError(
                    "expected a field name after '.' in filter")
            name = m.group(0)
            i += len(name)
            optional = False
            if i < n and stage[i] == "?":
                optional = True
                i += 1
            steps.append(("key", name, optional))
            continue
        if ch == "[":
            end = find_matching_bracket(stage, i)
            inner = stage[i + 1:end].strip()
            i = end + 1
            optional = False
            if i < n and stage[i] == "?":
                optional = True
                i += 1
            if inner == "":
                steps.append(("iterate", optional))
            elif inner[0] in "\"'":
                value, e = parse_quoted(inner, 0)
                if inner[e:].strip():
                    raise YQError("bad bracket key: %r" % inner)
                steps.append(("key", value, optional))
            elif re.fullmatch(r"-?[0-9]+", inner):
                steps.append(("index", int(inner), optional))
            else:
                steps.append(("key", inner, optional))
            continue
        raise YQError("unexpected character in filter: %r" % ch)
    return steps


def parse_filter(text):
    text = text.strip()
    if text == "":
        return []
    stages = []
    for part in split_pipes(text):
        stages.append(parse_stage(part))
    return stages


def apply_step(step, value):
    kind = step[0]
    if kind == "collect":
        inner = step[1]
        return [eval_filter(inner, value)]
    if kind == "key":
        _, name, optional = step
        if isinstance(value, dict):
            return [value.get(name)]
        if optional:
            return [None]
        raise YQError("cannot get key %r from %s"
                      % (name, type(value).__name__))
    if kind == "index":
        _, idx, optional = step
        if isinstance(value, list):
            pos = idx if idx >= 0 else len(value) + idx
            if 0 <= pos < len(value):
                return [value[pos]]
            return [None]
        if optional:
            return [None]
        raise YQError("cannot index %s with %d"
                      % (type(value).__name__, idx))
    if kind == "iterate":
        _, optional = step
        if isinstance(value, list):
            return list(value)
        if optional:
            return [None]
        raise YQError("cannot iterate over %s" % type(value).__name__)
    raise YQError("unknown step: %r" % (step,))


def eval_filter(filter_, value):
    values = [value]
    for stage in filter_:
        new_values = []
        for val in values:
            step_values = [val]
            for step in stage:
                nxt = []
                for sv in step_values:
                    nxt.extend(apply_step(step, sv))
                step_values = nxt
            new_values.extend(step_values)
        values = new_values
    return values


# ---------------------------------------------------------------- emitter

_PLAIN_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ ./-]*$")


def quote_double(text):
    out = []
    for ch in text:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def format_scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return ".nan"
        if value == float("inf"):
            return ".inf"
        if value == float("-inf"):
            return "-.inf"
        return repr(value)
    text = value
    if text == "":
        return '""'
    if "\n" in text:
        if text.endswith("\n"):
            style = "|"
            body = text[:-1].split("\n")
        else:
            style = "|-"
            body = text.split("\n")
        return style + "\n" + "\n".join("  " + line for line in body)
    needs_quote = False
    if text.strip() != text or looks_typed(text):
        needs_quote = True
    if ": " in text or " #" in text or text.endswith(":") or \
            text.startswith(("- ", "? ", ": ", "#", "&", "*", "!", "|",
                             ">", "'", '"', "%", "@", "`", "[", "]",
                             "{", "}", ",")):
        needs_quote = True
    if needs_quote:
        return quote_double(text)
    return text


def format_key(key):
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", key) and \
            not looks_typed(key):
        return key
    return quote_double(key)


def dump_value(value):
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for key, val in value.items():
            k = format_key(str(key))
            if isinstance(val, (dict, list)) and val:
                lines.append("%s:" % k)
                lines.extend("  " + ln for ln in
                             dump_value(val).split("\n"))
            else:
                rendered = dump_value(val)
                sub = rendered.split("\n")
                lines.append("%s: %s" % (k, sub[0]))
                lines.extend("  " + ln for ln in sub[1:])
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)) and item:
                sub = dump_value(item).split("\n")
                lines.append("- " + sub[0])
                lines.extend("  " + ln for ln in sub[1:])
            else:
                sub = dump_value(item).split("\n")
                lines.append("- " + sub[0])
                lines.extend("  " + ln for ln in sub[1:])
        return "\n".join(lines)
    return format_scalar(value)


# ---------------------------------------------------------------- CLI

def main(argv):
    args = argv[1:]
    filter_text = "."
    filename = None
    if len(args) == 1:
        arg = args[0]
        if arg == "-":
            pass
        elif arg.endswith((".yaml", ".yml")) or _is_file(arg):
            filename = arg
        else:
            filter_text = arg
    elif len(args) == 2:
        filter_text, filename = args
    elif len(args) > 2:
        sys.stderr.write(
            "usage: ccyq.py [FILTER] [FILE]\n")
        return 2
    try:
        filter_ = parse_filter(filter_text)
        if filename is None or filename == "-":
            text = sys.stdin.read()
        else:
            with open(filename, "r", encoding="utf-8") as fh:
                text = fh.read()
        data = parse_yaml(text)
        results = eval_filter(filter_, data)
    except YQError as exc:
        sys.stderr.write("ccyq: %s\n" % exc)
        return 2
    except OSError as exc:
        sys.stderr.write("ccyq: %s\n" % exc)
        return 2
    except BrokenPipeError:
        return 0
    if not results:
        print("[]")
        return 0
    if len(results) == 1:
        print(dump_value(results[0]))
    else:
        print("\n---\n".join(dump_value(r) for r in results))
    return 0


def _is_file(arg):
    try:
        with open(arg, "rb"):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(main(sys.argv))

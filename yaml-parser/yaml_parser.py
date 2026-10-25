#!/usr/bin/env python3
"""Hand-written YAML parser (subset) — standard library only.

Parses block mappings/sequences, flow collections, YAML 1.1
scalars, quoted strings, and folded/literal block scalars into
Python values. No PyYAML or any other YAML library is used.

Usage:
    python3 yaml_parser.py FILE        # print JSON (indent 2)
    python3 yaml_parser.py              # read YAML from stdin

See docs/SPEC.md for the supported subset and deliberate limits.
"""

import json
import math
import re
import sys

__all__ = ["YamlError", "parse", "parse_file"]


class YamlError(Exception):
    """Parse error carrying the offending source line number."""

    def __init__(self, message, lineno=None):
        super().__init__(message)
        self.message = message
        self.lineno = lineno

    def __str__(self):
        if self.lineno is not None:
            return "line %d: %s" % (self.lineno, self.message)
        return self.message


# ---------------------------------------------------------------------------
# Scalar typing (YAML 1.1, as required by the challenge's `off` example)
# ---------------------------------------------------------------------------

_NULL_WORDS = {"", "~", "null"}
_TRUE_WORDS = {"y", "yes", "true", "on"}
_FALSE_WORDS = {"n", "no", "false", "off"}

_INT_RE = re.compile(r"[-+]?[0-9][0-9_]*\Z")
_HEX_RE = re.compile(r"([-+]?)0x[0-9a-fA-F_]+\Z")
_OCT_RE = re.compile(r"([-+]?)0o[0-7_]+\Z")
_FLOAT_RE = re.compile(
    r"[-+]?(\.[0-9]+|[0-9][0-9_]*(\.[0-9_]*)?)([eE][-+]?[0-9]+)?\Z"
)
_INF_RE = re.compile(r"([-+]?)\.(inf|Inf|INF)\Z")
_NAN_RE = re.compile(r"[-+]?\.(nan|NaN|NAN)\Z")


def _signed_int(sign, digits, base):
    value = int(digits, base)
    return -value if sign == "-" else value


def parse_scalar_token(token, lineno=None):
    """Type a plain scalar token following YAML 1.1 rules."""
    text = token.strip()
    low = text.lower()
    if low in _NULL_WORDS:
        return None
    if low in _TRUE_WORDS:
        return True
    if low in _FALSE_WORDS:
        return False
    m = _INF_RE.match(text)
    if m:
        return math.inf if m.group(1) != "-" else -math.inf
    if _NAN_RE.match(text):
        return math.nan
    m = _HEX_RE.match(text)
    if m:
        digits = text[m.start() + len(m.group(1)) + 2 :]
        return _signed_int(m.group(1), digits.replace("_", ""), 16)
    m = _OCT_RE.match(text)
    if m:
        digits = text[m.start() + len(m.group(1)) + 2 :]
        return _signed_int(m.group(1), digits.replace("_", ""), 8)
    if _INT_RE.match(text):
        sign = ""
        digits = text
        if digits[0] in "+-":
            sign, digits = digits[0], digits[1:]
        digits = digits.replace("_", "")
        # Legacy leading-zero octal, e.g. 023332 -> 9946. A
        # leading-zero literal containing 8/9 is not valid octal,
        # so it falls back to decimal instead of erroring.
        if len(digits) > 1 and digits[0] == "0" and all(
            c in "01234567" for c in digits
        ):
            return _signed_int(sign, digits, 8)
        return _signed_int(sign, digits, 10)
    if _FLOAT_RE.match(text) and ("." in text or "e" in low):
        try:
            return float(text.replace("_", ""))
        except ValueError:
            pass
    return text


# ---------------------------------------------------------------------------
# Quoted scalars
# ---------------------------------------------------------------------------

_SIMPLE_ESCAPES = {
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    '"': '"',
    "\\": "\\",
    "/": "/",
    " ": " ",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}


def parse_double_quoted(text, start, lineno):
    """Parse a double-quoted scalar starting at text[start] == '"'.

    Returns (value, index just past the closing quote).
    """
    out = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == '"':
            return "".join(out), i + 1
        if ch == "\\":
            if i + 1 >= len(text):
                raise YamlError("unterminated escape in double-quoted string", lineno)
            esc = text[i + 1]
            if esc in _SIMPLE_ESCAPES:
                out.append(_SIMPLE_ESCAPES[esc])
                i += 2
                continue
            if esc in "xuU":
                width = {"x": 2, "u": 4, "U": 8}[esc]
                hexpart = text[i + 2 : i + 2 + width]
                if len(hexpart) != width or not all(
                    c in "0123456789abcdefABCDEF" for c in hexpart
                ):
                    raise YamlError(
                        "invalid \\%s escape in double-quoted string" % esc, lineno
                    )
                out.append(chr(int(hexpart, 16)))
                i += 2 + width
                continue
            raise YamlError(
                "unknown escape '\\%s' in double-quoted string" % esc, lineno
            )
        out.append(ch)
        i += 1
    raise YamlError("unterminated double-quoted string", lineno)


def parse_single_quoted(text, start, lineno):
    """Parse a single-quoted scalar starting at text[start] == "'".

    Returns (value, index just past the closing quote). '' is one '.
    """
    out = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "'":
            if i + 1 < len(text) and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    raise YamlError("unterminated single-quoted string", lineno)


# ---------------------------------------------------------------------------
# Flow collections: [a, b] and {k: v}
# ---------------------------------------------------------------------------


class FlowParser:
    def __init__(self, text, lineno):
        self.text = text
        self.lineno = lineno
        self.pos = 0

    def parse_top(self):
        value = self.parse_value()
        self.skip_ws()
        if self.pos != len(self.text):
            raise YamlError(
                "unexpected trailing characters in flow value: %r"
                % self.text[self.pos :],
                self.lineno,
            )
        return value

    def skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1

    def parse_value(self):
        self.skip_ws()
        if self.pos >= len(self.text):
            raise YamlError("unexpected end of flow value", self.lineno)
        ch = self.text[self.pos]
        if ch == "[":
            return self.parse_sequence()
        if ch == "{":
            return self.parse_mapping()
        if ch == '"':
            value, self.pos = parse_double_quoted(self.text, self.pos, self.lineno)
            return value
        if ch == "'":
            value, self.pos = parse_single_quoted(self.text, self.pos, self.lineno)
            return value
        return self.parse_plain(stop_at_colon=False)

    def parse_sequence(self):
        self.pos += 1  # [
        items = []
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == "]":
            self.pos += 1
            return items
        while True:
            items.append(self.parse_value())
            self.skip_ws()
            if self.pos >= len(self.text):
                raise YamlError("unclosed flow sequence '['", self.lineno)
            ch = self.text[self.pos]
            if ch == ",":
                self.pos += 1
                continue
            if ch == "]":
                self.pos += 1
                return items
            raise YamlError(
                "expected ',' or ']' in flow sequence, got %r" % ch, self.lineno
            )

    def parse_mapping(self):
        self.pos += 1  # {
        result = {}
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == "}":
            self.pos += 1
            return result
        while True:
            self.skip_ws()
            if self.pos >= len(self.text):
                raise YamlError("unclosed flow mapping '{'", self.lineno)
            ch = self.text[self.pos]
            if ch == '"':
                key, self.pos = parse_double_quoted(self.text, self.pos, self.lineno)
            elif ch == "'":
                key, self.pos = parse_single_quoted(self.text, self.pos, self.lineno)
            elif ch in "[{":
                raise YamlError("complex flow keys are not supported", self.lineno)
            else:
                key = self.parse_plain(stop_at_colon=True)
            self.skip_ws()
            if self.pos >= len(self.text) or self.text[self.pos] != ":":
                raise YamlError("expected ':' in flow mapping", self.lineno)
            self.pos += 1
            self.skip_ws()
            if self.pos < len(self.text) and self.text[self.pos] in ",}":
                value = None
            else:
                value = self.parse_value()
            try:
                if key in result:
                    raise YamlError("duplicate key %r in flow mapping" % (key,), self.lineno)
                result[key] = value
            except TypeError:
                raise YamlError("unhashable key in flow mapping", self.lineno)
            self.skip_ws()
            if self.pos >= len(self.text):
                raise YamlError("unclosed flow mapping '{'", self.lineno)
            ch = self.text[self.pos]
            if ch == ",":
                self.pos += 1
                continue
            if ch == "}":
                self.pos += 1
                return result
            raise YamlError(
                "expected ',' or '}' in flow mapping, got %r" % ch, self.lineno
            )

    def parse_plain(self, stop_at_colon):
        start = self.pos
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch in ",]}":
                break
            if ch == ":" and stop_at_colon:
                nxt = self.text[self.pos + 1 : self.pos + 2]
                if nxt in ("", " ", ",", "}", "]"):
                    break
            self.pos += 1
        token = self.text[start : self.pos].strip()
        if not token:
            raise YamlError("empty value in flow collection", self.lineno)
        if token[0] in "&*!":
            raise YamlError(
                "anchors, aliases and tags are not supported: %r" % token, self.lineno
            )
        return parse_scalar_token(token, self.lineno)


def parse_inline(text, lineno):
    """Parse an inline (same-line) value: flow, quoted, or plain."""
    s = text.strip()
    if not s:
        return None
    if s[0] in "&*!":
        raise YamlError(
            "anchors, aliases and tags are not supported: %r" % s, lineno
        )
    if s[0] == "%":
        raise YamlError("directives are not supported: %r" % s, lineno)
    if s[0] in "[{":
        return FlowParser(s, lineno).parse_top()
    if s[0] == '"':
        value, end = parse_double_quoted(s, 0, lineno)
        if s[end:].strip():
            raise YamlError(
                "unexpected trailing characters after quoted string: %r"
                % s[end:].strip(),
                lineno,
            )
        return value
    if s[0] == "'":
        value, end = parse_single_quoted(s, 0, lineno)
        if s[end:].strip():
            raise YamlError(
                "unexpected trailing characters after quoted string: %r"
                % s[end:].strip(),
                lineno,
            )
        return value
    return parse_scalar_token(s, lineno)


# ---------------------------------------------------------------------------
# Line model
# ---------------------------------------------------------------------------


class RawLine:
    __slots__ = ("lineno", "indent", "content", "raw_index")

    def __init__(self, lineno, indent, content, raw_index):
        self.lineno = lineno
        self.indent = indent
        self.content = content
        self.raw_index = raw_index


class SigLine:
    __slots__ = ("lineno", "indent", "text", "raw_index")

    def __init__(self, lineno, indent, text, raw_index):
        self.lineno = lineno
        self.indent = indent
        self.text = text
        self.raw_index = raw_index


def strip_comment(text):
    """Remove a trailing comment (# preceded by space, outside quotes)."""
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
        elif quote == "'":
            if ch == "'":
                quote = None
        else:
            if ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
                return text[:i].rstrip()
        i += 1
    return text.rstrip()


def find_key(text):
    """Index of the mapping colon in text, or None.

    The colon must be outside quotes/flow brackets and followed by
    a space or end-of-line.
    """
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
        elif quote == "'":
            if ch == "'":
                quote = None
        else:
            if ch in "\"'":
                quote = ch
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                nxt = text[i + 1 : i + 2]
                if nxt in ("", " "):
                    return i
        i += 1
    return None


def is_seq_line(text):
    return text == "-" or text.startswith("- ")


def is_block_indicator(text):
    return text in (">", "|", ">-", ">+", "|-", "|+")


# ---------------------------------------------------------------------------
# Block parser
# ---------------------------------------------------------------------------


class Parser:
    def __init__(self, text):
        self.raw_lines = []
        for raw_index, raw in enumerate(text.splitlines()):
            line = raw.rstrip("\r")
            leading = 0
            while leading < len(line) and line[leading] in " \t":
                leading += 1
            if "\t" in line[:leading]:
                raise YamlError(
                    "tabs are not allowed for indentation", raw_index + 1
                )
            stripped = line[leading:]
            indent = leading
            self.raw_lines.append(
                RawLine(raw_index + 1, indent, stripped, raw_index)
            )
        self.lines = []
        for raw_line in self.raw_lines:
            content = strip_comment(raw_line.content)
            if not content.strip():
                continue
            if content.lstrip().startswith("#"):
                continue
            self.lines.append(
                SigLine(
                    raw_line.lineno,
                    raw_line.indent,
                    content,
                    raw_line.raw_index,
                )
            )
        # Document markers: one leading ---, one trailing ...
        if self.lines and self.lines[0].text == "---":
            self.lines.pop(0)
        if self.lines and self.lines[-1].text == "...":
            self.lines.pop()
        for line in self.lines:
            if line.text == "---":
                raise YamlError(
                    "multi-document streams are not supported", line.lineno
                )
            if line.text == "...":
                raise YamlError(
                    "unexpected document end marker '...'", line.lineno
                )
        self.pos = 0

    def peek(self):
        if self.pos < len(self.lines):
            return self.lines[self.pos]
        return None

    def advance(self):
        line = self.lines[self.pos]
        self.pos += 1
        return line

    def parse(self):
        if not self.lines:
            return None
        value = self.parse_block(self.lines[0].indent)
        extra = self.peek()
        if extra is not None:
            raise YamlError(
                "unexpected content after document", extra.lineno
            )
        return value

    def parse_block(self, indent):
        line = self.peek()
        if line is None:
            return None
        if is_seq_line(line.text):
            return self.parse_sequence(indent)
        if find_key(line.text) is not None:
            return self.parse_mapping(indent)
        if is_block_indicator(line.text.strip()):
            self.advance()
            return self.parse_block_scalar(
                indent, line.text.strip(), line.raw_index + 1
            )
        self.advance()
        return parse_inline(line.text, line.lineno)

    def parse_mapping(self, indent, first=None):
        """Parse a mapping at `indent`.

        `first` is an optional virtual first line
        (text, lineno, raw_index) — used for `- key: value` items,
        where the first key sits on the dash line.
        """
        result = {}
        pending = first
        while True:
            if pending is not None:
                text, lineno, raw_index = pending
                pending = None
            else:
                line = self.peek()
                if line is None:
                    break
                if line.indent < indent:
                    break
                if line.indent > indent:
                    raise YamlError(
                        "unexpected indentation", line.lineno
                    )
                if is_seq_line(line.text):
                    break
                text, lineno, raw_index = (
                    line.text,
                    line.lineno,
                    line.raw_index,
                )
                self.advance()
            key_idx = find_key(text)
            if key_idx is None:
                raise YamlError(
                    "expected a mapping key ('key: value'), got %r" % text,
                    lineno,
                )
            key_text = text[:key_idx].strip()
            if not key_text:
                raise YamlError("empty mapping key", lineno)
            key = parse_inline(key_text, lineno)
            try:
                if key in result:
                    raise YamlError(
                        "duplicate key %r in mapping" % (key,), lineno
                    )
            except TypeError:
                raise YamlError("unhashable mapping key", lineno)
            rest = text[key_idx + 1 :].strip()
            if rest == "":
                value = self._value_after_empty_key(indent)
            elif is_block_indicator(rest):
                value = self.parse_block_scalar(indent, rest, raw_index + 1)
            elif rest[0] in ">|" and len(rest) > 1:
                # e.g. |2 (explicit indentation) — not supported.
                raise YamlError(
                    "block scalar indicator %r is not supported" % rest, lineno
                )
            else:
                value = parse_inline(rest, lineno)
            result[key] = value
        return result

    def _value_after_empty_key(self, indent):
        nxt = self.peek()
        if nxt is None:
            return None
        if nxt.indent > indent:
            return self.parse_block(nxt.indent)
        if nxt.indent == indent and is_seq_line(nxt.text):
            return self.parse_sequence(indent)
        return None

    def parse_sequence(self, indent, first=None):
        """Parse a block sequence at `indent`.

        `first` is an optional virtual first line
        (text, lineno, raw_index) — used for `- - item` nesting.
        """
        result = []
        pending = first
        while True:
            if pending is not None:
                text, lineno, raw_index = pending
                pending = None
            else:
                line = self.peek()
                if line is None:
                    break
                if line.indent < indent:
                    break
                if line.indent > indent:
                    raise YamlError(
                        "unexpected indentation", line.lineno
                    )
                if not is_seq_line(line.text):
                    break
                text, lineno, raw_index = (
                    line.text,
                    line.lineno,
                    line.raw_index,
                )
                self.advance()
            content = "" if text == "-" else text[2:].strip()
            if content == "":
                nxt = self.peek()
                if nxt is not None and nxt.indent > indent:
                    result.append(self.parse_block(nxt.indent))
                else:
                    result.append(None)
            elif is_block_indicator(content):
                result.append(
                    self.parse_block_scalar(indent, content, raw_index + 1)
                )
            elif content[0] in ">|" and len(content) > 1:
                raise YamlError(
                    "block scalar indicator %r is not supported" % content,
                    lineno,
                )
            elif content.startswith("- ") or content == "-":
                result.append(
                    self.parse_sequence(
                        indent + 2, first=(content, lineno, raw_index)
                    )
                )
            elif find_key(content) is not None and not content.startswith(("[", "{")):
                result.append(
                    self.parse_mapping(
                        indent + 2, first=(content, lineno, raw_index)
                    )
                )
            else:
                result.append(parse_inline(content, lineno))
        return result

    def parse_block_scalar(self, parent_indent, indicator, start_raw):
        style = indicator[0]
        chomp = indicator[1:] if len(indicator) > 1 else ""
        i = start_raw
        collected = []  # str lines, or None for blank lines
        block_indent = None
        while i < len(self.raw_lines):
            raw = self.raw_lines[i]
            if raw.content.strip() == "":
                collected.append(None)
                i += 1
                continue
            if raw.indent <= parent_indent:
                break
            if block_indent is None:
                block_indent = raw.indent
            if raw.indent < block_indent:
                break
            collected.append(" " * (raw.indent - block_indent) + raw.content)
            i += 1
        trailing = 0
        while collected and collected[-1] is None:
            collected.pop()
            trailing += 1
        if not collected:
            body = ""
        elif style == "|":
            body = "\n".join("" if c is None else c for c in collected)
        else:  # folded
            parts = []
            last_was_text = False
            for entry in collected:
                if entry is None:
                    parts.append("\n")
                    last_was_text = False
                else:
                    if last_was_text:
                        parts.append(" ")
                    parts.append(entry)
                    last_was_text = True
            body = "".join(parts)
        if not body:
            result = ""
        elif chomp == "-":
            result = body
        elif chomp == "+":
            result = body + "\n" * (trailing + 1)
        else:  # clip
            result = body + "\n"
        # Resync the significant-line cursor past the block.
        while self.peek() is not None and self.peek().raw_index < i:
            self.advance()
        return result


def parse(text):
    """Parse YAML text into Python data (dict/list/scalar/None)."""
    return Parser(text).parse()


def parse_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return parse(handle.read())


def main(argv):
    args = [a for a in argv[1:] if a != "--json"]
    if len(args) > 1:
        print("usage: yaml_parser.py [FILE] [--json]", file=sys.stderr)
        return 2
    try:
        if args:
            with open(args[0], "r", encoding="utf-8") as handle:
                text = handle.read()
        else:
            text = sys.stdin.read()
        value = parse(text)
    except YamlError as exc:
        print("yaml_parser.py: %s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("yaml_parser.py: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(value, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

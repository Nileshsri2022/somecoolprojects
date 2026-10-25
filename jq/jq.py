#!/usr/bin/env python3
"""ccjq — a small jq clone (Python 3 standard library only).

Implements the filter subset in docs/SPEC.md: identity, field access,
array index/slice, iterate, pipes, commas, //, and/or, comparisons,
arithmetic, array/object construction, string interpolation, and the
builtins select, map, length, keys, type, values, empty, not, has,
tostring, tonumber.

The JSON parser and the output serializer are hand-written in this
file; Python's json module is not used, so parsed number literals
keep their original text (like system jq) and string escaping is
jq-style.
"""

import math
import sys

# ---------------------------------------------------------------- errors


class JqError(Exception):
    """Runtime filter error (exit 5)."""


class FilterSyntaxError(Exception):
    """Filter compile error (exit 3)."""


class JsonError(Exception):
    """Input JSON error (exit 5)."""


# ---------------------------------------------------------------- numbers


def _norm_exponent(literal):
    """Normalise a number literal's exponent to E+/- form, as jq does
    (1e20 -> 1E+20); the mantissa is left untouched."""
    if "e" not in literal and "E" not in literal:
        return literal
    mant, _, exp = literal.replace("E", "e").partition("e")
    sign = "+" if not exp.startswith(("-", "+")) else exp[0]
    digits = exp.lstrip("+-").lstrip("0") or "0"
    return "%sE%s%s" % (mant, sign, digits)


class JqNumber:
    """A JSON number: its numeric value, plus (for parsed literals)
    the original source text, which is what gets printed."""

    __slots__ = ("value", "literal")

    def __init__(self, value, literal=None):
        self.value = value
        self.literal = literal

    def __repr__(self):
        return "JqNumber(%r)" % (self.value,)

    def __eq__(self, other):
        if isinstance(other, JqNumber):
            return self.value == other.value
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return self.value == other
        return NotImplemented

    def __hash__(self):
        return hash(float(self.value))

    def format(self):
        if self.literal is not None:
            return _norm_exponent(self.literal)
        return format_computed_number(self.value)


def format_computed_number(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise JqError("number %r cannot be represented" % (value,))
        if value == int(value) and abs(value) < 1e21:
            return str(int(value))
        text = repr(value)
        if "e" in text:
            return _norm_exponent(text)
        return text
    raise JqError("not a number: %r" % (value,))


def is_number(v):
    return isinstance(v, JqNumber)


def num_value(v):
    return v.value


# ---------------------------------------------------------------- JSON parser


def _decode_escapes(raw, what="string"):
    """Decode JSON escape sequences in raw (the text between quotes).
    Returns the decoded string; raises JsonError on bad escapes."""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= n:
            raise JsonError("unterminated escape in %s" % what)
        e = raw[i + 1]
        simple = {'"': '"', "\\": "\\", "/": "/",
                  "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
        if e in simple:
            out.append(simple[e])
            i += 2
        elif e == "u":
            if i + 6 > n:
                raise JsonError("bad \\u escape in %s" % what)
            try:
                code = int(raw[i + 2:i + 6], 16)
            except ValueError:
                raise JsonError("bad \\u escape in %s" % what)
            i += 6
            if 0xD800 <= code <= 0xDBFF and raw[i:i + 2] == "\\u":
                try:
                    low = int(raw[i + 2:i + 6], 16)
                except ValueError:
                    low = -1
                if 0xDC00 <= low <= 0xDFFF:
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                    i += 6
            out.append(chr(code))
        else:
            raise JsonError("bad escape \\%s in %s" % (e, what))
    return "".join(out)


class JsonParser:
    def __init__(self, text):
        self.text = text
        self.i = 0
        self.n = len(text)

    def error(self, msg):
        line = self.text.count("\n", 0, self.i) + 1
        col = self.i - self.text.rfind("\n", 0, self.i)
        raise JsonError("%s at line %d, column %d" % (msg, line, col))

    def skip_ws(self):
        while self.i < self.n and self.text[self.i] in " \t\r\n":
            self.i += 1

    def peek(self):
        return self.text[self.i] if self.i < self.n else ""

    def parse_value(self):
        self.skip_ws()
        c = self.peek()
        if c == "{":
            return self.parse_object()
        if c == "[":
            return self.parse_array()
        if c == '"':
            return self.parse_string()
        if c == "t":
            return self.parse_literal("true", True)
        if c == "f":
            return self.parse_literal("false", False)
        if c == "n":
            return self.parse_literal("null", None)
        if c == "-" or c.isdigit():
            return self.parse_number()
        if c == "":
            self.error("unexpected end of input")
        self.error("unexpected character %r" % c)

    def parse_literal(self, word, value):
        if self.text[self.i:self.i + len(word)] != word:
            self.error("invalid literal")
        self.i += len(word)
        return value

    def parse_number(self):
        start = self.i
        if self.peek() == "-":
            self.i += 1
        if not self.peek().isdigit():
            self.error("invalid number")
        if self.peek() == "0":
            self.i += 1
        else:
            while self.peek().isdigit():
                self.i += 1
        is_float = False
        if self.peek() == ".":
            is_float = True
            self.i += 1
            if not self.peek().isdigit():
                self.error("invalid number")
            while self.peek().isdigit():
                self.i += 1
        if self.peek() in ("e", "E"):
            is_float = True
            self.i += 1
            if self.peek() in ("+", "-"):
                self.i += 1
            if not self.peek().isdigit():
                self.error("invalid number")
            while self.peek().isdigit():
                self.i += 1
        literal = self.text[start:self.i]
        value = float(literal) if is_float else int(literal)
        return JqNumber(value, literal)

    def parse_string(self):
        # self.text[self.i] == '"'; scan raw inner text, then decode.
        self.i += 1
        raw = []
        while True:
            if self.i >= self.n:
                self.error("unterminated string")
            c = self.text[self.i]
            if c == '"':
                self.i += 1
                break
            if c == "\\":
                if self.i + 1 >= self.n:
                    self.error("unterminated string")
                raw.append(self.text[self.i:self.i + 2])
                self.i += 2
                if raw[-1] == "\\u":
                    if self.i + 4 > self.n:
                        self.error("unterminated string")
                    raw.append(self.text[self.i:self.i + 4])
                    self.i += 4
                continue
            if ord(c) < 0x20:
                self.error("unescaped control character in string")
            raw.append(c)
            self.i += 1
        return _decode_escapes("".join(raw))

    def parse_array(self):
        self.i += 1
        out = []
        self.skip_ws()
        if self.peek() == "]":
            self.i += 1
            return out
        while True:
            out.append(self.parse_value())
            self.skip_ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                continue
            if c == "]":
                self.i += 1
                return out
            self.error("expected ',' or ']' in array")

    def parse_object(self):
        self.i += 1
        out = {}
        self.skip_ws()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            self.skip_ws()
            if self.peek() != '"':
                self.error("expected string key in object")
            key = self.parse_string()
            self.skip_ws()
            if self.peek() != ":":
                self.error("expected ':' in object")
            self.i += 1
            out[key] = self.parse_value()
            self.skip_ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                continue
            if c == "}":
                self.i += 1
                return out
            self.error("expected ',' or '}' in object")


def parse_json_stream(text):
    """Parse all concatenated JSON documents in text."""
    parser = JsonParser(text)
    docs = []
    while True:
        parser.skip_ws()
        if parser.i >= parser.n:
            break
        docs.append(parser.parse_value())
        parser.skip_ws()
    return docs


# ---------------------------------------------------------------- serializer


def escape_string(s):
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif c == "\b":
            out.append("\\b")
        elif c == "\f":
            out.append("\\f")
        elif ord(c) < 0x20:
            out.append("\\u%04x" % ord(c))
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def format_json(value, compact=False, sort_keys=False, _level=0):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return escape_string(value)
    if isinstance(value, JqNumber):
        return value.format()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_computed_number(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [format_json(v, compact, sort_keys, _level + 1)
                 for v in value]
        if compact:
            return "[" + ",".join(items) + "]"
        pad = "  " * (_level + 1)
        close = "  " * _level
        return ("[\n" + ",\n".join(pad + it for it in items)
                + "\n" + close + "]")
    if isinstance(value, dict):
        if not value:
            return "{}"
        keys = sorted(value) if sort_keys else list(value)
        pairs = [(k, format_json(value[k], compact, sort_keys, _level + 1))
                 for k in keys]
        if compact:
            return "{" + ",".join(escape_string(k) + ":" + v
                                  for k, v in pairs) + "}"
        pad = "  " * (_level + 1)
        close = "  " * _level
        return ("{\n" + ",\n".join(pad + escape_string(k) + ": " + v
                                   for k, v in pairs)
                + "\n" + close + "}")
    raise JqError("cannot format value of type %s" % type(value).__name__)

# ---------------------------------------------------------------- filter lexer

# Token: (kind, value). Kinds: DOT IDENT STRING NUMBER OP LP RP LB RB
# LC RC COLON SEMI Q EOF. OP values: | , // == != <= >= < > + - * / %

_MULTI_OPS = ("//", "==", "!=", "<=", ">=")


class FilterLexer:
    def __init__(self, text):
        self.text = text
        self.i = 0
        self.n = len(text)
        self.tokens = []
        self.tokenize()
        self.tokens.append(("EOF", None))

    def error(self, msg):
        raise FilterSyntaxError("%s at position %d" % (msg, self.i))

    def tokenize(self):
        while self.i < self.n:
            c = self.text[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif c == ".":
                self.tokens.append(("DOT", "."))
                self.i += 1
            elif c == '"':
                self.tokens.append(("STRING", self.scan_string()))
            elif c.isdigit():
                start = self.i
                while self.i < self.n and self.text[self.i].isdigit():
                    self.i += 1
                if self.i < self.n and self.text[self.i] == "." \
                        and self.i + 1 < self.n \
                        and self.text[self.i + 1].isdigit():
                    self.i += 1
                    while self.i < self.n and self.text[self.i].isdigit():
                        self.i += 1
                if self.i < self.n and self.text[self.i] in "eE":
                    j = self.i + 1
                    if j < self.n and self.text[j] in "+-":
                        j += 1
                    if j < self.n and self.text[j].isdigit():
                        self.i = j
                        while self.i < self.n and self.text[self.i].isdigit():
                            self.i += 1
                self.tokens.append(("NUMBER", self.text[start:self.i]))
            elif c.isalpha() or c == "_":
                start = self.i
                while self.i < self.n and (self.text[self.i].isalnum()
                                           or self.text[self.i] == "_"):
                    self.i += 1
                self.tokens.append(("IDENT", self.text[start:self.i]))
            elif self.text[self.i:self.i + 2] in _MULTI_OPS:
                self.tokens.append(("OP", self.text[self.i:self.i + 2]))
                self.i += 2
            elif c in "|,<>+-*/%":
                self.tokens.append(("OP", c))
                self.i += 1
            elif c == "(":
                self.tokens.append(("LP", c))
                self.i += 1
            elif c == ")":
                self.tokens.append(("RP", c))
                self.i += 1
            elif c == "[":
                self.tokens.append(("LB", c))
                self.i += 1
            elif c == "]":
                self.tokens.append(("RB", c))
                self.i += 1
            elif c == "{":
                self.tokens.append(("LC", c))
                self.i += 1
            elif c == "}":
                self.tokens.append(("RC", c))
                self.i += 1
            elif c == ":":
                self.tokens.append(("COLON", c))
                self.i += 1
            elif c == ";":
                self.tokens.append(("SEMI", c))
                self.i += 1
            elif c == "?":
                self.tokens.append(("Q", c))
                self.i += 1
            else:
                self.error("unexpected character %r" % c)

    def scan_string(self):
        # self.text[self.i] == '"'; return the raw inner text.
        self.i += 1
        raw = []
        while True:
            if self.i >= self.n:
                self.error("unterminated string in filter")
            c = self.text[self.i]
            if c == '"':
                self.i += 1
                return "".join(raw)
            if c == "\\":
                if self.i + 1 >= self.n:
                    self.error("unterminated string in filter")
                raw.append(self.text[self.i:self.i + 2])
                self.i += 2
                continue
            raw.append(c)
            self.i += 1


# ---------------------------------------------------------------- filter parser

# AST nodes are tuples whose first element names the kind; see DESIGN.md.

BARE_BUILTINS = {"length", "keys", "type", "values", "empty", "not",
                 "tostring", "tonumber"}
ALL_BUILTINS = BARE_BUILTINS | {"select", "map", "has"}


class FilterParser:
    def __init__(self, text):
        self.tokens = FilterLexer(text).tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def at_op(self, op):
        return self.peek() == ("OP", op)

    def eat_op(self, op):
        if self.at_op(op):
            self.pos += 1
            return True
        return False

    def expect(self, kind, what):
        tok = self.next()
        if tok[0] != kind:
            raise FilterSyntaxError("expected %s, got %r" % (what, tok[1]))
        return tok

    def at_ident(self, name):
        return self.peek() == ("IDENT", name)

    def parse(self):
        node = self.parse_pipe()
        if self.peek()[0] != "EOF":
            raise FilterSyntaxError("unexpected trailing input %r"
                                    % (self.peek()[1],))
        return node

    # pipe := comma ("|" comma)*   (pipe binds loosest)
    def parse_pipe(self):
        node = self.parse_comma()
        while self.eat_op("|"):
            node = ("pipe", node, self.parse_comma())
        return node

    # comma := alt ("," alt)*
    def parse_comma(self):
        node = self.parse_alt()
        while self.eat_op(","):
            node = ("comma", node, self.parse_alt())
        return node

    # alt := orexpr ("//" orexpr)*
    def parse_alt(self):
        node = self.parse_or()
        while self.eat_op("//"):
            node = ("alt", node, self.parse_or())
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.at_ident("or"):
            self.next()
            node = ("or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.at_ident("and"):
            self.next()
            node = ("and", node, self.parse_cmp())
        return node

    def parse_cmp(self):
        node = self.parse_add()
        if self.peek()[0] == "OP" and self.peek()[1] in (
                "==", "!=", "<", "<=", ">", ">="):
            op = self.next()[1]
            node = ("cmp", op, node, self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek()[0] == "OP" and self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            node = ("arith", op, node, self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek()[0] == "OP" and self.peek()[1] in ("*", "/", "%"):
            op = self.next()[1]
            node = ("arith", op, node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.eat_op("-"):
            return ("neg", self.parse_unary())
        return self.parse_postfix(self.parse_term())

    def parse_postfix(self, node):
        # Suffixes that may follow any term: .name, .[...], [...], ?
        while True:
            if self.peek()[0] == "DOT":
                save = self.pos
                self.next()
                if self.peek()[0] == "IDENT":
                    node = ("field", node, self.next()[1])
                elif self.peek()[0] == "LB":
                    node = self.parse_bracket(node)
                else:
                    self.pos = save
                    break
            elif self.peek()[0] == "LB":
                node = self.parse_bracket(node)
            elif self.peek()[0] == "Q":
                self.next()
                node = ("opt", node)
            else:
                break
        return node

    def parse_bracket(self, node):
        """Parse [...] after a term. Handles .[expr], .[], .[n:m]."""
        self.expect("LB", "'['")
        if self.peek()[0] == "RB":
            self.next()
            return ("iterate", node)
        start = None
        if self.peek()[0] != "COLON":
            start = self.parse_pipe_nocomma()
        if self.peek()[0] == "COLON":
            self.next()
            end = None
            if self.peek()[0] != "RB":
                end = self.parse_pipe_nocomma()
            self.expect("RB", "']'")
            return ("slice", node, start, end)
        self.expect("RB", "']'")
        return ("index", node, start)

    def parse_pipe_nocomma(self):
        """A pipe whose operands stop at a top-level ',' (used for
        object values and slice bounds, where ',' means something
        else)."""
        node = self.parse_alt()
        while self.eat_op("|"):
            node = ("pipe", node, self.parse_alt())
        return node

    def parse_term(self):
        kind, val = self.peek()
        if kind == "DOT":
            return self.parse_dot_term()
        if kind == "STRING":
            self.next()
            return ("string", split_interpolation(val))
        if kind == "NUMBER":
            self.next()
            lit = val
            value = float(lit) if ("." in lit or "e" in lit or "E" in lit) \
                else int(lit)
            return ("literal", JqNumber(value, lit))
        if kind == "LP":
            self.next()
            node = self.parse_pipe()
            self.expect("RP", "')'")
            return node
        if kind == "LB":
            self.next()
            if self.peek()[0] == "RB":
                self.next()
                return ("iterate", ("ident",))
            node = self.parse_pipe()
            self.expect("RB", "']'")
            return ("array", node)
        if kind == "LC":
            return self.parse_object()
        if kind == "IDENT":
            if val in ("true", "false"):
                self.next()
                return ("literal", val == "true")
            if val == "null":
                self.next()
                return ("literal", None)
            if val in ("and", "or"):
                raise FilterSyntaxError("unexpected %r" % val)
            self.next()
            if self.peek()[0] == "LP":
                self.next()
                args = [self.parse_pipe()]
                while self.peek()[0] == "SEMI":
                    self.next()
                    args.append(self.parse_pipe())
                self.expect("RP", "')'")
                if val not in ALL_BUILTINS:
                    raise FilterSyntaxError("unknown function %r" % val)
                return ("call", val, args)
            if val in BARE_BUILTINS:
                return ("call", val, [])
            raise FilterSyntaxError("unknown function or variable %r" % val)
        raise FilterSyntaxError("unexpected token %r" % (val,))

    def parse_dot_term(self):
        # self.peek() == DOT. A dot term is '.' plus at most one
        # immediate suffix (.name or [...] or nothing); the remaining
        # chain (.b, [0], ?) is handled by parse_postfix, which runs
        # over every term.
        self.next()
        node = ("ident",)
        # A following identifier is a field name -- except the keywords
        # 'and'/'or', which are operators on the identity term
        # (". and true" must not parse as field access ".and").
        if self.peek()[0] == "IDENT" and self.peek()[1] not in ("and", "or"):
            node = ("field", node, self.next()[1])
        elif self.peek()[0] == "LB":
            node = self.parse_bracket(node)
        if self.peek()[0] == "Q":
            self.next()
            node = ("opt", node)
        return node

    def parse_object(self):
        self.expect("LC", "'{'")
        entries = []
        if self.peek()[0] == "RC":
            self.next()
            return ("object", entries)
        while True:
            kind, val = self.peek()
            if kind == "STRING":
                self.next()
                key = ("keylit", val)
                self.expect("COLON", "':'")
                value = self.parse_pipe_nocomma()
            elif kind == "IDENT":
                self.next()
                if self.peek()[0] == "COLON":
                    self.next()
                    key = ("keylit", val)
                    value = self.parse_pipe_nocomma()
                elif self.peek()[0] in ("OP", "RC") \
                        and (self.peek()[0] == "RC"
                             or self.peek()[1] == ","):
                    key = ("keylit", val)
                    value = ("field", ("ident",), val)
                else:
                    raise FilterSyntaxError(
                        "expected ':' or ',' after object key %r" % val)
            elif kind == "LP":
                self.next()
                key = ("keyexpr", self.parse_pipe())
                self.expect("RP", "')'")
                self.expect("COLON", "':'")
                value = self.parse_pipe_nocomma()
            else:
                raise FilterSyntaxError("bad object key %r" % (val,))
            entries.append((key, value))
            if self.eat_op(","):
                continue
            self.expect("RC", "'}'")
            return ("object", entries)


def split_interpolation(raw):
    """Split a filter string's raw inner text into ('lit', str) and
    ('expr', AST) parts. A backslash-paren starts an interpolation;
    other backslash sequences stay in the literal text and are decoded
    with the JSON escape rules when the part is flushed."""
    parts = []
    buf = []
    i = 0
    n = len(raw)
    while i < n:
        if raw[i] == "\\" and i + 1 < n and raw[i + 1] == "(":
            # Start of interpolation: scan a balanced filter.
            if buf:
                parts.append(("lit", decode_filter_string("".join(buf))))
                buf = []
            j = i + 2
            depth = 1
            in_str = False
            while j < n and depth > 0:
                ch = raw[j]
                if in_str:
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == '"':
                        in_str = False
                    j += 1
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:
                raise FilterSyntaxError("unterminated interpolation")
            inner = raw[i + 2:j]
            parts.append(("expr", FilterParser(inner).parse()))
            i = j + 1
            continue
        if raw[i] == "\\" and i + 1 < n:
            buf.append(raw[i:i + 2])
            i += 2
            continue
        buf.append(raw[i])
        i += 1
    if buf:
        parts.append(("lit", decode_filter_string("".join(buf))))
    return parts


def decode_filter_string(raw):
    try:
        return _decode_escapes(raw, "filter string")
    except JsonError as exc:
        raise FilterSyntaxError(str(exc))


def parse_filter(text):
    return FilterParser(text).parse()

# ---------------------------------------------------------------- evaluator

def truthy(v):
    return not (v is None or v is False)


def type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, JqNumber):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    raise JqError("unknown value type %s" % type(v).__name__)


def jq_equal(a, b):
    if isinstance(a, JqNumber) and isinstance(b, JqNumber):
        return a.value == b.value
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(jq_equal(x, y)
                                        for x, y in zip(a, b))
    if isinstance(a, dict):
        return (set(a) == set(b)
                and all(jq_equal(a[k], b[k]) for k in a))
    return a == b


def order_key(v):
    """jq's total order: null < false < true < number < string <
    array < object."""
    if v is None:
        return (0,)
    if isinstance(v, bool):
        return (1, 1 if v else 0)
    if isinstance(v, JqNumber):
        return (2, float(v.value))
    if isinstance(v, str):
        return (3, v)
    if isinstance(v, list):
        return (4, tuple(order_key(x) for x in v))
    if isinstance(v, dict):
        keys = sorted(v)
        return (5, tuple(keys), tuple(order_key(v[k]) for k in keys))
    raise JqError("cannot order value of type %s" % type(v).__name__)


def describe(v):
    if isinstance(v, JqNumber):
        return "number (%s)" % v.format()
    if isinstance(v, str):
        return "string (%s)" % format_json(v, compact=True)
    return "%s (%s)" % (type_name(v), format_json(v, compact=True))


def field_access(v, name):
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get(name)
    raise JqError("cannot index %s with %s" % (describe(v),
                                                format_json(name,
                                                            compact=True)))


def index_access(v, key):
    if v is None:
        return None
    if isinstance(v, dict):
        if not isinstance(key, str):
            raise JqError("cannot index object with %s" % describe(key))
        return v.get(key)
    if isinstance(v, list):
        if not isinstance(key, JqNumber) or not float(key.value).is_integer():
            raise JqError("cannot index array with %s" % describe(key))
        idx = int(key.value)
        if idx < 0:
            idx += len(v)
        if idx < 0 or idx >= len(v):
            return None
        return v[idx]
    raise JqError("cannot index %s with %s" % (describe(v), describe(key)))


def slice_value(v, start, end):
    if v is None:
        return None
    if isinstance(v, (list, str)):
        n = len(v)
        s = 0 if start is None else int(start.value)
        e = n if end is None else int(end.value)
        if s < 0:
            s += n
        if e < 0:
            e += n
        s = max(0, min(n, s))
        e = max(0, min(n, e))
        if e < s:
            e = s
        return v[s:e]
    raise JqError("cannot slice %s" % describe(v))


def bound_value(node, val):
    """Evaluate a slice/index bound against the term's input value;
    it must be a number (or absent)."""
    if node is None:
        return None
    outs = list(ev(node, val))
    if len(outs) != 1 or not isinstance(outs[0], JqNumber):
        raise JqError("slice/index bound must be a single number")
    return outs[0]


def deep_merge(left, right):
    out = dict(left)
    for k, rv in right.items():
        if k in out and isinstance(out[k], dict) and isinstance(rv, dict):
            out[k] = deep_merge(out[k], rv)
        else:
            out[k] = rv
    return out


def arith(op, a, b):
    if op == "+":
        if a is None:
            return b
        if b is None:
            return a
        if isinstance(a, JqNumber) and isinstance(b, JqNumber):
            s = a.value + b.value
            return JqNumber(s if isinstance(s, int) else float(s))
        if isinstance(a, str) and isinstance(b, str):
            return a + b
        if isinstance(a, list) and isinstance(b, list):
            return a + b
        if isinstance(a, dict) and isinstance(b, dict):
            out = dict(a)
            out.update(b)
            return out
        raise JqError("%s and %s cannot be added"
                      % (describe(a), describe(b)))
    if op == "-":
        if isinstance(a, JqNumber) and isinstance(b, JqNumber):
            d = a.value - b.value
            return JqNumber(d if isinstance(d, int) else float(d))
        if isinstance(a, list) and isinstance(b, list):
            return [x for x in a
                    if not any(jq_equal(x, y) for y in b)]
        raise JqError("%s and %s cannot be subtracted"
                      % (describe(a), describe(b)))
    if op == "*":
        if isinstance(a, JqNumber) and isinstance(b, JqNumber):
            p = a.value * b.value
            return JqNumber(p if isinstance(p, int) else float(p))
        if isinstance(a, dict) and isinstance(b, dict):
            return deep_merge(a, b)
        if isinstance(a, str) and isinstance(b, JqNumber):
            return a * _repeat_count(b)
        if isinstance(a, JqNumber) and isinstance(b, str):
            return b * _repeat_count(a)
        raise JqError("%s and %s cannot be multiplied"
                      % (describe(a), describe(b)))
    if op == "/":
        if isinstance(a, JqNumber) and isinstance(b, JqNumber):
            if b.value == 0:
                raise JqError("division by zero")
            q = a.value / b.value
            if isinstance(a.value, int) and isinstance(b.value, int) \
                    and a.value % b.value == 0:
                return JqNumber(a.value // b.value)
            return JqNumber(float(q))
        if isinstance(a, str) and isinstance(b, str):
            return a.split(b) if b else list(a)
        raise JqError("%s and %s cannot be divided"
                      % (describe(a), describe(b)))
    if op == "%":
        if isinstance(a, JqNumber) and isinstance(b, JqNumber):
            if b.value == 0:
                raise JqError("division by zero")
            if isinstance(a.value, int) and isinstance(b.value, int):
                q = abs(a.value) // abs(b.value)
                if (a.value < 0) != (b.value < 0):
                    q = -q
                return JqNumber(a.value - q * b.value)
            return JqNumber(math.fmod(float(a.value), float(b.value)))
        raise JqError("%s and %s cannot be divided (remainder)"
                      % (describe(a), describe(b)))
    raise JqError("unknown operator %r" % op)


def _repeat_count(n):
    if not float(n.value).is_integer() or n.value < 0:
        raise JqError("string repetition count must be a non-negative "
                      "integer, got %s" % n.format())
    return int(n.value)


def ev(node, val):
    kind = node[0]
    if kind == "ident":
        yield val
    elif kind == "literal":
        yield node[1]
    elif kind == "string":
        results = [""]
        for part in node[1]:
            if part[0] == "lit":
                results = [r + part[1] for r in results]
            else:
                expanded = []
                for r in results:
                    for out in ev(part[1], val):
                        if isinstance(out, str):
                            expanded.append(r + out)
                        else:
                            expanded.append(r + format_json(out,
                                                            compact=True))
                results = expanded
        for r in results:
            yield r
    elif kind == "field":
        for v in ev(node[1], val):
            yield field_access(v, node[2])
    elif kind == "index":
        # Index expressions are evaluated against the term's input,
        # not against the indexed value (verified against system jq:
        # '{"x":[10,20],"y":1}' | '.x[.y]' gives 20).
        keys = list(ev(node[2], val))
        for v in ev(node[1], val):
            for k in keys:
                yield index_access(v, k)
    elif kind == "iterate":
        for v in ev(node[1], val):
            if isinstance(v, list):
                for x in v:
                    yield x
            elif isinstance(v, dict):
                for x in v.values():
                    yield x
            else:
                raise JqError("cannot iterate over %s" % describe(v))
    elif kind == "slice":
        start = bound_value(node[2], val) if node[2] is not None else None
        end = bound_value(node[3], val) if node[3] is not None else None
        for v in ev(node[1], val):
            yield slice_value(v, start, end)
    elif kind == "opt":
        try:
            for out in ev(node[1], val):
                yield out
        except JqError:
            return
    elif kind == "pipe":
        for v in ev(node[1], val):
            for out in ev(node[2], v):
                yield out
    elif kind == "comma":
        for out in ev(node[1], val):
            yield out
        for out in ev(node[2], val):
            yield out
    elif kind == "alt":
        good = [o for o in ev(node[1], val) if truthy(o)]
        if good:
            for o in good:
                yield o
        else:
            for out in ev(node[2], val):
                yield out
    elif kind == "and":
        for lv in ev(node[1], val):
            for rv in ev(node[2], val):
                yield truthy(lv) and truthy(rv)
    elif kind == "or":
        for lv in ev(node[1], val):
            for rv in ev(node[2], val):
                yield truthy(lv) or truthy(rv)
    elif kind == "cmp":
        op = node[1]
        for lv in ev(node[2], val):
            for rv in ev(node[3], val):
                if op == "==":
                    yield jq_equal(lv, rv)
                elif op == "!=":
                    yield not jq_equal(lv, rv)
                else:
                    lk, rk = order_key(lv), order_key(rv)
                    if op == "<":
                        yield lk < rk
                    elif op == "<=":
                        yield lk <= rk
                    elif op == ">":
                        yield lk > rk
                    else:
                        yield lk >= rk
    elif kind == "arith":
        for lv in ev(node[2], val):
            for rv in ev(node[3], val):
                yield arith(node[1], lv, rv)
    elif kind == "neg":
        for v in ev(node[1], val):
            if isinstance(v, JqNumber):
                yield JqNumber(-v.value)
            else:
                raise JqError("cannot negate %s" % describe(v))
    elif kind == "array":
        yield list(ev(node[1], val))
    elif kind == "object":
        dicts = [{}]
        for keynode, valnode in node[1]:
            new_dicts = []
            for partial in dicts:
                if keynode[0] == "keylit":
                    keys = [keynode[1]]
                else:
                    keys = []
                    for k in ev(keynode[1], val):
                        if isinstance(k, str):
                            keys.append(k)
                        elif isinstance(k, JqNumber):
                            keys.append(k.format())
                        else:
                            raise JqError("object keys must be strings")
                for k in keys:
                    for v in ev(valnode, val):
                        merged = dict(partial)
                        merged[k] = v
                        new_dicts.append(merged)
            dicts = new_dicts
        for d in dicts:
            yield d
    elif kind == "call":
        for out in call_builtin(node[1], node[2], val):
            yield out
    else:
        raise JqError("unknown filter node %r" % (kind,))


def call_builtin(name, args, val):
    if name == "select":
        outs = list(ev(args[0], val))
        if any(truthy(o) for o in outs):
            yield val
    elif name == "map":
        if not isinstance(val, list):
            raise JqError("cannot iterate over %s" % describe(val))
        out = []
        for elem in val:
            out.extend(ev(args[0], elem))
        yield out
    elif name == "length":
        if val is None:
            yield JqNumber(0)
        elif isinstance(val, JqNumber):
            yield JqNumber(abs(val.value))
        elif isinstance(val, (str, list)):
            yield JqNumber(len(val))
        elif isinstance(val, dict):
            yield JqNumber(len(val))
        elif isinstance(val, bool):
            raise JqError("boolean has no length")
        else:
            raise JqError("%s has no length" % describe(val))
    elif name == "keys":
        if isinstance(val, dict):
            yield sorted(val)
        elif isinstance(val, list):
            yield [JqNumber(i) for i in range(len(val))]
        else:
            raise JqError("%s has no keys" % describe(val))
    elif name == "type":
        yield type_name(val)
    elif name == "values":
        if val is None:
            return
        if isinstance(val, dict):
            for x in val.values():
                yield x
        elif isinstance(val, list):
            for x in val:
                yield x
        else:
            yield val
    elif name == "empty":
        return
    elif name == "not":
        yield not truthy(val)
    elif name == "has":
        for k in ev(args[0], val):
            if isinstance(val, dict):
                yield isinstance(k, str) and k in val
            elif isinstance(val, list):
                yield (isinstance(k, JqNumber)
                       and float(k.value).is_integer()
                       and 0 <= int(k.value) < len(val))
            else:
                raise JqError("%s has no keys" % describe(val))
    elif name == "tostring":
        if isinstance(val, str):
            yield val
        else:
            yield format_json(val, compact=True)
    elif name == "tonumber":
        if isinstance(val, JqNumber):
            yield val
        elif isinstance(val, str):
            try:
                docs = parse_json_stream(val)
            except JsonError:
                docs = []
            if len(docs) == 1 and isinstance(docs[0], JqNumber):
                yield docs[0]
            else:
                raise JqError("invalid number literal %r" % val)
        else:
            raise JqError("cannot convert %s to a number" % describe(val))
    else:
        raise JqError("unknown builtin %r" % name)


# ---------------------------------------------------------------- CLI

USAGE = """usage: jq.py [-c] [-r] [--sort-keys] [filter] [file ...]
  No filter means '.'. No files means read stdin.
  -c          compact output (one value per line)
  -r          raw output (strings without quotes)
  --sort-keys sort object keys on output
  -h, --help  show this message"""


def main(argv):
    compact = False
    raw = False
    sort_keys = False
    rest = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            rest.extend(argv[i + 1:])
            break
        if arg == "--sort-keys":
            sort_keys = True
        elif arg in ("-h", "--help"):
            print(USAGE)
            return 0
        elif arg.startswith("-") and len(arg) > 1 and arg != "-":
            for ch in arg[1:]:
                if ch == "c":
                    compact = True
                elif ch == "r":
                    raw = True
                else:
                    print("jq.py: unknown option -%s" % ch, file=sys.stderr)
                    print(USAGE, file=sys.stderr)
                    return 3
        else:
            rest.append(arg)
        i += 1

    filter_text = rest[0] if rest else "."
    files = rest[1:]
    try:
        program = parse_filter(filter_text)
    except FilterSyntaxError as exc:
        print("jq.py: filter error: %s" % exc, file=sys.stderr)
        return 3

    texts = []
    if not files:
        texts.append(sys.stdin.read())
    else:
        for path in files:
            try:
                with open(path, encoding="utf-8") as fh:
                    texts.append(fh.read())
            except OSError as exc:
                print("jq.py: %s" % exc, file=sys.stderr)
                return 2

    out = sys.stdout
    try:
        for text in texts:
            try:
                docs = parse_json_stream(text)
            except JsonError as exc:
                print("jq.py: JSON error: %s" % exc, file=sys.stderr)
                return 5
            for doc in docs:
                try:
                    outputs = list(ev(program, doc))
                except JqError as exc:
                    print("jq.py: error: %s" % exc, file=sys.stderr)
                    return 5
                for value in outputs:
                    if raw and isinstance(value, str):
                        out.write(value + "\n")
                    else:
                        out.write(format_json(value, compact=compact,
                                              sort_keys=sort_keys) + "\n")
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

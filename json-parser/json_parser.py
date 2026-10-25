#!/usr/bin/env python3
"""json-parser - Build Your Own JSON Parser (Coding Challenges #2).

Usage: json_parser.py [file.json]
  No file: read stdin. Valid input prints "Valid JSON" and exits 0.
  Invalid input prints an error to stderr and exits 1.

Hand-written lexer + recursive-descent parser. Python standard
library only, and deliberately NOT the json module - using it
would be the whole challenge. See docs/SPEC.md for the grammar
and docs/DESIGN.md for the algorithm.
"""

import sys

ESCAPES = {
    '"': '"', "\\": "\\", "/": "/",
    "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
}
WHITESPACE = " \t\n\r"


class JsonError(Exception):
    """Parse error with a character offset into the input text."""

    def __init__(self, message, offset):
        super().__init__(message)
        self.message = message
        self.offset = offset


class Token:
    def __init__(self, kind, value, offset):
        self.kind = kind
        self.value = value
        self.offset = offset

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r})"


# Token kinds: LBRACE RBRACE LBRACKET RBRACKET COLON COMMA
#                STRING NUMBER TRUE FALSE NULL EOF


class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def tokenize(self):
        tokens = []
        while True:
            self._skip_whitespace()
            if self.pos >= self.length:
                tokens.append(Token("EOF", None, self.pos))
                return tokens
            start = self.pos
            char = self.text[self.pos]
            if char in "{}[],:":
                kind = {"{": "LBRACE", "}": "RBRACE",
                        "[": "LBRACKET", "]": "RBRACKET",
                        ":": "COLON", ",": "COMMA"}[char]
                tokens.append(Token(kind, char, start))
                self.pos += 1
            elif char == '"':
                tokens.append(Token("STRING", self._read_string(), start))
            elif char == "-" or char.isdigit():
                tokens.append(Token("NUMBER", self._read_number(), start))
            elif char.isalpha():
                tokens.append(self._read_literal())
            else:
                raise JsonError(f"unexpected character {char!r}", start)

    def _skip_whitespace(self):
        while self.pos < self.length and self.text[self.pos] in WHITESPACE:
            self.pos += 1

    def _read_string(self):
        # self.text[self.pos] is the opening quote.
        self.pos += 1
        out = []
        while True:
            if self.pos >= self.length:
                raise JsonError("unterminated string", self.pos)
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                return "".join(out)
            if ord(char) < 0x20:
                raise JsonError("unescaped control character in string",
                                self.pos)
            if char == "\\":
                self.pos += 1
                if self.pos >= self.length:
                    raise JsonError("unterminated escape in string",
                                    self.pos)
                esc = self.text[self.pos]
                if esc == "u":
                    out.append(self._read_unicode_escape())
                elif esc in ESCAPES:
                    out.append(ESCAPES[esc])
                    self.pos += 1
                else:
                    raise JsonError(f"invalid escape '\\{esc}'", self.pos)
            else:
                out.append(char)
                self.pos += 1

    def _read_unicode_escape(self):
        # self.text[self.pos] is 'u'; caller already consumed the backslash.
        start = self.pos - 1  # position of the backslash
        code = self._read_hex4(self.pos + 1)
        self.pos += 5  # 'u' + 4 hex digits
        if 0xD800 <= code <= 0xDBFF:
            # High surrogate: a low surrogate must follow immediately.
            if self.text[self.pos:self.pos + 2] != "\\u":
                raise JsonError("lone high surrogate in string", start)
            low = self._read_hex4(self.pos + 2)
            if not 0xDC00 <= low <= 0xDFFF:
                raise JsonError("invalid low surrogate in string", start)
            self.pos += 6  # backslash, 'u', 4 hex digits
            return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00))
        if 0xDC00 <= code <= 0xDFFF:
            raise JsonError("lone low surrogate in string", start)
        return chr(code)

    def _read_hex4(self, start):
        digits = self.text[start:start + 4]
        if len(digits) != 4 or any(c not in "0123456789abcdefABCDEF"
                                   for c in digits):
            raise JsonError("invalid unicode escape", start - 1)
        return int(digits, 16)

    def _read_number(self):
        start = self.pos
        if self.text[self.pos] == "-":
            self.pos += 1
            if self.pos >= self.length or not self.text[self.pos].isdigit():
                raise JsonError("invalid number", start)
        # Integer part: '0' alone, or non-zero digit followed by digits.
        if self.text[self.pos] == "0":
            self.pos += 1
            if self.pos < self.length and self.text[self.pos].isdigit():
                raise JsonError("leading zero in number", start)
        else:
            while self.pos < self.length and self.text[self.pos].isdigit():
                self.pos += 1
        is_float = False
        if self.pos < self.length and self.text[self.pos] == ".":
            is_float = True
            self.pos += 1
            if self.pos >= self.length or not self.text[self.pos].isdigit():
                raise JsonError("missing digits after decimal point", start)
            while self.pos < self.length and self.text[self.pos].isdigit():
                self.pos += 1
        if self.pos < self.length and self.text[self.pos] in "eE":
            is_float = True
            self.pos += 1
            if self.pos < self.length and self.text[self.pos] in "+-":
                self.pos += 1
            if self.pos >= self.length or not self.text[self.pos].isdigit():
                raise JsonError("missing digits in exponent", start)
            while self.pos < self.length and self.text[self.pos].isdigit():
                self.pos += 1
        raw = self.text[start:self.pos]
        return float(raw) if is_float else int(raw)

    def _read_literal(self):
        start = self.pos
        while self.pos < self.length and self.text[self.pos].isalpha():
            self.pos += 1
        word = self.text[start:self.pos]
        if word == "true":
            return Token("TRUE", True, start)
        if word == "false":
            return Token("FALSE", False, start)
        if word == "null":
            return Token("NULL", None, start)
        raise JsonError(f"invalid literal {word!r}", start)


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos]

    def _advance(self):
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _expect(self, kind):
        token = self._peek()
        if token.kind != kind:
            raise JsonError(f"expected {kind}, found {token.kind}",
                            token.offset)
        return self._advance()

    def parse(self):
        value = self.parse_value()
        token = self._peek()
        if token.kind != "EOF":
            raise JsonError("trailing characters after top-level value",
                            token.offset)
        return value

    def parse_value(self):
        token = self._peek()
        if token.kind == "LBRACE":
            return self.parse_object()
        if token.kind == "LBRACKET":
            return self.parse_array()
        if token.kind in ("STRING", "NUMBER", "TRUE", "FALSE", "NULL"):
            return self._advance().value
        raise JsonError(f"unexpected token {token.kind}", token.offset)

    def parse_object(self):
        self._expect("LBRACE")
        result = {}
        if self._peek().kind == "RBRACE":
            self._advance()
            return result
        while True:
            key = self._expect("STRING")
            self._expect("COLON")
            result[key.value] = self.parse_value()
            if self._peek().kind == "COMMA":
                self._advance()
                continue
            self._expect("RBRACE")
            return result

    def parse_array(self):
        self._expect("LBRACKET")
        result = []
        if self._peek().kind == "RBRACKET":
            self._advance()
            return result
        while True:
            result.append(self.parse_value())
            if self._peek().kind == "COMMA":
                self._advance()
                continue
            self._expect("RBRACKET")
            return result


def parse(text):
    """Parse JSON text, returning the Python value, or raise JsonError."""
    return Parser(Lexer(text).tokenize()).parse()


def line_col(text, offset):
    """Convert a character offset to (line, column), both 1-based."""
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def main(argv):
    if len(argv) > 1:
        print("usage: json_parser.py [file.json]", file=sys.stderr)
        return 2
    try:
        if argv:
            with open(argv[0], "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()
    except OSError as exc:
        print(f"json_parser: {exc.strerror}", file=sys.stderr)
        return 1
    try:
        parse(text)
    except JsonError as exc:
        line, col = line_col(text, exc.offset)
        print(f"Invalid JSON: {exc.message} at line {line}, column {col}",
              file=sys.stderr)
        return 1
    print("Valid JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

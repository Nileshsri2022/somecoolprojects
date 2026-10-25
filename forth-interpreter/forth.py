#!/usr/bin/env python3
"""A small Forth-like interpreter (codingchallenges.fyi, challenge-forth).

Python 3 standard library only. See docs/SPEC.md for the word list
and documented divergences from the challenge page.

Usage:
    python3 forth.py            # REPL (prompt: ok>, bye to quit)
    python3 forth.py prog.forth # run a script file
    python3 forth.py -          # run a script from stdin, no prompts

Programmatic use:
    interp = Interpreter()
    interp.run("1 2 + .")       # output goes to interp.out (a StringIO
                                # by default); interp.stack holds the
                                # data stack afterwards.
"""

import io
import re
import sys

_INT_RE = re.compile(r"-?[0-9]+$")
_CLOSERS = {"then", "else", "loop", ";"}
_CONTROL = {"if", "then", "else", "do", "loop", "bye", ":", ";"}
_BUILTINS = {
    "+", "-", "*", "/", "mod",
    "dup", "drop", "swap", "over", "rot",
    ".", "emit", "cr",
    "<", ">", "=", "<>", "and", "or", "invert",
    "i",
}
_RESERVED = _BUILTINS | _CONTROL


class ForthError(Exception):
    """Any error in a Forth program (underflow, div by zero, bad syntax)."""


class StopExecution(Exception):
    """Raised by `bye`; a clean stop, not an error."""


# Tokens are ("num", int), ("str", str) or ("word", lowercase str).
def tokenize(source):
    """Split source into tokens, skipping ( ... ) comments and
    capturing ." ..." string literals. Raises ForthError on an
    unterminated comment or string."""
    tokens = []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
        elif c == "(":
            j = source.find(")", i + 1)
            if j < 0:
                raise ForthError("unterminated comment")
            i = j + 1
        elif source.startswith('."', i):
            i += 2
            if i < n and source[i] == " ":
                i += 1
            j = source.find('"', i)
            if j < 0:
                raise ForthError('unterminated string literal (missing ")')
            tokens.append(("str", source[i:j]))
            i = j + 1
        else:
            j = i
            while j < n and not source[j].isspace():
                j += 1
            text = source[i:j]
            if _INT_RE.match(text):
                tokens.append(("num", int(text)))
            else:
                tokens.append(("word", text.lower()))
            i = j
    return tokens


class Parser:
    """Turns a flat token list into a list of nodes, recording
    `: name ... ;` definitions in `words` as it goes.

    Nodes: ("push", int), ("print-str", str), ("word", name),
    ("bye",), ("if", then_nodes, else_nodes), ("do", body_nodes).
    """

    def __init__(self, tokens, words):
        self.tokens = tokens
        self.pos = 0
        self.words = words

    def parse_program(self):
        nodes = self._parse_seq(stop=set(), allow_def=True)
        if self.pos < len(self.tokens):
            raise ForthError("unexpected %s" % self._peek_word())
        return nodes

    def _peek_word(self):
        kind, value = self.tokens[self.pos]
        return value if kind == "word" else repr(value)

    def _parse_seq(self, stop, allow_def):
        nodes = []
        while self.pos < len(self.tokens):
            kind, value = self.tokens[self.pos]
            if kind == "num":
                nodes.append(("push", value))
                self.pos += 1
            elif kind == "str":
                nodes.append(("print-str", value))
                self.pos += 1
            elif value in stop:
                break
            elif value in _CLOSERS:
                raise ForthError("unexpected %s" % value)
            elif value == ":":
                if not allow_def:
                    raise ForthError(
                        "word definition inside another word is not supported")
                self.pos += 1
                if self.pos >= len(self.tokens):
                    raise ForthError("definition without a name")
                name_kind, name = self.tokens[self.pos]
                if name_kind != "word" or name in _RESERVED:
                    raise ForthError("bad definition name %r" % (name,))
                self.pos += 1
                body = self._parse_seq(stop={";"}, allow_def=False)
                if self.pos >= len(self.tokens):
                    raise ForthError("unterminated definition of %s" % name)
                self.pos += 1  # consume ";"
                self.words[name] = body
            elif value == "if":
                self.pos += 1
                then_nodes = self._parse_seq(stop={"else", "then"},
                                             allow_def=False)
                if self.pos >= len(self.tokens):
                    raise ForthError("unterminated if (missing then)")
                if self.tokens[self.pos][1] == "else":
                    self.pos += 1
                    else_nodes = self._parse_seq(stop={"then"},
                                                 allow_def=False)
                    if self.pos >= len(self.tokens):
                        raise ForthError("unterminated if (missing then)")
                else:
                    else_nodes = []
                self.pos += 1  # consume "then"
                nodes.append(("if", then_nodes, else_nodes))
            elif value == "do":
                self.pos += 1
                body = self._parse_seq(stop={"loop"}, allow_def=False)
                if self.pos >= len(self.tokens):
                    raise ForthError("unterminated do (missing loop)")
                self.pos += 1  # consume "loop"
                nodes.append(("do", body))
            elif value == "bye":
                nodes.append(("bye",))
                self.pos += 1
            else:
                nodes.append(("word", value))
                self.pos += 1
        return nodes


def _trunc_div(a, b):
    """Quotient truncated toward zero (standard Forth, not //)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class Interpreter:
    def __init__(self, out=None):
        self.stack = []
        self.words = {}
        self.loop_stack = []  # each frame: [index, limit]
        self.out = out if out is not None else io.StringIO()

    def output_text(self):
        """Captured output when the default StringIO is in use."""
        if isinstance(self.out, io.StringIO):
            return self.out.getvalue()
        return ""

    def run(self, source):
        """Parse and execute one chunk of source (a line or a file).
        Unknown words print "<word> ?" and continue; other problems
        raise ForthError; `bye` raises StopExecution."""
        nodes = Parser(tokenize(source), self.words).parse_program()
        self._exec(nodes)

    # -- stack helpers -------------------------------------------------
    def _pop(self):
        if not self.stack:
            raise ForthError("stack underflow")
        return self.stack.pop()

    def _need(self, count):
        if len(self.stack) < count:
            raise ForthError("stack underflow")

    # -- execution -----------------------------------------------------
    def _exec(self, nodes):
        for node in nodes:
            kind = node[0]
            if kind == "push":
                self.stack.append(node[1])
            elif kind == "print-str":
                self.out.write(node[1])
            elif kind == "bye":
                raise StopExecution
            elif kind == "if":
                flag = self._pop()
                self._exec(node[1] if flag != 0 else node[2])
            elif kind == "do":
                start = self._pop()
                limit = self._pop()
                frame = [start, limit]
                self.loop_stack.append(frame)
                try:
                    while frame[0] < frame[1]:
                        self._exec(node[1])
                        frame[0] += 1
                finally:
                    self.loop_stack.pop()
            else:  # ("word", name)
                self._exec_word(node[1])

    def _exec_word(self, name):
        if name in _BUILTINS:
            self._builtin(name)
        elif name in self.words:
            self._exec(self.words[name])
        else:
            self.out.write("%s ?\n" % name)

    def _builtin(self, name):
        if name == "i":
            if not self.loop_stack:
                raise ForthError("i used outside a do loop")
            self.stack.append(self.loop_stack[-1][0])
            return
        if name == "cr":
            self.out.write("\n")
            return
        if name == ".":
            self.out.write("%d " % self._pop())
            return
        if name == "emit":
            self.out.write(chr(self._pop() & 0xFF))
            return
        if name == "dup":
            self._need(1)
            self.stack.append(self.stack[-1])
            return
        if name == "drop":
            self._pop()
            return
        if name == "invert":
            self.stack.append(~self._pop())
            return
        self._need(2)
        b = self._pop()
        a = self._pop()
        if name == "+":
            self.stack.append(a + b)
        elif name == "-":
            self.stack.append(a - b)
        elif name == "*":
            self.stack.append(a * b)
        elif name == "/":
            if b == 0:
                raise ForthError("division by zero")
            self.stack.append(_trunc_div(a, b))
        elif name == "mod":
            if b == 0:
                raise ForthError("division by zero")
            self.stack.append(a - _trunc_div(a, b) * b)
        elif name == "swap":
            self.stack.append(b)
            self.stack.append(a)
        elif name == "over":
            self.stack.append(a)
            self.stack.append(b)
            self.stack.append(a)
        elif name == "rot":
            # ( x y z -- y z x ): a, b above are y, z; pop x too.
            self._need(1)
            x = self._pop()
            self.stack.append(a)
            self.stack.append(b)
            self.stack.append(x)
        elif name == "<":
            self.stack.append(-1 if a < b else 0)
        elif name == ">":
            self.stack.append(-1 if a > b else 0)
        elif name == "=":
            self.stack.append(-1 if a == b else 0)
        elif name == "<>":
            self.stack.append(-1 if a != b else 0)
        elif name == "and":
            self.stack.append(a & b)
        elif name == "or":
            self.stack.append(a | b)
        else:  # pragma: no cover - _BUILTINS guards this
            raise ForthError("unknown builtin %s" % name)


def repl(interp, inp, out):
    """Read-Eval-Print Loop. Returns on `bye` or EOF."""
    while True:
        stack_str = " ".join(str(v) for v in interp.stack)
        prompt = ("%s ok> " % stack_str) if stack_str else "ok> "
        out.write(prompt)
        out.flush()
        line = inp.readline()
        if line == "":
            break
        if not _is_tty(inp):
            out.write("\n")  # simulate terminal echo of the input line
        if line.strip().lower() == "bye":
            break
        try:
            interp.run(line)
        except StopExecution:
            break
        except ForthError as exc:
            out.write("error: %s\n" % exc)


def _is_tty(stream):
    try:
        return stream.isatty()
    except Exception:
        return False


def main(argv):
    if len(argv) > 2:
        print("usage: forth.py [file | -]", file=sys.stderr)
        return 2
    if len(argv) == 2 and argv[1] != "-":
        try:
            with open(argv[1], "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
        interp = Interpreter(out=sys.stdout)
        try:
            interp.run(source)
        except StopExecution:
            pass
        except ForthError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
        return 0
    if len(argv) == 2:  # "-" : script from stdin, no prompts
        interp = Interpreter(out=sys.stdout)
        try:
            interp.run(sys.stdin.read())
        except StopExecution:
            pass
        except ForthError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 1
        return 0
    repl(Interpreter(out=sys.stdout), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

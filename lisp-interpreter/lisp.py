#!/usr/bin/env python3
"""A small Lisp interpreter (Coding Challenges: challenge-lisp).

Pipeline: tokenize -> parse (S-expressions) -> evaluate against a
lexically scoped environment chain. Standard library only.

See docs/SPEC.md, docs/DESIGN.md for the spec and assumptions.
"""

import re
import sys


class LispError(Exception):
    """Any user-facing Lisp error (unbound symbol, bad call, ...)."""


class Symbol:
    """A Lisp symbol. Distinct from a Python str (a string atom)."""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Symbol) and self.name == other.name

    def __hash__(self):
        return hash(self.name)


# ---------------------------------------------------------------- tokenizer

def tokenize(source):
    """Return a flat list of raw token strings for *source*.

    Tokens are '(', ')', "'", string tokens (quotes included) and
    bare atoms. ';' comments run to end of line and are dropped.
    """
    tokens = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif ch == ";":
            while i < n and source[i] != "\n":
                i += 1
        elif ch in "()'":
            tokens.append(ch)
            i += 1
        elif ch == '"':
            j = i + 1
            while j < n and source[j] != '"':
                if source[j] == "\\":
                    j += 2
                else:
                    j += 1
            if j >= n:
                raise LispError("unterminated string")
            tokens.append(source[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and (not source[j].isspace()
                             and source[j] not in "()'\";"):
                j += 1
            tokens.append(source[i:j])
            i = j
    return tokens


# ------------------------------------------------------------------- parser

_INT_RE = re.compile(r"-?\d+$")
_FLOAT_RE = re.compile(r"-?\d+\.\d*|-?\.\d+$")
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


def _unescape(raw):
    """Turn a quoted token (quotes included) into a Python str."""
    out = []
    i = 1  # skip opening quote
    while i < len(raw) - 1:  # skip closing quote
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw) - 1:
            out.append(_ESCAPES.get(raw[i + 1], raw[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _atom(token):
    if token.startswith('"'):
        return _unescape(token)
    if _INT_RE.match(token):
        return int(token)
    if _FLOAT_RE.match(token):
        return float(token)
    if token.upper() == "NIL":
        return None
    if token.upper() == "T":
        return True
    return Symbol(token.upper())


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def parse_expr(self):
        if self.pos >= len(self.tokens):
            raise LispError("unexpected end of input")
        token = self.tokens[self.pos]
        self.pos += 1
        if token == "(":
            if self.pos < len(self.tokens) and self.tokens[self.pos] == ")":
                self.pos += 1
                return None  # () is nil
            items = []
            while True:
                if self.pos >= len(self.tokens):
                    raise LispError("unbalanced parentheses")
                if self.tokens[self.pos] == ")":
                    self.pos += 1
                    return items
                items.append(self.parse_expr())
        if token == ")":
            raise LispError("unexpected ')'")
        if token == "'":
            return [Symbol("QUOTE"), self.parse_expr()]
        return _atom(token)


def parse(source):
    """Parse exactly one form; error on trailing or missing input."""
    parser = _Parser(tokenize(source))
    if parser.pos >= len(parser.tokens):
        raise LispError("empty input")
    expr = parser.parse_expr()
    if parser.pos != len(parser.tokens):
        raise LispError("trailing input after expression")
    return expr


def parse_all(source):
    """Parse every form in *source*, returning a list of ASTs."""
    parser = _Parser(tokenize(source))
    exprs = []
    while parser.pos < len(parser.tokens):
        exprs.append(parser.parse_expr())
    return exprs


# --------------------------------------------------------------------- env

class Env:
    """A mapping from symbol name to value, with a parent chain."""

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def define(self, name, value):
        self.vars[name] = value

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise LispError("unbound symbol: %s" % name)

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return value
            env = env.parent
        raise LispError("cannot set! unbound symbol: %s" % name)


class LispFunction:
    """A user-defined function: params, body forms, captured env."""

    def __init__(self, params, body, env, name=None):
        self.params = params
        self.body = body
        self.env = env
        self.name = name


class Builtin:
    def __init__(self, name, func):
        self.name = name
        self.func = func


# ------------------------------------------------------------------ printing

def format_value(value):
    """The single Lisp representation (REPL output and ~S)."""
    if value is None or value is False:
        return "NIL"
    if value is True:
        return "T"
    if isinstance(value, Symbol):
        return value.name
    if isinstance(value, str):
        escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
                   .replace("\n", "\\n").replace("\t", "\\t"))
        return '"%s"' % escaped
    if isinstance(value, list):
        return "(" + " ".join(format_value(v) for v in value) + ")"
    if isinstance(value, LispFunction):
        return "#<FUNCTION %s>" % (value.name or "LAMBDA")
    if isinstance(value, Builtin):
        return "#<BUILTIN %s>" % value.name
    return str(value)


def _aesthetic(value):
    """~A / ~D rendering: strings raw, everything else as printed."""
    if isinstance(value, str):
        return value
    return format_value(value)


# ------------------------------------------------------------------ builtins

def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numbers(args, name):
    for arg in args:
        if not _is_number(arg):
            raise LispError("%s: expected a number, got %s"
                            % (name, format_value(arg)))
    return args


def _int_if_integral(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _builtin_add(args):
    return sum(_numbers(args, "+"))


def _builtin_sub(args):
    _numbers(args, "-")
    if not args:
        raise LispError("-: expected at least one argument")
    if len(args) == 1:
        return -args[0]
    result = args[0]
    for arg in args[1:]:
        result -= arg
    return result


def _builtin_mul(args):
    result = 1
    for arg in _numbers(args, "*"):
        result *= arg
    return result


def _builtin_div(args):
    _numbers(args, "/")
    if not args:
        raise LispError("/: expected at least one argument")
    if len(args) == 1:
        if args[0] == 0:
            raise LispError("/: division by zero")
        return _int_if_integral(1 / args[0])
    result = args[0]
    for arg in args[1:]:
        if arg == 0:
            raise LispError("/: division by zero")
        result /= arg
    return _int_if_integral(result)


def _builtin_mod(args):
    if len(args) != 2:
        raise LispError("mod: expected 2 arguments, got %d" % len(args))
    _numbers(args, "mod")
    if args[1] == 0:
        raise LispError("mod: division by zero")
    return args[0] % args[1]


def _comparison(args, name, op):
    _numbers(args, name)
    if len(args) < 2:
        raise LispError("%s: expected at least 2 arguments" % name)
    return all(op(args[i], args[i + 1]) for i in range(len(args) - 1))


def _builtin_eq(args):
    if len(args) < 2:
        raise LispError("=: expected at least 2 arguments")
    return all(arg == args[0] for arg in args[1:])


def _list_arg(value, name):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise LispError("%s: expected a list, got %s"
                    % (name, format_value(value)))


def _builtin_list(args):
    return list(args) if args else None


def _builtin_cons(args):
    if len(args) != 2:
        raise LispError("cons: expected 2 arguments, got %d" % len(args))
    return [args[0]] + _list_arg(args[1], "cons")


def _builtin_car(args):
    if len(args) != 1:
        raise LispError("car: expected 1 argument, got %d" % len(args))
    items = _list_arg(args[0], "car")
    return items[0] if items else None


def _builtin_cdr(args):
    if len(args) != 1:
        raise LispError("cdr: expected 1 argument, got %d" % len(args))
    items = _list_arg(args[0], "cdr")
    return items[1:] if len(items) > 1 else None


def _builtin_append(args):
    out = []
    for arg in args:
        out.extend(_list_arg(arg, "append"))
    return out if out else None


def _builtin_length(args):
    if len(args) != 1:
        raise LispError("length: expected 1 argument, got %d" % len(args))
    value = args[0]
    if isinstance(value, str):
        return len(value)
    return len(_list_arg(value, "length"))


def _builtin_null(args):
    if len(args) != 1:
        raise LispError("null?: expected 1 argument, got %d" % len(args))
    return args[0] is None


def _predicate(args, name, check):
    if len(args) != 1:
        raise LispError("%s: expected 1 argument, got %d" % (name, len(args)))
    return check(args[0])


def _builtin_format(args):
    if len(args) < 2:
        raise LispError("format: expected destination and format string")
    dest, fmt = args[0], args[1]
    if not isinstance(fmt, str):
        raise LispError("format: format string must be a string")
    values = list(args[2:])
    out = []
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch != "~":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(fmt):
            raise LispError("format: trailing '~' in format string")
        directive = fmt[i + 1]
        i += 2
        if directive == "%":
            out.append("\n")
        elif directive == "~":
            out.append("~")
        elif directive in ("D", "A", "S"):
            if not values:
                raise LispError("format: no argument for ~%s" % directive)
            value = values.pop(0)
            out.append(format_value(value) if directive == "S"
                       else _aesthetic(value))
        else:
            raise LispError("format: unknown directive ~%s" % directive)
    text = "".join(out)
    if dest is True:
        sys.stdout.write(text)
        return None
    if dest is None:
        return text
    raise LispError("format: destination must be t or nil")


def _make_builtins():
    import operator

    def one_arg(name, func):
        def wrapper(args):
            if len(args) != 1:
                raise LispError("%s: expected 1 argument, got %d"
                                % (name, len(args)))
            return func(args[0])
        return wrapper

    raw = {
        "+": _builtin_add,
        "-": _builtin_sub,
        "*": _builtin_mul,
        "/": _builtin_div,
        "MOD": _builtin_mod,
        "=": _builtin_eq,
        "<": lambda a: _comparison(a, "<", operator.lt),
        ">": lambda a: _comparison(a, ">", operator.gt),
        "<=": lambda a: _comparison(a, "<=", operator.le),
        ">=": lambda a: _comparison(a, ">=", operator.ge),
        "LIST": _builtin_list,
        "CONS": _builtin_cons,
        "CAR": _builtin_car,
        "CDR": _builtin_cdr,
        "APPEND": _builtin_append,
        "LENGTH": _builtin_length,
        "NULL?": _builtin_null,
        "NULL": _builtin_null,
        "NOT": one_arg("not", lambda v: v is None or v is False),
        "NUMBER?": lambda a: _predicate(a, "number?", _is_number),
        "STRING?": lambda a: _predicate(a, "string?",
                                        lambda v: isinstance(v, str)),
        "SYMBOL?": lambda a: _predicate(a, "symbol?",
                                        lambda v: isinstance(v, Symbol)),
        "LIST?": lambda a: _predicate(a, "list?",
                                      lambda v: v is None
                                      or isinstance(v, list)),
        "ATOM?": lambda a: _predicate(a, "atom?",
                                      lambda v: not isinstance(v, list)),
        "FORMAT": _builtin_format,
    }
    return {name: Builtin(name, func) for name, func in raw.items()}


def standard_env():
    """A fresh global environment preloaded with the builtins."""
    env = Env()
    for name, builtin in _make_builtins().items():
        env.define(name, builtin)
    return env


# ---------------------------------------------------------------- evaluator

SPECIAL_FORMS = ("QUOTE", "IF", "DEFINE", "DEFUN", "LAMBDA",
                 "LET", "LET*", "SET!", "BEGIN")


def _is_truthy(value):
    return value is not None and value is not False


def _params(form, what):
    if form is None:
        return []
    if not isinstance(form, list):
        raise LispError("%s: parameter list must be a list" % what)
    names = []
    for item in form:
        if not isinstance(item, Symbol):
            raise LispError("%s: parameter must be a symbol" % what)
        names.append(item.name)
    return names


def _check_body(body, what):
    if not body:
        raise LispError("%s: expected at least one body form" % what)
    return body


def _eval_body(body, env):
    result = None
    for form in body:
        result = evaluate(form, env)
    return result


def _parse_bindings(form, what):
    if form is None:
        return []
    if not isinstance(form, list):
        raise LispError("%s: bindings must be a list" % what)
    bindings = []
    for item in form:
        if (not isinstance(item, list)) or len(item) != 2 \
                or not isinstance(item[0], Symbol):
            raise LispError("%s: bad binding %s"
                            % (what, format_value(item)))
        bindings.append((item[0].name, item[1]))
    return bindings


def _eval_special(head, expr, env):
    args = expr[1:]
    if head == "QUOTE":
        if len(args) != 1:
            raise LispError("quote: expected 1 argument")
        return args[0]
    if head == "IF":
        if len(args) not in (2, 3):
            raise LispError("if: expected 2 or 3 arguments")
        if _is_truthy(evaluate(args[0], env)):
            return evaluate(args[1], env)
        return evaluate(args[2], env) if len(args) == 3 else None
    if head == "DEFINE":
        if len(args) < 2:
            raise LispError("define: expected a name and a value")
        target = args[0]
        if isinstance(target, Symbol):
            value = evaluate(args[1], env)
            if len(args) != 2:
                raise LispError("define: expected exactly 2 arguments")
            env.define(target.name, value)
            return target
        if isinstance(target, list) and target \
                and isinstance(target[0], Symbol):
            func = LispFunction(_params(target[1:], "define"),
                                _check_body(args[1:], "define"),
                                env, name=target[0].name)
            env.define(target[0].name, func)
            return target[0]
        raise LispError("define: bad definition target")
    if head == "DEFUN":
        if len(args) < 3 or not isinstance(args[0], Symbol):
            raise LispError("defun: expected (defun name (params) body...)")
        func = LispFunction(_params(args[1], "defun"),
                            _check_body(args[2:], "defun"),
                            env, name=args[0].name)
        env.define(args[0].name, func)
        return args[0]
    if head == "LAMBDA":
        if len(args) < 2:
            raise LispError("lambda: expected (lambda (params) body...)")
        return LispFunction(_params(args[0], "lambda"),
                            _check_body(args[1:], "lambda"), env)
    if head in ("LET", "LET*"):
        if len(args) < 2:
            raise LispError("%s: expected bindings and a body" % head)
        bindings = _parse_bindings(args[0], head.lower())
        child = Env(parent=env)
        if head == "LET":
            values = [evaluate(value, env) for _, value in bindings]
            for (name, _), value in zip(bindings, values):
                child.define(name, value)
        else:
            for name, value in bindings:
                child.define(name, evaluate(value, child))
        return _eval_body(args[1:], child)
    if head == "SET!":
        if len(args) != 2 or not isinstance(args[0], Symbol):
            raise LispError("set!: expected (set! name value)")
        return env.set(args[0].name, evaluate(args[1], env))
    if head == "BEGIN":
        return _eval_body(args, env)
    raise LispError("unknown special form: %s" % head)  # unreachable


def apply(proc, args):
    if isinstance(proc, Builtin):
        return proc.func(args)
    if isinstance(proc, LispFunction):
        if len(args) != len(proc.params):
            raise LispError("%s: expected %d arguments, got %d"
                            % (proc.name or "lambda", len(proc.params),
                               len(args)))
        child = Env(parent=proc.env)
        for name, value in zip(proc.params, args):
            child.define(name, value)
        return _eval_body(proc.body, child)
    raise LispError("not a function: %s" % format_value(proc))


def evaluate(expr, env):
    if isinstance(expr, Symbol):
        return env.lookup(expr.name)
    if isinstance(expr, list):
        if not expr:
            return None
        head = expr[0]
        if isinstance(head, Symbol) and head.name in SPECIAL_FORMS:
            return _eval_special(head.name, expr, env)
        proc = evaluate(head, env)
        args = [evaluate(arg, env) for arg in expr[1:]]
        return apply(proc, args)
    return expr  # numbers, strings, True, None are self-evaluating


def eval_str(source, env=None):
    """Evaluate every form in *source*; return the last value."""
    if env is None:
        env = standard_env()
    result = None
    for expr in parse_all(source):
        result = evaluate(expr, env)
    return result


def run_script(source, env=None):
    """Evaluate a script, discarding results (only side effects show)."""
    if env is None:
        env = standard_env()
    for expr in parse_all(source):
        evaluate(expr, env)
    return env


def run_file(path, env=None):
    with open(path, "r", encoding="utf-8") as handle:
        return run_script(handle.read(), env)


# ---------------------------------------------------------------------- REPL

def _balanced(source):
    """True when parens are balanced and no string is unterminated."""
    depth = 0
    in_string = False
    i = 0
    while i < len(source):
        ch = source[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == ";":
            while i < len(source) and source[i] != "\n":
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return True  # let the parser report the error
        i += 1
    return depth == 0 and not in_string


def _is_quit(form):
    if isinstance(form, Symbol) and form.name in ("QUIT", "EXIT"):
        return True
    return (isinstance(form, list) and len(form) == 1
            and isinstance(form[0], Symbol)
            and form[0].name in ("QUIT", "EXIT"))


def repl(in_stream=None, out_stream=None):
    """Read-Evaluate-Print Loop with the page's `cclisp>` prompt."""
    if in_stream is None:
        in_stream = sys.stdin
    if out_stream is None:
        out_stream = sys.stdout
    env = standard_env()
    prompt = "cclisp> "
    buffer = ""
    while True:
        out_stream.write(prompt)
        out_stream.flush()
        line = in_stream.readline()
        if line == "":
            out_stream.write("\n")
            return
        if buffer == "" and line.strip().lower() in ("quit", "exit"):
            return
        buffer += line
        if not _balanced(buffer):
            prompt = "...> "
            continue
        prompt = "cclisp> "
        try:
            forms = parse_all(buffer)
        except LispError as exc:
            out_stream.write("Error: %s\n" % exc)
            buffer = ""
            continue
        buffer = ""
        if not forms:
            continue
        if len(forms) == 1 and _is_quit(forms[0]):
            return
        try:
            for form in forms:
                if _is_quit(form):
                    return
                out_stream.write(format_value(evaluate(form, env)) + "\n")
        except LispError as exc:
            out_stream.write("Error: %s\n" % exc)
        except RecursionError:
            out_stream.write("Error: recursion limit exceeded\n")


# ------------------------------------------------------------------------ CLI

_USAGE = ("usage: lisp.py [--repl] [script.lisp | -]\n"
          "  no argument: REPL if stdin is a tty, else stdin script\n")


def main(argv):
    args = argv[1:]
    if args == ["--help"]:
        sys.stdout.write(_USAGE)
        return 0
    if len(args) > 1:
        sys.stderr.write(_USAGE)
        return 2
    try:
        if args == ["--repl"]:
            repl()
        elif args == ["-"]:
            run_script(sys.stdin.read())
        elif len(args) == 1:
            run_file(args[0])
        elif sys.stdin.isatty():
            repl()
        else:
            run_script(sys.stdin.read())
    except LispError as exc:
        sys.stderr.write("Error: %s\n" % exc)
        return 1
    except OSError as exc:
        sys.stderr.write("Error: %s\n" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

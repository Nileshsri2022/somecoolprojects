#!/usr/bin/env python3
"""ccxargs — build command lines from stdin and run them (a small xargs).

Python 3 standard library only. Arguments are passed to the utility via
exec (subprocess with an argument list), never through a shell, so shell
metacharacters in stdin items are data, not code.

See docs/SPEC.md for the supported options, exit codes and divergences
from GNU xargs.
"""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

VERSION = "1.0.0"
USAGE = """usage: ccxargs [-0prtx] [-E eofstr] [-I replstr] [-L max-lines]
               [-n max-args] [-P max-procs] [-s max-chars] [-d delim]
               [utility [initial-argument ...]]
  default utility is echo. Run `ccxargs --help` for the full list."""

HELP = USAGE + """

options:
  -0, --null             items are NUL-separated; no quoting
  -E eofstr, --eof=eofstr
                         stop reading at an item equal to eofstr (not in -0 mode)
  -I replstr, --replace=replstr
                         replace replstr in the utility arguments with one
                         input line per invocation (implies -L 1)
  -L max-lines, --max-lines=max-lines
                         at most max-lines non-blank input lines per invocation
  -n max-args, --max-args=max-args
                         at most max-args stdin items per invocation
  -P max-procs, --max-procs=max-procs
                         run at most max-procs invocations at once (0 = all)
  -p, --interactive      prompt on stderr before each invocation; answer
                         is read from /dev/tty (skipped if no tty)
  -r, --no-run-if-empty  do not run the utility when stdin yields no items
  -s max-chars, --max-chars=max-chars
                         approximate cap on one invocation's argument bytes
  -t, --verbose          print each command to stderr before running it
  -x                     error out instead of running a batch the -s limit
                         forced below the -n count, or a lone oversized item
  -d delim, --delimiter=delim
                         input items are separated by delim (quoting off)
  --help                 print this help and exit
  --version              print the version and exit
"""


class XargsError(Exception):
    """Usage / input error: reported as `ccxargs: <msg>`, exit 1."""


class Item:
    __slots__ = ("text", "line")

    def __init__(self, text, line):
        self.text = text
        self.line = line


def _decode(data):
    return data.decode("utf-8", "surrogateescape")


def _encode(text):
    return text.encode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- tokeniser

def tokenise(data, null_mode=False, delimiter=None):
    """Split raw stdin bytes into Items.

    Whitespace mode implements GNU quoting (single quotes, double quotes
    with limited backslash escapes, unquoted backslash escapes, and
    backslash-newline continuation). -0 splits on NUL, -d on the
    delimiter, both with quoting disabled. In -0/-d mode each item gets
    its own line number so -L/-I treat one item as one line.
    """
    text = _decode(data)
    if null_mode:
        parts = text.split("\x00")
        if parts and parts[-1] == "":
            parts.pop()
        return [Item(p, i) for i, p in enumerate(parts)]
    if delimiter is not None:
        parts = text.split(delimiter)
        if parts and parts[-1] == "":
            parts.pop()
        return [Item(p, i) for i, p in enumerate(parts)]

    items = []
    i, n = 0, len(text)
    line = 0
    while i < n:
        c = text[i]
        if c in " \t\n":
            if c == "\n":
                line += 1
            i += 1
            continue
        # Start of one item.
        start_line = line
        buf = []
        while i < n:
            c = text[i]
            if c in " \t\n":
                if c == "\n":
                    line += 1
                break
            if c == "'":
                i += 1
                while i < n and text[i] != "'":
                    if text[i] == "\n":
                        line += 1
                    buf.append(text[i])
                    i += 1
                if i >= n:
                    raise XargsError("unmatched single quote")
                i += 1  # closing quote
            elif c == '"':
                i += 1
                closed = False
                while i < n:
                    ch = text[i]
                    if ch == '"':
                        closed = True
                        i += 1
                        break
                    if ch == "\\" and i + 1 < n and text[i + 1] in '$`"\\\n':
                        if text[i + 1] == "\n":
                            line += 1
                        else:
                            buf.append(text[i + 1])
                        i += 2
                        continue
                    if ch == "\n":
                        line += 1
                    buf.append(ch)
                    i += 1
                if not closed:
                    raise XargsError("unmatched double quote")
            elif c == "\\":
                if i + 1 >= n:
                    # Trailing backslash: GNU keeps it out; treat as literal.
                    i += 1
                    continue
                nxt = text[i + 1]
                if nxt == "\n":
                    line += 1
                else:
                    buf.append(nxt)
                i += 2
            else:
                buf.append(c)
                i += 1
        items.append(Item("".join(buf), start_line))
    return items


# ------------------------------------------------------------------- options

class Options:
    def __init__(self):
        self.null = False
        self.eof = None
        self.replace = None
        self.max_lines = None
        self.max_args = None
        self.max_procs = None
        self.interactive = False
        self.no_run_if_empty = False
        self.max_chars = None
        self.verbose = False
        self.exit_on_size = False
        self.delimiter = None


def _need_value(opts, i, argv, attached):
    if attached is not None:
        return attached
    if i + 1 >= len(argv):
        raise XargsError("option requires an argument")
    return argv[i + 1]


def _parse_int(value, name):
    try:
        num = int(value, 10)
    except ValueError:
        raise XargsError("invalid %s value: %r" % (name, value))
    return num


def _parse_delim(value):
    escapes = {"n": "\n", "t": "\t", "r": "\r", "0": "\x00", "\\": "\\"}
    if len(value) == 2 and value[0] == "\\" and value[1] in escapes:
        return escapes[value[1]]
    if len(value) != 1:
        raise XargsError("-d delimiter must be a single character")
    return value


_LONG_VALUE = {
    "--null": ("null", False),
    "--eof": ("eof", True),
    "--replace": ("replace", True),
    "--max-lines": ("max_lines", True),
    "--max-args": ("max_args", True),
    "--max-procs": ("max_procs", True),
    "--interactive": ("interactive", False),
    "--no-run-if-empty": ("no_run_if_empty", False),
    "--max-chars": ("max_chars", True),
    "--verbose": ("verbose", False),
    "--delimiter": ("delimiter", True),
}

_SHORT_VALUE = {"E": "eof", "I": "replace", "L": "max_lines",
                "n": "max_args", "P": "max_procs", "s": "max_chars",
                "d": "delimiter"}
_SHORT_FLAG = {"0": "null", "p": "interactive", "r": "no_run_if_empty",
               "t": "verbose", "x": "exit_on_size"}


def parse_args(argv):
    """Return (Options, utility, initial_args). Stops at the first
    non-option argument or after `--`."""
    opts = Options()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            i += 1
            break
        if arg.startswith("--"):
            name, eq, val = arg.partition("=")
            if name in ("--help",):
                sys.stdout.write(HELP)
                raise SystemExit(0)
            if name in ("--version",):
                sys.stdout.write("ccxargs %s\n" % VERSION)
                raise SystemExit(0)
            if name not in _LONG_VALUE:
                raise XargsError("unknown option: %s" % name)
            field, takes_value = _LONG_VALUE[name]
            if takes_value:
                if not eq:
                    if i + 1 >= len(argv):
                        raise XargsError("option %s requires an argument" % name)
                    val = argv[i + 1]
                    i += 1
                setattr(opts, field, val)
            else:
                if eq:
                    raise XargsError("option %s takes no argument" % name)
                setattr(opts, field, True)
            i += 1
            continue
        if arg.startswith("-") and arg != "-":
            j = 1
            consumed_next = False
            while j < len(arg):
                ch = arg[j]
                if ch in _SHORT_FLAG:
                    setattr(opts, _SHORT_FLAG[ch], True)
                    j += 1
                    continue
                if ch in _SHORT_VALUE:
                    attached = arg[j + 1:] or None
                    val = _need_value(opts, i, argv, attached)
                    if attached is None:
                        consumed_next = True
                    setattr(opts, _SHORT_VALUE[ch], val)
                    j = len(arg)
                    continue
                raise XargsError("unknown option: -%s" % ch)
            i += 2 if consumed_next else 1
            continue
        break
    rest = argv[i:]
    utility = rest[0] if rest else "echo"
    initial = rest[1:] if len(rest) > 1 else []
    return opts, utility, initial


def validate(opts):
    if opts.max_args is not None:
        opts.max_args = _parse_int(opts.max_args, "-n")
        if opts.max_args < 1:
            raise XargsError("-n value must be at least 1")
    if opts.max_lines is not None:
        opts.max_lines = _parse_int(opts.max_lines, "-L")
        if opts.max_lines < 1:
            raise XargsError("-L value must be at least 1")
    if opts.max_procs is not None:
        opts.max_procs = _parse_int(opts.max_procs, "-P")
        if opts.max_procs < 0:
            raise XargsError("-P value must not be negative")
    if opts.max_chars is not None:
        opts.max_chars = _parse_int(opts.max_chars, "-s")
        if opts.max_chars < 1:
            raise XargsError("-s value must be at least 1")
    if opts.replace is not None and opts.replace == "":
        raise XargsError("-I replacement string must not be empty")
    if opts.delimiter is not None:
        opts.delimiter = _parse_delim(opts.delimiter)
    if opts.null and opts.delimiter is not None:
        raise XargsError("cannot combine -0 and -d")
    if opts.replace is not None:
        # -I implies -L 1, overriding any explicit -L.
        opts.max_lines = 1


# ------------------------------------------------------------------- batching

def group_lines(items):
    """Group items by line, dropping blank lines. Returns a list of
    lists of item texts, in input order."""
    groups = {}
    order = []
    for item in items:
        if item.line not in groups:
            groups[item.line] = []
            order.append(item.line)
        groups[item.line].append(item.text)
    return [groups[line] for line in order]


def build_batches(opts, items):
    """Return a list of batches; each batch is a list of item texts.
    For -I mode each batch is a single line (as one string)."""
    if opts.eof is not None and not opts.null:
        cut = []
        for item in items:
            if item.text == opts.eof:
                break
            cut.append(item)
        items = cut
    if not items:
        return [] if opts.no_run_if_empty else [[]]

    if opts.replace is not None:
        # One invocation per non-blank line; the line is one argument.
        return [[" ".join(line)] for line in group_lines(items)]

    if opts.max_lines is not None:
        lines = group_lines(items)
        batches = []
        for start in range(0, len(lines), opts.max_lines):
            chunk = lines[start:start + opts.max_lines]
            flat = [text for line in chunk for text in line]
            if opts.max_args is not None:
                # -L and -n both apply: split the chunk by -n as well.
                for s in range(0, len(flat), opts.max_args):
                    batches.append(flat[s:s + opts.max_args])
            else:
                batches.append(flat)
        return batches

    texts = [item.text for item in items]
    if opts.max_args is None and opts.max_chars is None:
        return [texts]

    batches = []
    cur, cur_size = [], 0
    for text in texts:
        size = len(_encode(text)) + 1
        if opts.max_chars is not None and size > opts.max_chars:
            raise XargsError("argument line too long")
        if cur and opts.max_chars is not None and cur_size + size > opts.max_chars:
            if opts.exit_on_size and opts.max_args is not None \
                    and len(cur) < opts.max_args:
                raise XargsError("argument line too long")
            batches.append(cur)
            cur, cur_size = [], 0
        if opts.max_args is not None and len(cur) >= opts.max_args:
            batches.append(cur)
            cur, cur_size = [], 0
        cur.append(text)
        cur_size += size
    if cur:
        batches.append(cur)
    return batches


def build_command(opts, utility, initial, batch):
    if opts.replace is not None:
        line = batch[0] if batch else ""
        if not initial:
            return [utility, line]
        return [utility] + [a.replace(opts.replace, line) for a in initial]
    return [utility] + initial + batch


# -------------------------------------------------------------------- running

def _trace(cmd):
    return " ".join(cmd)


def _prompt_and_confirm(cmd):
    sys.stderr.write("%s ?... " % _trace(cmd))
    sys.stderr.flush()
    try:
        tty = open("/dev/tty", "r")
    except OSError:
        sys.stderr.write("\n")
        return False
    with tty:
        answer = tty.readline()
    return answer[:1] in ("y", "Y")


def _run_one(opts, cmd):
    if opts.verbose:
        sys.stderr.write("%s\n" % _trace(cmd))
        sys.stderr.flush()
    if opts.interactive and not _prompt_and_confirm(cmd):
        return 0, True  # skipped counts as success
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        sys.stderr.write("ccxargs: %s: No such file or directory\n" % cmd[0])
        return 127, False
    except PermissionError:
        sys.stderr.write("ccxargs: %s: Permission denied\n" % cmd[0])
        return 127, False
    except OSError as exc:
        sys.stderr.write("ccxargs: %s: %s\n" % (cmd[0], exc))
        return 127, False
    return proc.returncode, True


def _map_status(code):
    """Map one child status to the aggregate exit code contribution."""
    if code == 0:
        return 0
    if code == 255:
        return 124
    if code < 0:
        return 125
    return 123


def run_batches(opts, commands):
    """Run commands, return the aggregate exit code."""
    if not commands:
        return 0
    seen = set()

    def note(code, ok):
        if not ok:
            return 127
        seen.add(_map_status(code))
        return None

    def aggregate():
        # Priority when kinds mix: 124 (exit 255) > 125 (signal) > 123.
        for wanted in (124, 125, 123):
            if wanted in seen:
                return wanted
        return 0

    procs = opts.max_procs
    if procs is None or procs == 1:
        for cmd in commands:
            code, ok = _run_one(opts, cmd)
            fatal = note(code, ok)
            if fatal is not None:
                return fatal
            if code == 255:
                break  # GNU aborts remaining invocations on exit 255.
        return aggregate()

    workers = len(commands) if procs == 0 else min(procs, len(commands))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_run_one, opts, cmd) for cmd in commands]
        for fut in as_completed(futures):
            code, ok = fut.result()
            fatal = note(code, ok)
            if fatal is not None:
                return fatal
    return aggregate()


def main(argv):
    try:
        opts, utility, initial = parse_args(argv)
        validate(opts)
        data = sys.stdin.buffer.read()
        items = tokenise(data, null_mode=opts.null,
                         delimiter=opts.delimiter)
        batches = build_batches(opts, items)
        commands = [build_command(opts, utility, initial, b) for b in batches]
        return run_batches(opts, commands)
    except XargsError as exc:
        sys.stderr.write("ccxargs: %s\n" % exc)
        sys.stderr.write(USAGE + "\n")
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

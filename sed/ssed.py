#!/usr/bin/env python3
"""ssed — a small stream editor (Build Your Own sed, Easy difficulty).

Python 3 standard library only. See docs/SPEC.md for the contract
and README.md for divergences from GNU sed (notably: Python `re`
instead of GNU BRE/ERE).

Usage: ssed.py [-n] [-i[SUFFIX]] [-e SCRIPT]... [-f FILE]...
               [SCRIPT] [FILE]...
"""

import re
import sys

PROG = "ssed"


class SedError(Exception):
    """Script/usage error: exit status 1 (matches GNU sed)."""


class Address:
    def __init__(self, kind, value=None):
        self.kind = kind  # 'line', 'last', 'regex'
        self.value = value

    def matches_line(self, line_no, is_last, line):
        if self.kind == "line":
            return line_no == self.value
        if self.kind == "last":
            return is_last
        return self.value.search(line) is not None


class Command:
    def __init__(self, kind, addr1=None, addr2=None):
        self.kind = kind  # 's', 'p', 'd', 'G', 'q'
        self.addr1 = addr1
        self.addr2 = addr2
        # s-command fields
        self.pattern = None
        self.replacement = ""
        self.global_flag = False
        self.nth = None
        self.print_flag = False
        self.w_file = None


def _split_lines(text):
    """Split text into (content, terminator) pairs, splitting on \\n only.

    A final line without a trailing newline keeps terminator ''.
    Empty text yields no lines.
    """
    if text == "":
        return []
    parts = text.split("\n")
    if text.endswith("\n"):
        parts = parts[:-1]
        return [(p, "\n") for p in parts]
    return [(p, "\n") for p in parts[:-1]] + [(parts[-1], "")]


class ScriptParser:
    """Sequential parser for one script text.

    Separators are newlines and ';' outside s-command fields and
    address regexes. `last_regex` tracks the most recent regex
    (address or s pattern) so an empty pattern reuses it.
    """

    def __init__(self, text, last_regex):
        self.text = text
        self.i = 0
        self.n = len(text)
        self.last_regex = last_regex  # (source, flags) or None
        self.first_command = True

    def error(self, msg):
        raise SedError(msg)

    def peek(self):
        return self.text[self.i] if self.i < self.n else ""

    def skip_blanks(self):
        while self.peek() in (" ", "\t"):
            self.i += 1

    def parse(self):
        commands = []
        # GNU: a script beginning with #n enables -n.
        if self.text.startswith("#n"):
            rest = self.text[2:]
            if rest == "" or rest[0] == "\n":
                self.i = 2
                commands.append("__quiet__")
        while True:
            # Skip separators and blank lines between commands.
            while self.peek() in (" ", "\t", "\n", ";"):
                self.i += 1
            if self.i >= self.n:
                break
            if self.first_command and self.peek() == "#":
                # #n handled above; any other leading comment line.
                while self.peek() not in ("", "\n"):
                    self.i += 1
                self.first_command = False
                continue
            self.first_command = False
            commands.append(self.parse_command())
        return commands

    def parse_address(self):
        ch = self.peek()
        if ch.isdigit():
            start = self.i
            while self.peek().isdigit():
                self.i += 1
            value = int(self.text[start:self.i])
            if value == 0:
                self.error("invalid usage of line address 0")
            return Address("line", value)
        if ch == "$":
            self.i += 1
            return Address("last")
        if ch == "/" or (ch == "\\" and self.i + 1 < self.n):
            if ch == "\\":
                delim = self.text[self.i + 1]
                self.i += 2
            else:
                delim = "/"
                self.i += 1
            source = self._read_field(delim)
            flags = 0
            # GNU address flag is capital I only: lowercase i here
            # would be the insert command, not a flag.
            if self.peek() == "I":
                flags = re.IGNORECASE
                self.i += 1
            if source == "":
                if self.last_regex is None:
                    self.error("no previous regular expression")
                source, flags = self.last_regex
            try:
                compiled = re.compile(source, flags)
            except re.error as exc:
                self.error("invalid regular expression: %s" % exc)
            self.last_regex = (source, flags)
            return Address("regex", compiled)
        return None

    def _read_field(self, delim):
        """Read up to an unescaped delimiter; delimiter escapes collapse.

        Other backslash sequences are preserved verbatim (the regex
        engine and the replacement expander interpret them).
        """
        out = []
        while self.i < self.n:
            ch = self.text[self.i]
            if ch == "\\" and self.i + 1 < self.n:
                nxt = self.text[self.i + 1]
                if nxt == delim:
                    out.append(delim)
                    self.i += 2
                else:
                    out.append(ch)
                    out.append(nxt)
                    self.i += 2
                continue
            if ch == delim:
                self.i += 1
                return "".join(out)
            if ch == "\n":
                break
            out.append(ch)
            self.i += 1
        self.error("unterminated command (missing delimiter %r)" % delim)

    def parse_command(self):
        addr1 = self.parse_address()
        addr2 = None
        self.skip_blanks()
        if addr1 is not None and self.peek() == ",":
            self.i += 1
            self.skip_blanks()
            addr2 = self.parse_address()
            if addr2 is None:
                self.error("missing address after ','")
            self.skip_blanks()
        if self.i >= self.n:
            self.error("missing command after address")
        kind = self.text[self.i]
        self.i += 1
        cmd = Command(kind, addr1, addr2)
        if kind == "s":
            self._parse_substitute(cmd)
        elif kind in ("p", "d", "G", "q"):
            pass
        else:
            self.error("unknown command: %r" % kind)
        self._expect_separator()
        return cmd

    def _parse_substitute(self, cmd):
        if self.i >= self.n:
            self.error("unterminated `s' command")
        delim = self.text[self.i]
        self.i += 1
        source = self._read_field(delim)
        cmd.replacement = self._read_field(delim)
        flags = 0
        number = None
        w_file = None
        while self.i < self.n:
            ch = self.text[self.i]
            if ch == "g":
                cmd.global_flag = True
                self.i += 1
            elif ch == "p":
                cmd.print_flag = True
                self.i += 1
            elif ch in ("i", "I"):
                flags |= re.IGNORECASE
                self.i += 1
            elif ch.isdigit():
                start = self.i
                while self.peek().isdigit():
                    self.i += 1
                number = int(self.text[start:self.i])
            elif ch == "w":
                self.i += 1
                self.skip_blanks()
                start = self.i
                while self.peek() not in ("", "\n", ";"):
                    self.i += 1
                w_file = self.text[start:self.i].strip()
                if not w_file:
                    self.error("missing filename for `w' flag")
                break
            elif ch in (" ", "\t"):
                self.i += 1
            else:
                break
        if cmd.global_flag and number is not None:
            self.error("cannot combine `g' flag with a number flag")
        cmd.nth = number
        if source == "":
            if self.last_regex is None:
                self.error("no previous regular expression")
            source, flags = self.last_regex
        try:
            cmd.pattern = re.compile(source, flags)
        except re.error as exc:
            self.error("invalid regular expression: %s" % exc)
        self.last_regex = (source, flags)
        cmd.w_file = w_file

    def _expect_separator(self):
        self.skip_blanks()
        ch = self.peek()
        if ch not in ("", "\n", ";"):
            self.error("extra characters after command: %r" % ch)


def parse_scripts(script_texts):
    """Parse all -e/-f/script texts in order. Returns (commands, quiet)."""
    commands = []
    quiet = False
    last_regex = None
    for text in script_texts:
        parser = ScriptParser(text, last_regex)
        parsed = parser.parse()
        last_regex = parser.last_regex
        for cmd in parsed:
            if cmd == "__quiet__":
                quiet = True
            else:
                commands.append(cmd)
    return commands, quiet


def parse_args(argv):
    """Returns (opts, script_texts, files). opts: dict."""
    opts = {"quiet": False, "in_place": None, "in_place_suffix": None}
    script_texts = []
    files = []
    script_from_args = False
    i = 0
    end_opts = False
    while i < len(argv):
        arg = argv[i]
        if end_opts or not arg.startswith("-") or arg == "-":
            if not script_texts and not script_from_args:
                script_texts.append(arg)
                script_from_args = True
            else:
                files.append(arg)
            i += 1
            continue
        if arg == "--":
            end_opts = True
            i += 1
            continue
        if arg == "--help":
            print("Usage: ssed.py [-n] [-i[SUFFIX]] [-e SCRIPT]... "
                  "[-f FILE]... [SCRIPT] [FILE]...")
            sys.exit(0)
        # Short-option cluster.
        j = 1
        consumed_next = False
        while j < len(arg):
            ch = arg[j]
            if ch == "n":
                opts["quiet"] = True
                j += 1
            elif ch == "i":
                opts["in_place"] = True
                opts["in_place_suffix"] = arg[j + 1:] or None
                j = len(arg)
            elif ch == "e":
                if j + 1 < len(arg):
                    script_texts.append(arg[j + 1:])
                else:
                    if i + 1 >= len(argv):
                        raise SedError("option -e requires an argument")
                    script_texts.append(argv[i + 1])
                    consumed_next = True
                j = len(arg)
            elif ch == "f":
                if j + 1 < len(arg):
                    path = arg[j + 1:]
                else:
                    if i + 1 >= len(argv):
                        raise SedError("option -f requires an argument")
                    path = argv[i + 1]
                    consumed_next = True
                try:
                    with open(path, "r", encoding="utf-8",
                              errors="surrogateescape") as fh:
                        script_texts.append(fh.read())
                except OSError as exc:
                    raise SedError("can't read %s: %s" % (path, exc.strerror))
                j = len(arg)
            else:
                raise SedError("unknown option: -%s" % ch)
        i += 2 if consumed_next else 1
    if not script_texts:
        raise SedError("no script given (usage: ssed.py [SCRIPT] [FILE]...)")
    return opts, script_texts, files


def expand_replacement(replacement, match):
    out = []
    i = 0
    while i < len(replacement):
        ch = replacement[i]
        if ch == "&":
            out.append(match.group(0))
            i += 1
        elif ch == "\\" and i + 1 < len(replacement):
            nxt = replacement[i + 1]
            if nxt.isdigit():
                try:
                    out.append(match.group(int(nxt)) or "")
                except IndexError:
                    out.append("")
                i += 2
            elif nxt == "&":
                out.append("&")
                i += 2
            elif nxt == "\\":
                out.append("\\")
                i += 2
            elif nxt == "n":
                out.append("\n")
                i += 2
            else:
                out.append(nxt)
                i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def apply_substitution(cmd, line):
    """Returns (new_line, substituted_bool)."""
    matches = list(cmd.pattern.finditer(line))
    if not matches:
        return line, False
    if cmd.nth is not None:
        wanted = {cmd.nth - 1}
    elif cmd.global_flag:
        wanted = set(range(len(matches)))
    else:
        wanted = {0}
    out = []
    pos = 0
    for idx, m in enumerate(matches):
        if idx not in wanted:
            continue
        out.append(line[pos:m.start()])
        out.append(expand_replacement(cmd.replacement, m))
        pos = m.end()
    out.append(line[pos:])
    return "".join(out), True


def render(chunks):
    """Turn [(pattern, source_terminator)] into output text.

    Verified against GNU sed 4.9: every chunk is terminated with
    "\\n" except possibly the very last chunk of a destination
    stream, which keeps no terminator when its source line had
    none and its pattern does not end with "\\n" (e.g. a plain
    unterminated last line, but not a G-doubled one, whose
    pattern already ends with "\\n").
    """
    out = []
    for idx, (pattern, term) in enumerate(chunks):
        if idx == len(chunks) - 1 and term == "" \
                and not pattern.endswith("\n"):
            out.append(pattern)
        else:
            out.append(pattern + "\n")
    return "".join(out)


def process_lines(lines, commands, quiet, w_chunks):
    """Run one file's cycle. lines: [(content, terminator)]. Returns
    output [(pattern, source_terminator)] and whether q stopped
    processing. w_chunks maps a w filename to its chunk list."""
    output = []
    range_active = {id(cmd): False for cmd in commands}
    total = len(lines)
    quit_all = False
    for line_no, (line, term) in enumerate(lines, start=1):
        is_last = line_no == total
        pattern = line
        deleted = False
        for cmd in commands:
            # Address matching, with range state.
            started = False
            if cmd.addr1 is None:
                matched = True
            elif cmd.addr2 is None:
                matched = cmd.addr1.matches_line(line_no, is_last, pattern)
            else:
                if range_active[id(cmd)]:
                    matched = True
                elif cmd.addr1.matches_line(line_no, is_last, pattern):
                    matched = True
                    range_active[id(cmd)] = True
                    started = True
                else:
                    matched = False
            if not matched:
                continue
            if cmd.kind == "s":
                pattern, substituted = apply_substitution(cmd, pattern)
                if substituted:
                    if cmd.print_flag:
                        output.append((pattern, term))
                    if cmd.w_file is not None:
                        w_chunks[cmd.w_file].append((pattern, term))
            elif cmd.kind == "p":
                output.append((pattern, term))
            elif cmd.kind == "d":
                deleted = True
            elif cmd.kind == "G":
                pattern = pattern + "\n"
            elif cmd.kind == "q":
                quit_all = True
            # Range end check (after this line's command).
            if cmd.addr2 is not None and range_active[id(cmd)]:
                end = cmd.addr2
                if end.kind == "line":
                    if line_no >= end.value:
                        range_active[id(cmd)] = False
                elif end.kind == "last":
                    if is_last:
                        range_active[id(cmd)] = False
                elif not started:
                    if end.matches_line(line_no, is_last, pattern):
                        range_active[id(cmd)] = False
            if cmd.kind == "d":
                break
            if quit_all:
                break
        if not deleted and not quiet:
            output.append((pattern, term))
        if quit_all:
            break
    return output, quit_all


def read_input(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "surrogateescape")


def main(argv):
    try:
        opts, script_texts, files = parse_args(argv)
        commands, script_quiet = parse_scripts(script_texts)
    except SedError as exc:
        print("%s: %s" % (PROG, exc), file=sys.stderr)
        return 1
    quiet = opts["quiet"] or script_quiet

    # Buffer w output per file (truncation happens at flush time,
    # matching GNU: the w file is created even if no line matches).
    w_chunks = {}
    for cmd in commands:
        if cmd.w_file is not None and cmd.w_file not in w_chunks:
            w_chunks[cmd.w_file] = []
    exit_status = 0
    inputs = files if files else ["-"]
    quit_all = False
    stdout_chunks = []
    for path in inputs:
        if quit_all:
            break
        if path == "-":
            text = sys.stdin.buffer.read().decode(
                "utf-8", "surrogateescape")
            lines = _split_lines(text)
            output, quit_all = process_lines(
                lines, commands, quiet, w_chunks)
            if opts["in_place"]:
                # No file to edit: pass through unchanged, like GNU.
                sys.stdout.buffer.write(
                    text.encode("utf-8", "surrogateescape"))
            else:
                stdout_chunks.extend(output)
            continue
        try:
            text = read_input(path)
        except OSError as exc:
            print("%s: can't read %s: %s"
                  % (PROG, path, exc.strerror), file=sys.stderr)
            exit_status = 2
            continue
        lines = _split_lines(text)
        output, quit_all = process_lines(
            lines, commands, quiet, w_chunks)
        if not opts["in_place"]:
            stdout_chunks.extend(output)
            continue
        out_text = render(output)
        if opts["in_place_suffix"] is not None:
            try:
                with open(path + opts["in_place_suffix"], "wb") as fh:
                    fh.write(text.encode("utf-8", "surrogateescape"))
            except OSError as exc:
                print("%s: can't write backup %s: %s"
                      % (PROG, path + opts["in_place_suffix"],
                         exc.strerror), file=sys.stderr)
                exit_status = 2
                continue
        try:
            with open(path, "wb") as fh:
                fh.write(out_text.encode("utf-8", "surrogateescape"))
        except OSError as exc:
            print("%s: can't write %s: %s"
                  % (PROG, path, exc.strerror), file=sys.stderr)
            exit_status = 2
    # Stdout is rendered once, so the final-newline rule (see
    # render()) applies to the last chunk of the whole run, not
    # per file — matching GNU sed on multi-file input.
    if stdout_chunks:
        sys.stdout.buffer.write(
            render(stdout_chunks).encode("utf-8", "surrogateescape"))
    for w_path, chunks in w_chunks.items():
        try:
            with open(w_path, "wb") as fh:
                fh.write(render(chunks).encode(
                    "utf-8", "surrogateescape"))
        except OSError as exc:
            print("%s: can't write %s: %s"
                  % (PROG, w_path, exc.strerror), file=sys.stderr)
            exit_status = 2
    return exit_status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

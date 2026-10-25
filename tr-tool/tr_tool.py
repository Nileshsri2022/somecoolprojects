#!/usr/bin/env python3
"""tr_tool.py — a byte-oriented clone of the Unix `tr` command.

Translate, delete, and squeeze characters, reading standard input
and writing standard output. Python 3 standard library only.

See docs/SPEC.md for the full behaviour specification, including
the deliberate divergences from the BSD man page quoted by the
challenge page (https://codingchallenges.fyi/challenges/challenge-tr).

Usage:
    python3 tr_tool.py [-cCdstu] [string1 [string2]]
    python3 tr_tool.py --delete string1
    python3 tr_tool.py --squeeze-repeats string1
    python3 tr_tool.py --delete --squeeze-repeats string1 string2
"""

import os
import sys

CHUNK_SIZE = 65536

USAGE = """\
Usage: tr_tool.py [-cCdstu] string1 [string2]
       tr_tool.py -d string1
       tr_tool.py -s string1
       tr_tool.py -ds string1 string2
Options:
  -c, -C, --complement        complement string1
  -d, --delete                delete characters in string1
  -s, --squeeze-repeats       squeeze repeated characters
  -t, --truncate-set1         truncate string1 to the length of string2
  -u                          accepted, no-op (output is already chunked)
  --help                      print this help
"""


class TrError(Exception):
    """A user-facing error: message to stderr, exit status 1."""


# Character classes, in ascending byte order. ASCII definitions,
# matching GNU tr in the C locale (see docs/SPEC.md).
def _class_bytes(predicate):
    return [b for b in range(256) if predicate(b)]


CLASSES = {
    "alnum": _class_bytes(lambda b: (48 <= b <= 57) or (65 <= b <= 90)
                          or (97 <= b <= 122)),
    "alpha": _class_bytes(lambda b: (65 <= b <= 90) or (97 <= b <= 122)),
    "blank": [9, 32],
    "cntrl": _class_bytes(lambda b: b <= 31 or b == 127),
    "digit": _class_bytes(lambda b: 48 <= b <= 57),
    "graph": _class_bytes(lambda b: 33 <= b <= 126),
    "lower": _class_bytes(lambda b: 97 <= b <= 122),
    "print": _class_bytes(lambda b: 32 <= b <= 126),
    "punct": _class_bytes(lambda b: (33 <= b <= 47) or (58 <= b <= 64)
                          or (91 <= b <= 96) or (123 <= b <= 126)),
    "space": [9, 10, 11, 12, 13, 32],
    "upper": _class_bytes(lambda b: 65 <= b <= 90),
    "xdigit": _class_bytes(lambda b: (48 <= b <= 57) or (65 <= b <= 70)
                           or (97 <= b <= 102)),
}

_NAMED_ESCAPES = {
    97: 7,    # \a alert
    98: 8,    # \b backspace
    102: 12,  # \f form feed
    110: 10,  # \n newline
    114: 13,  # \r carriage return
    116: 9,   # \t tab
    118: 11,  # \v vertical tab
    92: 92,   # \\ backslash
}

# Atom kinds produced by the scanner (see parse_set):
#   ("s", value, is_bare_hyphen)  a single byte
#   ("c", [bytes])                a class expansion
#   ("r", value, n_or_None)       a [c*n] repeat (string2 only);
#                                 n None means "fill to string1's length"


def _parse_escape(spec, i):
    """Parse the escape starting at spec[i] == backslash.

    Returns (value, next_index). A trailing backslash is a
    literal backslash (system tr warns about this spelling but
    still treats it that way; this tool does so silently).
    """
    if i + 1 >= len(spec):
        return 92, i + 1
    c = spec[i + 1]
    if c in _NAMED_ESCAPES:
        return _NAMED_ESCAPES[c], i + 2
    if 48 <= c <= 55:  # octal digit: consume up to 3 octal digits
        j = i + 1
        while j < len(spec) and j < i + 4 and 48 <= spec[j] <= 55:
            j += 1
        return int(spec[i + 1:j], 8) & 0xFF, j
    return c, i + 2


def _try_repeat(spec, i):
    """Try to parse a [c*n] / [c*] repeat starting at spec[i] == '['.

    Returns (value, n_or_None, end_index) or None if the text does
    not have the repeat shape. n None means omitted or 0 (fill).
    """
    pos = i + 1
    if pos >= len(spec):
        return None
    if spec[pos] == 92:  # backslash
        try:
            value, pos = _parse_escape(spec, pos)
        except TrError:
            return None
    else:
        value, pos = spec[pos], pos + 1
    if pos >= len(spec) or spec[pos] != 42:  # '*'
        return None
    pos += 1
    start = pos
    while pos < len(spec) and 48 <= spec[pos] <= 57:
        pos += 1
    if pos >= len(spec) or spec[pos] != 93:  # ']'
        return None
    digits = spec[start:pos]
    if not digits or digits == b"0":
        n = None
    elif len(digits) > 1 and digits[:1] == b"0":
        n = int(digits, 8)
    else:
        n = int(digits, 10)
    return value, n, pos + 1


def parse_set(spec, allow_equivalence=True):
    """Parse a set specification (bytes) into a list of elements.

    allow_equivalence=False rejects [=c=] (system tr forbids
    equivalence expressions in string2 when translating).

    Elements are ints, except a repeat-fill which is the tuple
    ("fill", byte); use resolve_fills() to expand fills once the
    length of string1 is known. Ranges, classes, escapes,
    equivalence and repeats are expanded here. A fill repeat
    ([c*] / [c*0]) in string1 is rejected later, by
    build_config/build_translation, not here, so that the same
    parser serves both operands. Raises TrError on malformed
    specifications.
    """
    atoms = []
    i = 0
    while i < len(spec):
        b = spec[i]
        if b == 92:  # backslash
            value, i = _parse_escape(spec, i)
            atoms.append(("s", value, False))
            continue
        if b == 91:  # '['
            # Character class [:name:]
            if spec[i:i + 2] == b"[:":
                j = spec.find(b":]", i + 2)
                if j != -1:
                    name = spec[i + 2:j]
                    if name and all(97 <= c <= 122 for c in name):
                        name_str = name.decode("ascii")
                        if name_str not in CLASSES:
                            raise TrError(
                                "invalid character class '%s'" % name_str)
                        atoms.append(("c", list(CLASSES[name_str])))
                        i = j + 2
                        continue
            # Equivalence [=c=]
            if spec[i:i + 2] == b"[=":
                j = spec.find(b"=]", i + 2)
                if j != -1 and not allow_equivalence:
                    raise TrError(
                        "[=c=] expressions may not appear in string2 "
                        "when translating")
                if j != -1:
                    inner = spec[i + 2:j]
                    if len(inner) == 1:
                        atoms.append(("s", inner[0], False))
                        i = j + 2
                        continue
                    if inner[:1] == b"\\" :
                        try:
                            value, nxt = _parse_escape(inner, 0)
                        except TrError:
                            value, nxt = None, -1
                        if nxt == len(inner):
                            atoms.append(("s", value, False))
                            i = j + 2
                            continue
                    raise TrError(
                        "equivalence class [=...=] must contain "
                        "exactly one character")
            # Repeat [c*n] / [c*] (explicit counts in either set;
            # a fill repeat in string1 is rejected by the caller)
            repeat = _try_repeat(spec, i)
            if repeat is not None:
                value, n, end = repeat
                atoms.append(("r", value, n))
                i = end
                continue
            atoms.append(("s", 91, False))
            i += 1
            continue
        atoms.append(("s", b, b == 45))  # bare '-' is a range operator
        i += 1

    # Range pass: single, bare '-', single -> inclusive range.
    # A class or repeat block on either side breaks the range,
    # and a '-' at the start/end stays literal.
    out = []
    i = 0
    while i < len(atoms):
        atom = atoms[i]
        if (atom[0] == "s" and i + 2 < len(atoms)
                and atoms[i + 1][0] == "s"
                and atoms[i + 1][1] == 45 and atoms[i + 1][2]
                and atoms[i + 2][0] == "s"):
            lo, hi = atom[1], atoms[i + 2][1]
            if lo > hi:
                raise TrError(
                    "range-endpoints of '%s-%s' are in reverse "
                    "collating sequence order"
                    % (chr(lo) if 32 <= lo < 127 else "\\%03o" % lo,
                       chr(hi) if 32 <= hi < 127 else "\\%03o" % hi))
            out.extend(range(lo, hi + 1))
            i += 3
        elif atom[0] == "s":
            out.append(atom[1])
            i += 1
        elif atom[0] == "c":
            out.extend(atom[1])
            i += 1
        else:  # repeat
            _, value, n = atom
            if n is None:
                out.append(("fill", value))
            else:
                out.extend([value] * n)
            i += 1
    return out


def resolve_fills(elements, target_len):
    """Expand ("fill", byte) elements in a parsed set.

    With target_len given, the first fill expands to however many
    copies are needed to reach target_len (further fills expand
    to nothing); without one, each fill expands to a single copy
    (membership is all that matters for a squeeze/delete set).
    """
    if not any(isinstance(e, tuple) for e in elements):
        return list(elements)
    fixed = sum(1 for e in elements if isinstance(e, int))
    out = []
    remaining = None if target_len is None else max(0, target_len - fixed)
    for e in elements:
        if isinstance(e, int):
            out.append(e)
        else:
            _, value = e
            if remaining is None:
                out.append(value)
            else:
                out.extend([value] * remaining)
                remaining = 0
    return out


def _check_no_fill_in_string1(elements):
    if any(isinstance(e, tuple) for e in elements):
        raise TrError(
            "the [c*] repeat construct may not appear in string1")


def build_translation(s1_elements, s2_elements, complement, truncate):
    """Build (translation_table, squeeze_set) for translate mode.

    s1_elements / s2_elements are parse_set() results. The
    squeeze set is string2 as written (before padding), as
    verified against system tr (see docs/DESIGN.md).
    """
    _check_no_fill_in_string1(s1_elements)
    s1 = resolve_fills(s1_elements, None)
    if complement:
        in_s1 = set(s1)
        s1 = [b for b in range(256) if b not in in_s1]
    s2_written = resolve_fills(s2_elements, None)
    s2 = resolve_fills(s2_elements, len(s1))
    if truncate:
        s1 = s1[:len(s2)]
    else:
        if not s2 and s1:
            raise TrError(
                "when not truncating set1, string2 must be non-empty")
        if len(s2) < len(s1):
            s2 = s2 + [s2[-1]] * (len(s1) - len(s2))
    table = bytearray(range(256))
    for a, b in zip(s1, s2):
        table[a] = b  # last pairing wins on duplicates (system tr)
    return bytes(table), set(s2_written)


def squeeze_chunk(data, squeeze_set, prev):
    """Squeeze one chunk. Returns (output_bytes, new_prev).

    `prev` is the last byte actually emitted (or None at the
    start); it is carried across chunks by the caller so a run
    split by a chunk boundary still squeezes to one byte.
    """
    if not squeeze_set:
        return data, (data[-1] if data else prev)
    out = bytearray()
    for b in data:
        if b == prev and b in squeeze_set:
            continue
        out.append(b)
        prev = b
    return bytes(out), prev


def parse_args(argv):
    """Parse argv (list of str) into (flags_dict, operands).

    Raises TrError on unknown options. --help is reported via
    the 'help' flag; the caller prints USAGE and exits 0.
    """
    flags = {"complement": False, "delete": False, "squeeze": False,
             "truncate": False, "help": False}
    long_options = {
        "--complement": "complement",
        "--delete": "delete",
        "--squeeze-repeats": "squeeze",
        "--truncate-set1": "truncate",
        "--help": "help",
    }
    short_options = {"c": "complement", "C": "complement",
                     "d": "delete", "s": "squeeze", "t": "truncate",
                     "u": None}  # -u: accepted, no-op
    operands = []
    end_options = False
    for arg in argv:
        if end_options or operands:
            operands.append(arg)
        elif arg == "--":
            end_options = True
        elif arg.startswith("--"):
            if arg not in long_options:
                raise TrError("unrecognized option '%s'" % arg)
            flags[long_options[arg]] = True
        elif arg.startswith("-") and len(arg) > 1:
            for ch in arg[1:]:
                if ch not in short_options:
                    raise TrError("invalid option -- '%s'" % ch)
                if short_options[ch] is not None:
                    flags[short_options[ch]] = True
        else:
            operands.append(arg)
    return flags, operands


def build_config(flags, operands):
    """Validate mode/operands and build the processing config.

    Returns a dict with keys: table (bytes|None), delete (set|None),
    squeeze (set|None). Raises TrError before any input is read.
    """
    delete = flags["delete"]
    squeeze = flags["squeeze"]
    if delete and squeeze:
        if len(operands) != 2:
            raise TrError(
                "when deleting and squeezing, two operands are required")
        s1 = parse_set(os.fsencode(operands[0]))
        s2 = parse_set(os.fsencode(operands[1]))
        _check_no_fill_in_string1(s1)
        del_set = set(resolve_fills(s1, None))
        if flags["complement"]:
            del_set = set(range(256)) - del_set
        return {"table": None, "delete": del_set,
                "squeeze": set(resolve_fills(s2, None))}
    if delete:
        if len(operands) != 1:
            raise TrError("when deleting, exactly one operand is required")
        s1 = parse_set(os.fsencode(operands[0]))
        _check_no_fill_in_string1(s1)
        del_set = set(resolve_fills(s1, None))
        if flags["complement"]:
            del_set = set(range(256)) - del_set
        return {"table": None, "delete": del_set, "squeeze": None}
    if squeeze and len(operands) == 1:
        s1 = parse_set(os.fsencode(operands[0]))
        _check_no_fill_in_string1(s1)
        sq_set = set(resolve_fills(s1, None))
        if flags["complement"]:
            sq_set = set(range(256)) - sq_set
        return {"table": None, "delete": None, "squeeze": sq_set}
    # Translate, with or without squeeze.
    if len(operands) != 2:
        if not operands:
            raise TrError("missing operand")
        raise TrError(
            "when translating, two operands are required")
    s1 = parse_set(os.fsencode(operands[0]))
    s2 = parse_set(os.fsencode(operands[1]), allow_equivalence=False)
    table, s2_written = build_translation(
        s1, s2, flags["complement"], flags["truncate"])
    sq_set = set(s2_written) if squeeze else None
    return {"table": table, "delete": None, "squeeze": sq_set}


def process_stream(in_stream, out_stream, config):
    """Stream in_stream to out_stream per config (see build_config)."""
    table = config["table"]
    if table is None:
        table = bytes(range(256))
    delete = (bytes(sorted(config["delete"]))
              if config["delete"] else b"")
    squeeze_set = config["squeeze"]
    prev = None
    while True:
        chunk = in_stream.read(CHUNK_SIZE)
        if not chunk:
            break
        if config["delete"] or config["table"] is not None:
            chunk = chunk.translate(table, delete)
        if squeeze_set is not None:
            chunk, prev = squeeze_chunk(chunk, squeeze_set, prev)
        out_stream.write(chunk)
        out_stream.flush()


def main(argv):
    try:
        flags, operands = parse_args(argv)
        if flags["help"]:
            sys.stdout.write(USAGE)
            return 0
        config = build_config(flags, operands)
        process_stream(sys.stdin.buffer, sys.stdout.buffer, config)
    except TrError as exc:
        sys.stderr.write("tr_tool.py: %s\n" % exc)
        return 1
    except BrokenPipeError:
        try:
            sys.stdout.buffer.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

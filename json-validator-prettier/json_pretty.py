#!/usr/bin/env python3
"""JSON validator and prettier (CLI).

Validate JSON, pretty-print it, sort keys at every level, compress it
(whitespace removal that preserves string contents byte-for-byte), or
convert it to YAML. Python 3 standard library only.

Usage:
    python3 json_pretty.py [options] [file]
    cat file.json | python3 json_pretty.py [options]

With no file argument (or "-" as the file), input is read from stdin.
See docs/SPEC.md for the full contract, including exit codes:
0 = valid, 1 = invalid JSON, 2 = usage/IO error.
"""

import argparse
import json
import sys

USAGE_MODES = ("pretty", "check", "compress", "yaml")


def _reject_constant(value):
    """parse_constant hook: NaN/Infinity are not JSON, so reject them."""
    raise ValueError("Invalid constant %r: not valid JSON" % value)


def validate(text):
    """Parse *text* as JSON.

    Returns (value, None) on success, or (None, error_dict) on failure,
    where error_dict has keys: message, line, column.
    """
    try:
        value = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        return None, {"message": exc.msg, "line": exc.lineno,
                      "column": exc.colno}
    except RecursionError:
        return None, {"message": "Input nesting is too deep",
                      "line": 1, "column": 1}
    except ValueError as exc:
        # Raised by _reject_constant for NaN / Infinity / -Infinity.
        # json reports the constant's position only loosely; pin it to
        # the first occurrence so the caret still points at real text.
        for token in ("NaN", "Infinity", "-Infinity"):
            pos = text.find(token)
            if pos != -1:
                line = text.count("\n", 0, pos) + 1
                last_nl = text.rfind("\n", 0, pos)
                return None, {"message": str(exc), "line": line,
                              "column": pos - last_nl}
        return None, {"message": str(exc), "line": 1, "column": 1}
    return value, None


def format_error(text, error):
    """Render an error as: message line, source line, caret line."""
    lines = text.split("\n")
    line_no = error["line"]
    column = error["column"]
    if 1 <= line_no <= len(lines):
        source = lines[line_no - 1]
    elif lines:
        source = lines[-1]
        column = len(source) + 1
    else:
        source = ""
        column = 1
    caret = " " * max(column - 1, 0) + "^"
    return ("Invalid JSON: %s at line %d, column %d\n%s\n%s"
            % (error["message"], line_no, column, source, caret))


def sort_value(value):
    """Return a copy of *value* with every object's keys sorted.

    Array order is untouched; sorting applies independently at each
    nesting level, as the challenge's Step 3 requires.
    """
    if isinstance(value, dict):
        return {key: sort_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [sort_value(item) for item in value]
    return value


def compress_json(text):
    """Remove all whitespace outside strings from already-valid *text*.

    Character scanner: outside a string, whitespace is dropped; inside a
    string, characters are copied verbatim, with a backslash copying
    itself and the following character so an escaped quote never ends
    the string early. Original number and escape spellings survive,
    because nothing is re-serialized.
    """
    out = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
                out.append(char)
            elif char.isspace():
                continue
            else:
                out.append(char)
    return "".join(out)


# Characters that force double-quoting of a YAML plain scalar anywhere in
# the string. The rule is deliberately conservative: over-quoting is safe,
# under-quoting corrupts data (see docs/DESIGN.md). Interior hyphens and
# apostrophes are fine in plain scalars, so they are not in this set; a
# leading indicator character is caught by the first-character check in
# yaml_scalar instead.
_YAML_PLAIN_FORBIDDEN = set("{}[],&*#?|>@`\"")
_YAML_PLAIN_WORDS = {"true", "false", "null", "~", "yes", "no", "on", "off"}


def _looks_like_number(text):
    try:
        float(text)
    except ValueError:
        return False
    # float() also accepts "nan"/"inf"; those are not YAML numbers here.
    return text.strip().lower() not in ("nan", "inf", "+inf", "-inf",
                                        "infinity", "+infinity",
                                        "-infinity")


def yaml_scalar(value):
    """Render a JSON scalar as a YAML scalar (never a mapping/sequence)."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    # Strings: plain only when provably safe, otherwise double-quoted
    # (json.dumps escaping is valid YAML double-quoted style).
    text = value
    if text == "":
        return '""'
    if text != text.strip():
        return json.dumps(text, ensure_ascii=False)
    if text.lower() in _YAML_PLAIN_WORDS or _looks_like_number(text):
        return json.dumps(text, ensure_ascii=False)
    if text[0] in "-?:,[]{}#&*!|>'\"%@`":
        return json.dumps(text, ensure_ascii=False)
    if any(ch in _YAML_PLAIN_FORBIDDEN for ch in text):
        return json.dumps(text, ensure_ascii=False)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return json.dumps(text, ensure_ascii=False)
    if ": " in text or " #" in text or text.endswith(":"):
        return json.dumps(text, ensure_ascii=False)
    return text


def yaml_key(key):
    """Render a JSON object key for a YAML mapping line."""
    if key == "":
        return '""'
    return yaml_scalar(key)


def to_yaml(value, step=2):
    """Convert a parsed JSON value to YAML lines (no trailing newline).

    Mappings: ``key: value``; sequences: ``- item`` one step below the
    owning key; a mapping inside a sequence puts its first key on the
    dash line. Empty dict/list render as ``{}`` / ``[]``.
    """
    lines = []
    _emit_yaml(value, 0, step, lines)
    return lines


def _emit_yaml(value, indent, step, lines):
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            lines.append(pad + "{}")
            return
        for key, item in value.items():
            rendered_key = yaml_key(key)
            if isinstance(item, dict):
                if not item:
                    lines.append("%s%s: {}" % (pad, rendered_key))
                else:
                    lines.append("%s%s:" % (pad, rendered_key))
                    _emit_yaml(item, indent + step, step, lines)
            elif isinstance(item, list):
                if not item:
                    lines.append("%s%s: []" % (pad, rendered_key))
                else:
                    lines.append("%s%s:" % (pad, rendered_key))
                    _emit_yaml(item, indent + step, step, lines)
            else:
                lines.append("%s%s: %s" % (pad, rendered_key,
                                            yaml_scalar(item)))
    elif isinstance(value, list):
        if not value:
            lines.append(pad + "[]")
            return
        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(pad + "- {}")
                else:
                    entries = list(item.items())
                    first_key, first_val = entries[0]
                    _append_mapping_first(lines, pad, first_key, first_val,
                                          indent, step)
                    for key, val in entries[1:]:
                        # Continuation keys align with the first key,
                        # which sits two columns past the dash.
                        _emit_mapping_entry(key, val, indent + 2, step,
                                            lines)
            elif isinstance(item, list):
                if not item:
                    lines.append(pad + "- []")
                else:
                    lines.append(pad + "-")
                    _emit_yaml(item, indent + step, step, lines)
            else:
                lines.append("%s- %s" % (pad, yaml_scalar(item)))
    else:
        lines.append(pad + yaml_scalar(value))


def _emit_mapping_entry(key, item, indent, step, lines):
    """Emit one mapping entry at *indent* (used for nested mappings)."""
    pad = " " * indent
    rendered_key = yaml_key(key)
    if isinstance(item, dict):
        if not item:
            lines.append("%s%s: {}" % (pad, rendered_key))
        else:
            lines.append("%s%s:" % (pad, rendered_key))
            _emit_yaml(item, indent + step, step, lines)
    elif isinstance(item, list):
        if not item:
            lines.append("%s%s: []" % (pad, rendered_key))
        else:
            lines.append("%s%s:" % (pad, rendered_key))
            _emit_yaml(item, indent + step, step, lines)
    else:
        lines.append("%s%s: %s" % (pad, rendered_key, yaml_scalar(item)))


def _append_mapping_first(lines, pad, key, item, indent, step):
    """Emit the first entry of a sequence mapping on the dash line."""
    rendered_key = yaml_key(key)
    if isinstance(item, dict):
        if not item:
            lines.append("%s- %s: {}" % (pad, rendered_key))
        else:
            lines.append("%s- %s:" % (pad, rendered_key))
            # Nested block sits one step past the first key (dash + 2).
            _emit_yaml(item, indent + 2 + step, step, lines)
    elif isinstance(item, list):
        if not item:
            lines.append("%s- %s: []" % (pad, rendered_key))
        else:
            lines.append("%s- %s:" % (pad, rendered_key))
            _emit_yaml(item, indent + 2 + step, step, lines)
    else:
        lines.append("%s- %s: %s" % (pad, rendered_key, yaml_scalar(item)))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="json_pretty.py",
        description="Validate JSON and pretty-print, sort, compress, "
                    "or convert it to YAML.")
    parser.add_argument("file", nargs="?", default=None,
                        help="JSON file to read; omit or use - for stdin")
    parser.add_argument("--check", action="store_true",
                        help="only report whether the JSON is valid")
    parser.add_argument("--sort", action="store_true",
                        help="sort object keys alphabetically at every "
                             "level before output")
    parser.add_argument("--compress", "--minify", dest="compress",
                        action="store_true",
                        help="remove all whitespace outside strings")
    parser.add_argument("--yaml", action="store_true",
                        help="convert JSON to YAML instead of JSON output")
    parser.add_argument("--indent", type=int, default=2,
                        help="indent width for pretty-print and YAML "
                             "(1-8, default 2)")
    return parser


def run(argv=None, stdin_text=None):
    """Run the CLI. Returns an exit code; writes to stdout/stderr.

    *stdin_text* is a testing hook: when given, stdin is not read.
    """
    args = build_parser().parse_args(argv)
    if args.compress and args.yaml:
        print("Error: --compress and --yaml cannot be combined",
              file=sys.stderr)
        return 2
    if args.check and (args.compress or args.yaml):
        print("Error: --check cannot be combined with --compress or --yaml",
              file=sys.stderr)
        return 2
    if not 1 <= args.indent <= 8:
        print("Error: --indent must be between 1 and 8", file=sys.stderr)
        return 2

    if args.file is None or args.file == "-":
        if stdin_text is not None:
            text = stdin_text
        else:
            try:
                text = sys.stdin.read()
            except UnicodeDecodeError:
                print("Error: stdin is not valid UTF-8", file=sys.stderr)
                return 2
    else:
        try:
            with open(args.file, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            print("Error: cannot read %s: %s" % (args.file, exc.strerror
                                                 or exc),
                  file=sys.stderr)
            return 2
        except UnicodeDecodeError:
            print("Error: %s is not valid UTF-8" % args.file,
                  file=sys.stderr)
            return 2

    value, error = validate(text)
    if error is not None:
        print(format_error(text, error), file=sys.stderr)
        return 1

    if args.check:
        print("Valid JSON")
        return 0
    if args.sort:
        value = sort_value(value)
    if args.compress:
        # Compress the original text, not a re-serialization, so string
        # contents and literal spellings survive byte-for-byte. Sorting
        # cannot be expressed by a whitespace strip, so --sort --compress
        # re-serializes the sorted value compactly instead; that
        # combination is documented in README.
        if args.sort:
            output = json.dumps(value, separators=(",", ":"),
                                ensure_ascii=False)
        else:
            output = compress_json(text)
        print(output)
        return 0
    if args.yaml:
        print("\n".join(to_yaml(value, step=args.indent)))
        return 0
    print(json.dumps(value, indent=args.indent, ensure_ascii=False))
    return 0


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()

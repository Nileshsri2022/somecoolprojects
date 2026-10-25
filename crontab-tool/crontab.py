#!/usr/bin/env python3
"""crontab.py — decode, validate, explain and query cron expressions.

Build Your Own Crontab Tool (codingchallenges.fyi, slug
``challenge-cron``): Step 1 accept a five-field expression,
Step 2 validate it with an informative error, Step 3 translate
it into natural language. This build adds next-run computation,
matching against a datetime, and crontab-file listing on top of
the same parser.

Python 3 standard library only. Nothing here installs, edits
or reads the real system crontab; files are only read when
explicitly named on the command line (or stdin for ``list -``).

Usage:
    python3 crontab.py "0 9 * * 6 send-newsletter"   # explain (shorthand)
    python3 crontab.py explain "0 9 * * SAT"
    python3 crontab.py validate "61 * * * *"
    python3 crontab.py next "*/15 * * * *" [--from 2026-10-25T10:07] [--count 3]
    python3 crontab.py matches "0 9 * * 6" --at 2026-10-31T09:00
    python3 crontab.py list jobs.txt [--at ...] [--next 1]
"""

import argparse
import calendar
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = [
    "CronError", "CronExpression", "CronJob",
    "parse_expression", "parse_field", "parse_crontab_text",
    "next_runs", "describe",
]


class CronError(ValueError):
    """User-facing cron parse/validation error; names the field."""


_MONTH_NAMES = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_DOW_NAMES = {
    "SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6,
}
_MONTH_FULL = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]
_DOW_FULL = [
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday",
]

# (field name, lo, hi, names-or-None)
_FIELDS = (
    ("minute", 0, 59, None),
    ("hour", 0, 23, None),
    ("day of month", 1, 31, None),
    ("month", 1, 12, _MONTH_NAMES),
    ("day of week", 0, 6, _DOW_NAMES),
)

_SPECIALS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


_MONTH_FULL_NAMES = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5,
    "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
    "NOVEMBER": 11, "DECEMBER": 12,
}
_DOW_FULL_NAMES = {
    "SUNDAY": 0, "MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3,
    "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6,
}


def _resolve_value(token, field):
    """Resolve one numeric-or-name token to an int, or raise CronError."""
    name, lo, hi, names = field
    if token == "":
        raise CronError(f"{name}: empty value")
    if token.lstrip("-").isdigit():
        # Numeric values are valid in name fields too (e.g. month 1).
        value = int(token)
        if not lo <= value <= hi:
            raise CronError(f"{name}: value {value} out of range {lo}-{hi}")
        return value
    if names is not None:
        key = token.upper()
        # Abbreviations (JAN, SAT) and full names (JANUARY, SATURDAY).
        full_names = _MONTH_FULL_NAMES if names is _MONTH_NAMES else _DOW_FULL_NAMES
        if key in names:
            return names[key]
        if key in full_names:
            return full_names[key]
        raise CronError(f"{name}: unknown name {token!r}")
    raise CronError(f"{name}: invalid value {token!r} (expected a number or name)")


def _resolve_dow(value):
    """Day of week: 7 is Sunday on some systems -> normalise to 0."""
    return 0 if value == 7 else value


def parse_field(text, field):
    """Expand one field string to a frozenset of ints.

    Supports ``*``, lists (``1,15``), ranges (``1-5``) and steps
    (``*/15``, ``1-10/2``, ``5/15``). Raises CronError naming the
    field on any problem.
    """
    name, lo, hi, _names = field
    if text == "":
        raise CronError(f"{name}: empty field")
    if text in ("?", "L", "W") or "#" in text or text in ("LW",):
        raise CronError(
            f"{name}: {text!r} is not supported "
            "(?, L, W and # exist only in some cron implementations)")
    if any(ch not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
           "abcdefghijklmnopqrstuvwxyz*,/-" for ch in text):
        bad = next(ch for ch in text
                   if ch not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                   "abcdefghijklmnopqrstuvwxyz*,/-")
        raise CronError(f"{name}: unsupported character {bad!r}")
    # Day of week accepts 7 as Sunday even though the canonical
    # range is 0-6, so resolve dow values against a widened field
    # and normalise 7 -> 0 afterwards.
    resolve_field = field
    if name == "day of week":
        resolve_field = ("day of week", 0, 7, _DOW_NAMES)
        hi = 7
    values = set()
    for item in text.split(","):
        if item == "":
            raise CronError(f"{name}: empty item in list {text!r}")
        if "/" in item:
            base, step_text = item.split("/", 1)
            if step_text == "" or not step_text.isdigit():
                raise CronError(f"{name}: invalid step {step_text!r} in {item!r}")
            step = int(step_text)
            if step <= 0:
                raise CronError(f"{name}: step must be positive, got {step}")
        else:
            base, step = item, 1
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            first, last = base.split("-", 1)
            start = _resolve_value(first, resolve_field)
            end = _resolve_value(last, resolve_field)
            if start > end:
                raise CronError(
                    f"{name}: reversed range {base!r} ({start} > {end})")
        else:
            start = _resolve_value(base, resolve_field)
            # A bare value with a step means start..max, e.g. 5/15.
            end = hi if "/" in item else start
        for value in range(start, end + 1, step):
            if name == "day of week":
                value = _resolve_dow(value)
            values.add(value)
    return frozenset(values)


def _full_range(field):
    _, lo, hi, _ = field
    return frozenset(range(lo, hi + 1))


@dataclass(frozen=True)
class CronExpression:
    """A parsed five-field schedule (command optional)."""
    minutes: frozenset
    hours: frozenset
    days_of_month: frozenset
    months: frozenset
    days_of_week: frozenset
    raw_fields: tuple  # the five original field strings
    special: str = ""  # e.g. "@daily", "" for a plain expression
    command: str = ""
    reboot: bool = False

    @property
    def _sets(self):
        return (self.minutes, self.hours, self.days_of_month,
                self.months, self.days_of_week)

    def _restricted(self, values, field):
        return values != _full_range(field)

    def matches(self, dt):
        """True if dt (truncated to the minute) is a run time."""
        if self.reboot:
            return False
        dt = dt.replace(second=0, microsecond=0)
        if dt.minute not in self.minutes:
            return False
        if dt.hour not in self.hours:
            return False
        if dt.month not in self.months:
            return False
        dom_restricted = self._restricted(self.days_of_month, _FIELDS[2])
        dow_restricted = self._restricted(self.days_of_week, _FIELDS[4])
        dom_match = dt.day in self.days_of_month
        # Python: Monday=0..Sunday=6; cron: Sunday=0..Saturday=6.
        dow = (dt.weekday() + 1) % 7
        dow_match = dow in self.days_of_week
        if dom_restricted and dow_restricted:
            if not (dom_match or dow_match):
                return False
        elif dom_restricted:
            if not dom_match:
                return False
        elif dow_restricted:
            if not dow_match:
                return False
        return True

    def __str__(self):
        return " ".join(self.raw_fields)


def parse_expression(text, command=""):
    """Parse a schedule string (five fields, or @special) + optional command."""
    if text is None or not str(text).strip():
        raise CronError("empty cron expression")
    text = str(text).strip()
    tokens = text.split()
    if tokens[0].startswith("@"):
        special = tokens[0].lower()
        if special == "@reboot":
            rest = tokens[1:]
            return CronExpression(
                frozenset(), frozenset(), frozenset(), frozenset(),
                frozenset(), (special,), special=special,
                command=command or " ".join(rest), reboot=True)
        if special not in _SPECIALS:
            raise CronError(
                f"unknown special {tokens[0]!r} "
                f"(supported: {', '.join(sorted(_SPECIALS))}, @reboot)")
        expanded = _SPECIALS[special]
        expr = parse_expression(expanded)
        rest = tokens[1:]
        return CronExpression(
            expr.minutes, expr.hours, expr.days_of_month, expr.months,
            expr.days_of_week, expr.raw_fields, special=special,
            command=command or " ".join(rest))
    if len(tokens) < 5:
        raise CronError(
            f"expected 5 fields, got {len(tokens)}: {text!r}")
    if len(tokens) > 5:
        # 6th+ tokens are the command, not fields.
        fields, cmd = tokens[:5], " ".join(tokens[5:])
        if command:
            cmd = command
    else:
        fields, cmd = tokens, command
    sets = []
    for field_text, field in zip(fields, _FIELDS):
        sets.append(parse_field(field_text, field))
    return CronExpression(*sets, tuple(fields), command=cmd)


def _join_words(items):
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _field_phrase(values, field, word_fn, singular, plural):
    """Describe one expanded field set in words."""
    name, lo, hi, _ = field
    full = set(range(lo, hi + 1))
    if values == full:
        return None  # caller supplies the "every ..." wording
    ordered = sorted(values)
    if len(ordered) == 1:
        word = word_fn(ordered[0])
        return word if singular == "" else f"{singular} {word}"
    # Contiguous range?
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        body = f"{word_fn(ordered[0])} through {word_fn(ordered[-1])}"
    else:
        body = _join_words(word_fn(v) for v in ordered)
    return body if plural == "" else f"{plural} {body}"


def describe(expr):
    """Translate a parsed expression into natural language."""
    if expr.reboot:
        return "On system reboot."
    minutes, hours, dom, months, dow = expr._sets
    raw = expr.raw_fields

    def star_step(raw_text):
        # Step over the whole range, e.g. */5 -> every 5 minutes.
        # A stepped range (1-10/2) is not an "every N" phrase.
        if "/" in raw_text:
            base, step = raw_text.split("/", 1)
            if base == "*":
                return int(step)
        return None

    min_step, hour_step = star_step(raw[0]), star_step(raw[1])
    if min_step:
        min_phrase = f"every {min_step} minutes"
    elif minutes == _full_range(_FIELDS[0]):
        min_phrase = "every minute"
    else:
        min_phrase = _field_phrase(minutes, _FIELDS[0], str, "minute", "minutes")
    if hour_step:
        hour_phrase = f"every {hour_step} hours"
    elif hours == _full_range(_FIELDS[1]):
        hour_phrase = "every hour"
    else:
        hour_phrase = _field_phrase(
            hours, _FIELDS[1], lambda h: f"{h:02d}:00", "", "")

    if (minutes == _full_range(_FIELDS[0]) and hours == _full_range(_FIELDS[1])
            and dom == _full_range(_FIELDS[2]) and months == _full_range(_FIELDS[3])
            and dow == _full_range(_FIELDS[4])):
        return "At every minute, of every hour, every day."
    parts = [f"At {min_phrase}, {hour_phrase}"]
    if dom != _full_range(_FIELDS[2]):
        parts.append(_field_phrase(dom, _FIELDS[2], str, "on day", "on days"))
    if months != _full_range(_FIELDS[3]):
        parts.append(_field_phrase(
            months, _FIELDS[3], lambda m: _MONTH_FULL[m - 1], "in", "in"))
    if dow != _full_range(_FIELDS[4]):
        parts.append(_field_phrase(
            dow, _FIELDS[4], lambda d: _DOW_FULL[d], "on", "on"))
    if len(parts) == 1:
        parts[0] += ", every day"
    sentence = ", ".join(parts) + "."
    return sentence


def next_runs(expr, from_dt, count=3, max_years=5):
    """Next `count` run times strictly after `from_dt`.

    Raises CronError for @reboot and for schedules that never
    occur within `max_years` (e.g. 31 February).
    """
    if expr.reboot:
        raise CronError("@reboot has no scheduled run time")
    if count < 1:
        raise CronError("count must be at least 1")
    start = from_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = start + timedelta(days=365 * max_years + 2)
    runs, candidate = [], start
    while len(runs) < count:
        if candidate > limit:
            raise CronError(
                f"no run found within {max_years} year(s) "
                f"(schedule may never occur, e.g. 31 February)")
        if expr.matches(candidate):
            runs.append(candidate)
        candidate += timedelta(minutes=1)
    return runs


@dataclass
class CronJob:
    expression: CronExpression
    command: str
    lineno: int
    raw: str


import re as _re
_ENV_RE = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def parse_crontab_text(text):
    """Parse crontab file text -> (jobs, errors).

    Skips blanks, comments and env assignments. Errors are
    (lineno, line, message) triples; parsing continues after them.
    """
    jobs, errors = [], []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if _ENV_RE.match(line):
            continue
        try:
            expr = parse_expression(line)
        except CronError as exc:
            errors.append((lineno, raw_line, str(exc)))
            continue
        jobs.append(CronJob(expr, expr.command, lineno, raw_line))
    return jobs, errors


def _parse_datetime(text):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise CronError(
        f"invalid datetime {text!r} (expected YYYY-MM-DDTHH:MM)")


def _explain_output(expr):
    lines = [f"Expression: {expr}"]
    if expr.special:
        lines.append(f"Special: {expr.special}")
    if expr.reboot:
        lines.append("Runs: on system reboot")
    else:
        names = ("minute", "hour", "day of month", "month", "day of week")
        for label, values in zip(names, expr._sets):
            vals = " ".join(str(v) for v in sorted(values))
            lines.append(f"{label:<14} {vals}")
    lines.append(f"Description: {describe(expr)}")
    if expr.command:
        lines.append(f"Command: {expr.command}")
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare-expression shorthand: first arg is not a known subcommand.
    subcommands = {"explain", "validate", "next", "matches", "list"}
    if argv and argv[0] not in subcommands and not argv[0].startswith("-"):
        argv = ["explain"] + argv
    parser = argparse.ArgumentParser(
        prog="crontab",
        description="Decode, validate and query cron expressions.")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("explain", help="expand and describe an expression")
    p.add_argument("expression", nargs="+", help="cron expression / @special")
    p = sub.add_parser("validate", help="validate an expression")
    p.add_argument("expression", nargs="+")
    p = sub.add_parser("next", help="show next run times")
    p.add_argument("expression", nargs="+")
    p.add_argument("--from", dest="from_dt", default=None)
    p.add_argument("--count", type=int, default=3)
    p = sub.add_parser("matches", help="test an expression against a datetime")
    p.add_argument("expression", nargs="+")
    p.add_argument("--at", required=True)
    p = sub.add_parser("list", help="list jobs in a crontab file")
    p.add_argument("file", help="crontab file, or - for stdin")
    p.add_argument("--at", default=None)
    p.add_argument("--next", dest="next_count", type=int, default=0)

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_usage(sys.stderr)
        return 1
    try:
        if args.cmd in ("explain", "validate", "next", "matches"):
            expr = parse_expression(" ".join(args.expression))
        if args.cmd == "explain":
            print(_explain_output(expr))
            if not expr.reboot:
                ref = datetime.now()
                runs = next_runs(expr, ref, count=3)
                print("Next runs:")
                for run in runs:
                    print(f"  {run.strftime('%Y-%m-%d %H:%M %A')}")
            return 0
        if args.cmd == "validate":
            print(f"Valid: {describe(expr)}")
            return 0
        if args.cmd == "next":
            ref = _parse_datetime(args.from_dt) if args.from_dt else datetime.now()
            for run in next_runs(expr, ref, count=args.count):
                print(run.strftime("%Y-%m-%d %H:%M %A"))
            return 0
        if args.cmd == "matches":
            dt = _parse_datetime(args.at)
            print("yes" if expr.matches(dt) else "no")
            return 0 if expr.matches(dt) else 0
        if args.cmd == "list":
            if args.file == "-":
                text = sys.stdin.read()
            else:
                with open(args.file, "r", encoding="utf-8") as fh:
                    text = fh.read()
            jobs, errors = parse_crontab_text(text)
            at = _parse_datetime(args.at) if args.at else None
            for job in jobs:
                line = f"{job.lineno}: {job.expression}"
                if job.command:
                    line += f"  {job.command}"
                if at is not None:
                    line += f"  [due at {args.at}: {'yes' if job.expression.matches(at) else 'no'}]"
                if args.next_count and not job.expression.reboot:
                    try:
                        runs = next_runs(
                            job.expression, at or datetime.now(),
                            count=args.next_count)
                        line += "  [next: " + ", ".join(
                            r.strftime("%Y-%m-%d %H:%M") for r in runs) + "]"
                    except CronError as exc:
                        line += f"  [next: error: {exc}]"
                print(line)
            for lineno, raw, msg in errors:
                print(f"{lineno}: error: {msg} (line: {raw!r})", file=sys.stderr)
            return 0
    except CronError as exc:
        print(f"crontab: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"crontab: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

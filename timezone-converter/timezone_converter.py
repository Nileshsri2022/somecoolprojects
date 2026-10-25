#!/usr/bin/env python3
"""Time Zone Converter — CLI implementation of Coding Challenge #85.

Converts a time from a source timezone to one or more target timezones,
prints a 24-hour aligned table, sorts zones relative to the source, and
shows a highlighted time window in every zone. DST is handled by the
stdlib ``zoneinfo`` IANA database: the offset is computed for the actual
date being converted, never from a fixed abbreviation offset.

If the system tz database is absent, ``zoneinfo`` raises
``ZoneInfoNotFoundError``; this program turns that into a clear message
telling the user to install the ``tzdata`` package (``pip install tzdata``),
which ``zoneinfo`` then picks up automatically. No third-party package
is required when the system database is present.

Input time formats (``--time``):
  HH:MM            (today, in the source zone)
  HH:MM:SS         (today, in the source zone)
  YYYY-MM-DD HH:MM
  YYYY-MM-DD HH:MM:SS
  YYYY-MM-DDTHH:MM / YYYY-MM-DDTHH:MM:SS
  now              (current instant, converted from UTC)

Zone arguments accept an IANA name (``Europe/London``), a city substring
(``london`` -> ``Europe/London`` when unambiguous), or a common
abbreviation (``GMT``, ``EST``, ``CET``, ...). Abbreviations are
inherently ambiguous (e.g. IST = India / Israel / Ireland); the mapping
is documented in ABBREVIATIONS and ``--list`` shows what each maps to.
"""

import argparse
import sys
from datetime import datetime, time as dtime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
except ImportError:  # Python < 3.9, not expected here
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore
    available_timezones = None  # type: ignore

# Common abbreviations -> IANA zone. Deliberately small and documented:
# an abbreviation has no DST of its own, so it maps to a zone whose
# zoneinfo rules supply the correct offset (incl. DST) for the date.
# Ambiguous cases are resolved to the most common reading and flagged
# in the README/SPEC; prefer the IANA name for exactness.
ABBREVIATIONS = {
    "UTC": "UTC",
    "GMT": "Europe/London",  # GMT itself has no DST; London gives GMT in
    # winter and BST in summer, matching how the challenge uses GMT.
    "BST": "Europe/London",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "AKST": "America/Anchorage",
    "HST": "Pacific/Honolulu",
    "CET": "Europe/Paris",
    "CEST": "Europe/Paris",
    "EET": "Europe/Helsinki",
    "IST": "Asia/Kolkata",  # Ambiguous: also Israel/Ireland; see SPEC.
    "JST": "Asia/Tokyo",
    "AEST": "Australia/Sydney",
    "ACST": "Australia/Adelaide",
    "AWST": "Australia/Perth",
    "NZST": "Pacific/Auckland",
}


def resolve_zone(name):
    """Resolve a user-supplied zone spec to an IANA name.

    Accepts an exact IANA name, a case-insensitive abbreviation from
    ABBREVIATIONS, or a unique city substring (e.g. 'london',
    'new_york'). Raises ValueError with a helpful message otherwise.
    """
    if ZoneInfo is None:
        raise ValueError("zoneinfo is unavailable (requires Python 3.9+)")
    raw = name.strip()
    if not raw:
        raise ValueError("empty timezone")
    # Abbreviations FIRST, deliberately: tzdb itself ships zones named
    # CET, EST, MST, HST, ... with fixed or zone-specific rules, but a
    # user typing EST means US Eastern, which observes DST. An exact
    # IANA name that is not an abbreviation still matches below.
    upper = raw.upper()
    if upper in ABBREVIATIONS:
        return ABBREVIATIONS[upper]
    # Exact IANA name (case-sensitive as shipped).
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        pass
    # City substring, case-insensitive, matched against the part after '/'.
    lowered = raw.lower().replace(" ", "_")
    candidates = []
    try:
        zones = sorted(available_timezones())
    except Exception:
        zones = []
    for z in zones:
        city = z.split("/")[-1].lower()
        if city == lowered or lowered in city:
            candidates.append(z)
    # Prefer an exact city match over substring matches.
    exact = [z for z in candidates if z.split("/")[-1].lower() == lowered]
    if len(exact) == 1:
        return exact[0]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Deterministic disambiguation hint: list first few.
        raise ValueError(
            "ambiguous timezone %r; matches: %s (use a full IANA name)"
            % (name, ", ".join(candidates[:8]))
        )
    raise ValueError(
        "unknown timezone %r (use an IANA name like Europe/London, "
        "a city like london, or an abbreviation like CET)" % name
    )


def load_zone(name):
    """Resolve + load a ZoneInfo, with a tzdata hint on missing data."""
    iana = resolve_zone(name)
    try:
        return ZoneInfo(iana), iana
    except ZoneInfoNotFoundError:
        raise ValueError(
            "timezone database entry %r not found on this system; "
            "install system tzdata or run: pip install tzdata" % iana
        )


def parse_time(text, source_tz):
    """Parse --time text into an aware datetime in the source zone.

    'now' means the current instant. A bare HH:MM[:SS] uses today's date
    in the source zone (so DST for today applies, not UTC's date).
    """
    text = text.strip()
    if text.lower() == "now":
        return datetime.now(timezone.utc).astimezone(source_tz)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.replace(tzinfo=source_tz)
        except ValueError:
            continue
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(text, fmt).time()
            today = datetime.now(source_tz).date()
            return datetime.combine(today, t, tzinfo=source_tz)
        except ValueError:
            continue
    raise ValueError(
        "cannot parse time %r; use HH:MM, YYYY-MM-DD HH:MM, "
        "YYYY-MM-DDTHH:MM, or 'now'" % text
    )


def fmt_offset(dt):
    """Format a UTC offset as +HH:MM / -HH:MM."""
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "%s%02d:%02d" % (sign, total // 3600, (total % 3600) // 60)


def fmt_dt(dt):
    """'2026-03-29 09:30 +01:00 (CET)' style rendering."""
    abbr = dt.tzname() or ""
    suffix = " (%s)" % abbr if abbr else ""
    return "%s %s%s" % (dt.strftime("%Y-%m-%d %H:%M"), fmt_offset(dt), suffix)


def convert(source_dt, target_names):
    """Convert an aware source datetime to each target zone.

    Returns a list of (iana_name, aware_datetime) in argument order.
    """
    out = []
    for name in target_names:
        tz, iana = load_zone(name)
        out.append((iana, source_dt.astimezone(tz)))
    return out


def sort_relative(source_dt, target_names):
    """Sort zones relative to the source: negative offsets first.

    Order key: (offset_from_source, name). The source itself sorts at 0.
    Mirrors Step 2: negative-offset zones before the source, positive
    after it.
    """
    rows = []
    for name in target_names:
        tz, iana = load_zone(name)
        converted = source_dt.astimezone(tz)
        delta = (converted.utcoffset() or timedelta(0)) - (
            source_dt.utcoffset() or timedelta(0))
        rows.append((delta, iana, converted))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def day_table(first_zone_name, zones, date):
    """24-hour aligned table (Step 3).

    Rows are hours 0..23 of the FIRST listed zone on the given date;
    each column is that same instant rendered in another zone. Starting
    at 0:00 in the first zone is what aligns the rows; on a DST
    transition day a local hour may be skipped or repeated, which is
    preserved (see SPEC) rather than papered over.
    """
    first_tz, first_iana = load_zone(first_zone_name)
    loaded = [(first_iana, first_tz)]
    for name in zones:
        tz, iana = load_zone(name)
        loaded.append((iana, tz))
    rows = []
    for hour in range(24):
        base = datetime.combine(date, dtime(hour, 0), tzinfo=first_tz)
        rows.append([base.astimezone(tz) for _, tz in loaded])
    return [iana for iana, _ in loaded], rows


def window(source_dt, start_text, end_text, target_names):
    """Highlighted period (Step 4): start/end in source zone + per zone.

    start_text/end_text are HH:MM[:SS] on the source date (or full
    datetimes); an end earlier than the start is read as next-day.
    """
    src_tz = source_dt.tzinfo
    day = source_dt.date()

    def _parse(t):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(t, fmt).replace(tzinfo=src_tz)
            except ValueError:
                continue
        tpart = datetime.strptime(t, "%H:%M:%S" if t.count(":") == 2
                                  else "%H:%M").time()
        return datetime.combine(day, tpart, tzinfo=src_tz)

    try:
        start = _parse(start_text)
        end = _parse(end_text)
    except ValueError as exc:
        raise ValueError("cannot parse window time: %s" % exc)
    if end <= start:
        end = end + timedelta(days=1)
    out = []
    for name in target_names:
        tz, iana = load_zone(name)
        out.append((iana, start.astimezone(tz), end.astimezone(tz)))
    return start, end, out


def list_zones(query=None):
    """All IANA zones, optionally filtered by substring (city/region)."""
    try:
        zones = sorted(available_timezones())
    except Exception:
        zones = []
    if query:
        q = query.lower().replace(" ", "_")
        zones = [z for z in zones if q in z.lower()]
    return zones


def build_parser():
    p = argparse.ArgumentParser(
        prog="timezone_converter.py",
        description="Convert times between time zones (Coding Challenge #85).")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("convert", help="convert one time to other zones")
    c.add_argument("--from", dest="source", required=True,
                   help="source zone (IANA, city, or abbreviation)")
    c.add_argument("--time", required=True,
                   help="HH:MM, YYYY-MM-DD HH:MM, or 'now'")
    c.add_argument("--to", nargs="+", required=True,
                   help="one or more target zones")

    s = sub.add_parser("sort", help="list zones sorted relative to source")
    s.add_argument("--from", dest="source", required=True)
    s.add_argument("--time", default="now")
    s.add_argument("--to", nargs="+", required=True)

    t = sub.add_parser("table", help="24-hour aligned table (Step 3)")
    t.add_argument("--zones", nargs="+", required=True,
                   help="first zone anchors 0:00; rest are columns")
    t.add_argument("--date", default=None,
                   help="YYYY-MM-DD (default: today in the first zone)")

    w = sub.add_parser("window", help="highlight a period in every zone")
    w.add_argument("--from", dest="source", required=True)
    w.add_argument("--time", default=None,
                   help="reference date/time; date part anchors the window")
    w.add_argument("--start", required=True, help="HH:MM start in source zone")
    w.add_argument("--end", required=True, help="HH:MM end in source zone")
    w.add_argument("--to", nargs="+", required=True)

    l = sub.add_parser("list", help="list IANA zones / abbreviations")
    l.add_argument("query", nargs="?", default=None,
                   help="optional substring filter, e.g. london")
    l.add_argument("--abbreviations", action="store_true",
                   help="show the abbreviation -> IANA mapping instead")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "list":
            if args.abbreviations:
                for abbr, iana in sorted(ABBREVIATIONS.items()):
                    print("%-6s -> %s" % (abbr, iana))
                return 0
            for z in list_zones(args.query):
                print(z)
            return 0

        if args.cmd == "convert":
            src_tz, src_iana = load_zone(args.source)
            src_dt = parse_time(args.time, src_tz)
            print("%s: %s" % (src_iana, fmt_dt(src_dt)))
            for iana, conv in convert(src_dt, args.to):
                print("%s: %s" % (iana, fmt_dt(conv)))
            return 0

        if args.cmd == "sort":
            src_tz, src_iana = load_zone(args.source)
            src_dt = parse_time(args.time, src_tz)
            print("source %s: %s" % (src_iana, fmt_dt(src_dt)))
            for delta, iana, conv in sort_relative(src_dt, args.to):
                adelta = abs(delta)
                sign = "+" if delta >= timedelta(0) else "-"
                print("%s %s%02d:%02d  %s" % (
                    iana, sign, adelta.seconds // 3600,
                    (adelta.seconds % 3600) // 60, fmt_dt(conv)))
            return 0

        if args.cmd == "table":
            first_tz, _ = load_zone(args.zones[0])
            if args.date:
                try:
                    day = datetime.strptime(args.date, "%Y-%m-%d").date()
                except ValueError:
                    raise ValueError("--date must be YYYY-MM-DD")
            else:
                day = datetime.now(first_tz).date()
            headers, rows = day_table(args.zones[0], args.zones[1:], day)
            print("date in %s: %s (rows = hours 0-23 of first zone)" % (
                headers[0], day.isoformat()))
            print("%-6s" % "hour" + "".join("%-28s" % h for h in headers))
            for hour, row in enumerate(rows):
                print("%-6d" % hour + "".join(
                    "%-28s" % r.strftime("%Y-%m-%d %H:%M %Z") for r in row))
            return 0

        if args.cmd == "window":
            src_tz, src_iana = load_zone(args.source)
            ref = (parse_time(args.time, src_tz) if args.time
                   else datetime.now(src_tz))
            start, end, rows = window(ref, args.start, args.end, args.to)
            print("%s window: %s -> %s" % (src_iana, fmt_dt(start),
                                           fmt_dt(end)))
            for iana, s, e in rows:
                print("%s: %s -> %s" % (iana, fmt_dt(s), fmt_dt(e)))
            return 0
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Scheduling automation app (Coding Challenges #29).

A Calendly-style CLI over a local JSON store: consolidated
calendars (events carry a calendar label), one availability
window per weekday, free-slot computation, and booking with
an attendee. No live CalDAV/Google API: that step needs real
OAuth credentials, so it is documented as out of scope in
docs/SPEC.md rather than faked. Python 3 standard library only.

Usage: scheduler.py [--db PATH] <command> ...
See `scheduler.py --help` and README.md.
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_DB = "scheduler.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


class SchedulerError(ValueError):
    """A user-facing validation failure (exit 1, message on stderr)."""


def fresh_store():
    return {"next_id": 1, "availability": {}, "events": []}


def load_store(path):
    if not os.path.exists(path):
        return fresh_store()
    try:
        with open(path, encoding="utf-8") as fh:
            store = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise SchedulerError(f"cannot read store {path!r}: {exc}")
    if not isinstance(store, dict) or "events" not in store \
            or "availability" not in store or "next_id" not in store:
        raise SchedulerError(f"store {path!r} is not a scheduler store")
    return store


def save_store(path, store):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2)
        fh.write("\n")


def parse_datetime(text):
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise SchedulerError(
            f"bad datetime {text!r}: expected YYYY-MM-DDTHH:MM")


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise SchedulerError(f"bad date {text!r}: expected YYYY-MM-DD")


def parse_time(text):
    try:
        return time.fromisoformat(text)
    except ValueError:
        raise SchedulerError(f"bad time {text!r}: expected HH:MM")


def parse_weekday(text):
    day = text.strip().lower()[:3]
    if day not in WEEKDAYS:
        raise SchedulerError(
            f"bad weekday {text!r}: expected one of {', '.join(WEEKDAYS)}")
    return day


def parse_attendee(text):
    """CLI form 'Name <email>' -> {'name': ..., 'email': ...}."""
    match = re.match(r"^\s*([^<>]+?)\s*<([^<>]+)>\s*$", text)
    if not match:
        raise SchedulerError(
            f"bad attendee {text!r}: expected 'Name <email>'")
    name, email = match.group(1).strip(), match.group(2).strip()
    validate_attendee({"name": name, "email": email})
    return {"name": name, "email": email}


def validate_attendee(att):
    if not att.get("name"):
        raise SchedulerError("attendee needs a name")
    if not EMAIL_RE.match(att.get("email", "")):
        raise SchedulerError(f"bad attendee email {att.get('email')!r}")


def event_datetimes(event):
    return (datetime.fromisoformat(event["start"]),
            datetime.fromisoformat(event["end"]))


def overlaps(a_start, a_end, b_start, b_end):
    """Half-open overlap: back-to-back intervals do not overlap."""
    return a_start < b_end and b_start < a_end


def add_event(store, calendar, title, start, end, attendees=()):
    if end <= start:
        raise SchedulerError("event end must be after start")
    for att in attendees:
        validate_attendee(att)
    event = {
        "id": store["next_id"],
        "calendar": calendar,
        "title": title,
        "start": start.isoformat(timespec="minutes"),
        "end": end.isoformat(timespec="minutes"),
        "attendees": [dict(att) for att in attendees],
    }
    store["events"].append(event)
    store["next_id"] += 1
    return event


def cancel_event(store, event_id):
    for i, event in enumerate(store["events"]):
        if event["id"] == event_id:
            del store["events"][i]
            return event
    raise SchedulerError(f"no event with id {event_id}")


def set_availability(store, weekday, start, end):
    day = parse_weekday(weekday)
    if end <= start:
        raise SchedulerError("availability end must be after start")
    store["availability"][day] = [start.strftime("%H:%M"),
                                  end.strftime("%H:%M")]
    return day


def clear_availability(store, weekday):
    day = parse_weekday(weekday)
    store["availability"].pop(day, None)
    return day


def availability_window(store, day):
    """(start_time, end_time) for a weekday, or None."""
    window = store["availability"].get(day)
    if not window:
        return None
    return (time.fromisoformat(window[0]), time.fromisoformat(window[1]))


def is_free(store, start, end):
    """True iff [start, end) is inside that weekday's window and
    overlaps no event on any calendar."""
    if end <= start:
        return False
    day = WEEKDAYS[start.weekday()]
    window = availability_window(store, day)
    if window is None:
        return False
    win_start = datetime.combine(start.date(), window[0])
    win_end = datetime.combine(start.date(), window[1])
    if start < win_start or end > win_end:
        return False
    for event in store["events"]:
        ev_start, ev_end = event_datetimes(event)
        if overlaps(start, end, ev_start, ev_end):
            return False
    return True


def free_slots(store, day, duration_min, step_min=15):
    """Candidate starts at the day's window start, stepping by
    step_min, each lasting duration_min and passing is_free()."""
    if duration_min <= 0:
        raise SchedulerError("duration must be positive")
    if step_min <= 0:
        raise SchedulerError("step must be positive")
    weekday = WEEKDAYS[day.weekday()]
    window = availability_window(store, weekday)
    if window is None:
        return []
    win_start = datetime.combine(day, window[0])
    win_end = datetime.combine(day, window[1])
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)
    slots = []
    cursor = win_start
    while cursor + duration <= win_end:
        if is_free(store, cursor, cursor + duration):
            slots.append(cursor)
        cursor += step
    return slots


def book_event(store, calendar, title, start, duration_min,
               booker_name, booker_email):
    if duration_min <= 0:
        raise SchedulerError("duration must be positive")
    end = start + timedelta(minutes=duration_min)
    validate_attendee({"name": booker_name, "email": booker_email})
    if not is_free(store, start, end):
        raise SchedulerError(
            "requested slot is not free (outside availability "
            "or overlapping an existing event)")
    return add_event(store, calendar, title, start, end,
                     [{"name": booker_name, "email": booker_email}])


def list_events(store, calendar=None, from_date=None, to_date=None):
    events = sorted(store["events"],
                    key=lambda e: (e["start"], e["id"]))
    if calendar is not None:
        events = [e for e in events if e["calendar"] == calendar]
    if from_date is not None:
        events = [e for e in events
                  if datetime.fromisoformat(e["start"]).date() >= from_date]
    if to_date is not None:
        events = [e for e in events
                  if datetime.fromisoformat(e["start"]).date() <= to_date]
    return events


def format_event(event):
    attendees = ", ".join(
        f"{a['name']} <{a['email']}>" for a in event["attendees"])
    suffix = f" [{attendees}]" if attendees else ""
    return (f"{event['id']} [{event['calendar']}] {event['title']} "
            f"{event['start']} -> {event['end']}{suffix}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Scheduling automation app: availability windows, "
                    "free slots, and bookings over a local JSON store.")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="store path (default: scheduler.json in cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-event", help="add an existing calendar event")
    p.add_argument("--calendar", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DDTHH:MM")
    p.add_argument("--end", required=True, help="YYYY-MM-DDTHH:MM")
    p.add_argument("--attendee", action="append", default=[],
                   help="repeatable: 'Name <email>'")

    p = sub.add_parser("list-events", help="list events, sorted by start")
    p.add_argument("--calendar")
    p.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", help="YYYY-MM-DD")

    p = sub.add_parser("set-availability",
                       help="set one weekday's window, e.g. mon 08:00 17:30")
    p.add_argument("weekday")
    p.add_argument("start", help="HH:MM")
    p.add_argument("end", help="HH:MM")

    p = sub.add_parser("clear-availability", help="remove a weekday's window")
    p.add_argument("weekday")

    sub.add_parser("show-availability", help="show all weekday windows")

    p = sub.add_parser("free-slots", help="list free slots for a date")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--duration", required=True, type=int,
                   help="slot length in minutes")
    p.add_argument("--step", type=int, default=15,
                   help="candidate spacing in minutes (default 15)")

    p = sub.add_parser("book", help="book a free slot with an attendee")
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DDTHH:MM")
    p.add_argument("--duration", required=True, type=int,
                   help="length in minutes")
    p.add_argument("--name", required=True, help="booker's name")
    p.add_argument("--email", required=True, help="booker's email")
    p.add_argument("--calendar", default="work",
                   help="calendar to book into (default: work)")

    p = sub.add_parser("cancel-event", help="delete an event by id")
    p.add_argument("event_id", type=int)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        store = load_store(args.db)
        if args.command == "add-event":
            event = add_event(
                store, args.calendar, args.title,
                parse_datetime(args.start), parse_datetime(args.end),
                [parse_attendee(a) for a in args.attendee])
            save_store(args.db, store)
            print(format_event(event))
        elif args.command == "list-events":
            events = list_events(
                store, args.calendar,
                parse_date(args.from_date) if args.from_date else None,
                parse_date(args.to_date) if args.to_date else None)
            for event in events:
                print(format_event(event))
        elif args.command == "set-availability":
            day = set_availability(store, args.weekday,
                                   parse_time(args.start),
                                   parse_time(args.end))
            save_store(args.db, store)
            print(f"{day}: {args.start} - {args.end}")
        elif args.command == "clear-availability":
            day = clear_availability(store, args.weekday)
            save_store(args.db, store)
            print(f"{day}: cleared")
        elif args.command == "show-availability":
            for day in WEEKDAYS:
                window = store["availability"].get(day)
                print(f"{day}: "
                      f"{window[0]} - {window[1]}" if window
                      else f"{day}: (unavailable)")
        elif args.command == "free-slots":
            slots = free_slots(store, parse_date(args.date),
                               args.duration, args.step)
            if not slots:
                print("(no free slots)")
            for slot in slots:
                print(slot.strftime("%Y-%m-%dT%H:%M"))
        elif args.command == "book":
            event = book_event(store, args.calendar, args.title,
                               parse_datetime(args.start), args.duration,
                               args.name, args.email)
            save_store(args.db, store)
            print(format_event(event))
        elif args.command == "cancel-event":
            event = cancel_event(store, args.event_id)
            save_store(args.db, store)
            print(f"cancelled {format_event(event)}")
    except SchedulerError as exc:
        print(f"scheduler: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

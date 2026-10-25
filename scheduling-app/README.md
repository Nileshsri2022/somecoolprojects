# scheduling-app — Build Your Own Scheduling Automation App

Coding Challenges #29, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A Calendly-style CLI over a local JSON store: set a
per-weekday availability window, add events from one or
more calendars, list the free slots for a date, and book
one with a named attendee. Bookings are refused unless
the slot is free by exactly the same rules the slot
listing uses, so double-booking is impossible.

## Usage

```sh
python3 scheduler.py set-availability mon 08:00 17:30
python3 scheduler.py set-availability tue 08:00 17:30
# ... repeat for wed thu fri; weekends have no window

python3 scheduler.py add-event --calendar work --title Standup \
  --start 2026-10-26T09:00 --end 2026-10-26T10:00

python3 scheduler.py free-slots --date 2026-10-26 --duration 60 --step 60
# 2026-10-26T08:00
# 2026-10-26T10:00
# ... (09:00 is taken by Standup)

python3 scheduler.py book --title Interview --start 2026-10-26T10:00 \
  --duration 60 --name Bob --email bob@example.com
python3 scheduler.py list-events
python3 scheduler.py cancel-event 2
```

The store defaults to `scheduler.json` in the working
directory; pass `--db PATH` (before the subcommand) to
use another file. All subcommands: `add-event`,
`list-events` (`--calendar`, `--from`, `--to`),
`set-availability`, `clear-availability`,
`show-availability`, `free-slots` (`--date`,
`--duration`, `--step`, default 15), `book`, `cancel-event`.
Times are naive local times (`YYYY-MM-DDTHH:MM`,
availability `HH:MM`); overlap is half-open, so
back-to-back events do not conflict.

## Deliberate scope limit

The challenge page's Steps 1–2 (Google CalDAV OAuth and
live event fetching) need real Google credentials, so
they are NOT implemented and no credentials are invented:
`add-event` populates the same Event type a CalDAV
adapter would feed in. The page also does not specify
recurrence or reminders, so there are none. Full details
in `docs/SPEC.md`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover parsing/overlap, availability, free slots
(including partial overlaps and window edges), booking
rules and the double-booking guard, consolidated calendars
(a `personal` event blocks a `work` booking), cancel/id
handling, store round-trips, and CLI end-to-end runs —
all in temp directories, with no network and no reliance
on the current time.

## Files

- `scheduler.py` — store, core (overlap / free slots /
  booking), argparse CLI. Stdlib only.
- `docs/SPEC.md` — challenge steps, data model, scope limits.
- `docs/DESIGN.md` — assumptions and pipeline.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_scheduler.py` — the test suite (19 tests).

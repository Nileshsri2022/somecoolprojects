# scheduling-app — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Assumptions

1. One file is enough. The whole app is a store (load/save
   JSON), a few pure functions over events/availability, and
   an argparse CLI that prints them. No classes beyond plain
   dicts: an Event is a dict, so JSON round-trips with no
   serialiser code.
2. Naive local datetimes. The page never mentions timezones,
   and adding zone handling would be speculative complexity.
   All comparisons are naive `datetime` comparisons; the user
   is responsible for entering times in one consistent zone.
   Documented, not hidden.
3. Availability is one window per weekday, not several. The
   page's example is a single window ("08:00 to 17:30 Monday
   to Friday"). Multiple windows per day (e.g. lunch breaks)
   are representable instead as blocking events, which the
   overlap rule already handles — so no second data shape.
4. Booking and free-slot checks share one function. `book`
   must never accept a slot `free_slots` would not list, so
   both go through `is_free()`; the only difference is that
   `book` then appends the event. This removes a whole class
   of "listed as free but booking failed" (or vice versa) bugs.
5. IDs are small ints from a `next_id` counter in the store,
   not UUIDs. They are human-readable in CLI output, stable
   across loads, and never reused after a cancel.
6. The store is rewritten whole on every mutation (load,
   mutate, save). The file is small by design; no locking,
   no partial writes beyond writing to the same path. A
   corrupt store fails loudly instead of being silently reset.

## Pipeline

```
argv -> argparse -> command function
  -> load_store(path)          dict (or fresh store if missing)
  -> pure core: overlaps(), free_slots(), is_free()
  -> mutate (add/book/cancel/set-availability) or print
  -> save_store(path)          only on mutation, only on success
```

Core functions (all importable, all tested without the CLI):

- `parse_datetime(text)` / `parse_time(text)` — strict
  `fromisoformat` / `strptime` wrappers raising `ValueError`
  with a readable message.
- `overlaps(a_start, a_end, b_start, b_end)` — half-open
  interval test, so back-to-back events are fine.
- `free_slots(store, date, duration_min, step_min)` — the
  Step 4 algorithm: weekday window, step-aligned candidates,
  overlap filter across all calendars.
- `is_free(store, start, end)` — window containment + no
  overlap; used by both `free_slots` output sanity and `book`.
- `add_event(store, ...)` / `book_event(store, ...)` /
  `cancel_event(store, id)` / `set_availability(store, ...)`
  — validate, then mutate the dict; they never touch disk,
  so tests can drive them with an in-memory store and a fake
  clock is unnecessary (nothing here reads "now" — every
  date is supplied by the caller, which is what makes the
  timing tests deterministic without injection).

## CLI surface

```
scheduler.py [--db PATH] <command> ...
  add-event   --calendar C --title T --start ISO --end ISO
              [--attendee "Name <email>"]...   (repeatable)
  list-events [--calendar C] [--from DATE] [--to DATE]
  set-availability DAY HH:MM HH:MM
  clear-availability DAY
  show-availability
  free-slots --date DATE --duration MIN [--step MIN]
  book --title T --start ISO --duration MIN
       --name NAME --email EMAIL [--calendar C]
  cancel-event ID
```

`--db` is a global flag before the subcommand. Default db is
`scheduler.json` in the current working directory. Output is
one line per event/slot, human-readable, no colours, so it
pipes and greps cleanly. Attendee CLI form is
`Name <email>`; the library form is a `{"name", "email"}`
dict — parsing is a tiny split on `<`/`>`, validated.

## What was deliberately not built

- CalDAV/OAuth client (see SPEC.md out-of-scope #1).
- Recurrence, reminders, invites by email (SPEC.md #2).
- Multi-window availability, timezones, update-in-place —
  each covered by an existing mechanism (blocking events,
  consistent naive input, cancel + re-add) rather than new
  surface.

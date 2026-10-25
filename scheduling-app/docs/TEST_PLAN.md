# scheduling-app — TEST PLAN

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests use `tempfile.TemporaryDirectory` for the store;
no test touches the real working directory, another project,
or the network. No test sleeps or depends on the current
time: every date is supplied explicitly, so no fake clock
is needed (nothing in the code reads "now").

## Library-level (tests/test_scheduler.py, TestCore)

- Datetime/time parsing: valid ISO accepted; garbage and
  impossible times rejected.
- Overlap: overlapping, contained, touching (not overlap),
  disjoint, multi-day-spanning event vs a slot.
- add_event validation: end <= start rejected; bad attendee
  email (no `@`) rejected; good event stored with an id and
  the right calendar label.
- Availability: set stores the window; set with end <= start
  rejected; clear removes it; unknown weekday rejected.
- free_slots: Mon–Fri 08:00–17:30, 60-min duration, 60-min
  step gives the expected slot list; a blocking event removes
  exactly the slots it overlaps (including a partially
  overlapping slot at the window edge); a day with no window
  (Saturday) gives no slots; slots never cross the window end.
- is_free/book rules: booking inside the window with no
  conflict succeeds and appears in list; booking overlapping
  an existing event fails; booking outside the window fails;
  booking on a no-window day fails; a booking made via the
  library is then no longer free (second identical booking
  fails) — this is the double-booking guard.
- Consolidated calendars: an event on `personal` blocks a
  `work` booking at the same time (all calendars consulted).
- cancel: removes the event; unknown id raises; ids are not
  reused after a cancel.
- Persistence: save then load round-trips events,
  availability, and the id counter.

## CLI-level (TestCLI, same file, via subprocess)

- End-to-end happy path in a temp dir: set availability,
  add a work event, `free-slots` shows the gap, `book`
  succeeds, `list-events` shows both events, `cancel-event`
  removes the booking.
- CLI failures exit non-zero with stderr text: booking a
  busy slot, booking outside availability, bad datetime,
  cancelling an unknown id.
- Default-db behaviour is NOT tested against the real cwd
  (that would pollute it); CLI tests always pass `--db` into
  the temp dir, and the README documents the default.

## Manual spot-check (done once by hand, not in the suite)

- `python3 scheduler.py --help` lists all subcommands.
- A Saturday `free-slots` run prints `(no free slots)`.

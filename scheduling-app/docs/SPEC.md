# scheduling-app — SPEC

Source: Coding Challenges #29, "Build Your Own Scheduling
Automation App" (think Calendly / Cal.com / TidyCal).

- Challenge page (read first, 2026-10-25):
  https://codingchallenges.fyi/challenges/challenge-scheduler
  Slug used: `challenge-scheduler`. Note: the obvious guess
  `challenge-scheduling-automation-app` was NOT used — the
  real slug was found via the site's `tags/api` listing, which
  links to `challenge-scheduler`. The Substack mirror of the
  same challenge (#29) carries identical steps.
- The page's steps, mapped to this build:

| Page step | What it asks | This build |
|---|---|---|
| Step 0 | Pick a stack; CLI is an allowed choice | Python 3 stdlib CLI, `scheduler.py` |
| Step 1 | Authenticate with Google's CalDAV API (OAuth 2.0, scope `https://www.googleapis.com/auth/calendar`) | OUT OF SCOPE — see below. No credentials are invented, stored, or requested. |
| Step 2 | GET a list of events; define an Event data type | Local events in a JSON store; `Event` = id, calendar, title, start, end, attendees |
| Step 3 | Consolidated calendar: merge work + personal calendars; Event records which calendar it came from | Events carry a `calendar` label (e.g. `work`, `personal`); free-slot and booking checks consider ALL calendars |
| Step 4 | Per-weekday availability window (e.g. 08:00–17:30 Mon–Fri, none at weekends); combine with events to find free time; booker picks a slot free for at least a chosen duration | `set-availability` / `free-slots --duration` exactly as described |
| Step 5 | Create an event including attendees (booker's name + email) | `book` creates an event with one attendee (name + email) after verifying the slot is free |

## Out of scope (deliberate, documented divergences)

1. **No live CalDAV / Google Calendar API.** Step 1–2's OAuth
   flow and the `GET https://apidata.googleusercontent.com/
   caldav/v2/<cal_id>/events` call need a real Google account,
   OAuth client id/secret, and a token exchange. Building that
   would mean inventing credentials or shipping an unauthenticated
   stub that pretends to talk to Google. Instead the calendar
   store is local JSON, and `add-event` is the stand-in for
   "events pulled from a calendar": it populates the same Event
   type the rest of the pipeline consumes. A future CalDAV
   adapter would only need to translate CalDAV events into
   this Event shape and call the same free-slot/book code.
2. **No recurrence, no reminders, no web UI, no email sending.**
   The page does not specify recurrence rules or reminders;
   Step 5 only requires attendees on the created event, so no
   invite is actually sent. Adding cron-style recurrence or
   SMTP would be speculative (ponytail: nothing speculative).

## Data model

- Store: one JSON file, default `scheduler.json` in the working
  directory, overridable with `--db PATH` (never written into
  another project's directory; tests use temp directories).
  Shape: `{"next_id": int, "availability": {weekday: [start,
  end]}, "events": [Event, ...]}`.
- Weekday keys: `mon tue wed thu fri sat sun`.
- Times: naive local times. Datetimes `YYYY-MM-DDTHH:MM`
  (seconds accepted on input, normalised to minutes on output
  only where stored verbatim — stored exactly as parsed ISO).
  Availability times `HH:MM`, 24-hour.
- Event: `{"id": int, "calendar": str, "title": str,
  "start": ISO, "end": ISO, "attendees": [{"name", "email"}]}`.
  `end` must be strictly after `start`; attendees' emails must
  contain `@` (a shape check only, not deliverability).

## Behaviour

- Overlap: `[s1, e1)` overlaps `[s2, e2)` iff
  `s1 < e2 and s2 < e1`. Back-to-back events do not overlap.
- Free slots for a date: take that weekday's availability
  window (none configured = no slots); candidate starts begin
  at the window start and advance by `--step` minutes (default
  15); a candidate `[t, t+duration)` is free iff it lies
  entirely inside the window and overlaps no event on any
  calendar. Slots are listed in chronological order.
- Booking: `book` refuses (exit 1, message on stderr) unless
  the requested slot is free by exactly the free-slot rules
  above — i.e. it must sit inside that weekday's availability
  window and overlap nothing. A successful booking appends an
  event to the chosen calendar (default `work`) with the booker
  as its sole attendee.
- `list-events` sorts by start, then id; `--calendar` filters;
  `--from`/`--to` filter on event start (inclusive dates).
- Deleting: `cancel-event ID` removes that event, erroring if
  the id is unknown. There is no update command: cancel +
  re-add is the minimum that covers it.
- Errors (bad datetime, end <= start, bad availability range,
  unknown id, booking a busy/out-of-window slot, malformed
  JSON store) print to stderr and exit non-zero; nothing is
  written on a failed command.

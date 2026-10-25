#!/usr/bin/env python3
"""Tests for scheduler.py: library core + CLI, temp dirs only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler
from scheduler import (
    SchedulerError, add_event, availability_window, book_event,
    cancel_event, clear_availability, free_slots, is_free,
    list_events, load_store, overlaps, parse_attendee,
    parse_datetime, parse_time, save_store, set_availability,
)

# 2026-10-26 is a Monday; 2026-10-31 is a Saturday.
MONDAY = date(2026, 10, 26)
SATURDAY = date(2026, 10, 31)


def store_with_weekday_window():
    store = scheduler.fresh_store()
    for day in ("mon", "tue", "wed", "thu", "fri"):
        set_availability(store, day, time(8, 0), time(17, 30))
    return store


def dt(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute))


class TestParsingAndOverlap(unittest.TestCase):
    def test_parse_datetime_valid(self):
        self.assertEqual(parse_datetime("2026-10-26T09:30"),
                         datetime(2026, 10, 26, 9, 30))

    def test_parse_datetime_bad(self):
        for bad in ("tomorrow", "2026-13-01T09:00", "2026-10-26 9am"):
            with self.assertRaises(SchedulerError, msg=bad):
                parse_datetime(bad)

    def test_parse_time_bad(self):
        with self.assertRaises(SchedulerError):
            parse_time("25:00")

    def test_overlap_cases(self):
        a = (dt(MONDAY, 9), dt(MONDAY, 10))
        self.assertTrue(overlaps(*a, dt(MONDAY, 9, 30), dt(MONDAY, 10, 30)))
        self.assertTrue(overlaps(*a, dt(MONDAY, 8), dt(MONDAY, 11)))
        self.assertFalse(overlaps(*a, dt(MONDAY, 10), dt(MONDAY, 11)))
        self.assertFalse(overlaps(*a, dt(MONDAY, 8), dt(MONDAY, 9)))
        self.assertFalse(overlaps(*a, dt(MONDAY, 11), dt(MONDAY, 12)))

    def test_parse_attendee(self):
        self.assertEqual(parse_attendee("Ada Lovelace <ada@example.com>"),
                         {"name": "Ada Lovelace", "email": "ada@example.com"})
        for bad in ("Ada", "Ada <not-an-email>", "Ada <a@b> extra <c@d>"):
            with self.assertRaises(SchedulerError, msg=bad):
                parse_attendee(bad)


class TestEventsAndAvailability(unittest.TestCase):
    def test_add_event_validation(self):
        store = scheduler.fresh_store()
        with self.assertRaises(SchedulerError):
            add_event(store, "work", "Bad", dt(MONDAY, 10), dt(MONDAY, 9))
        with self.assertRaises(SchedulerError):
            add_event(store, "work", "Bad", dt(MONDAY, 9), dt(MONDAY, 9))
        with self.assertRaises(SchedulerError):
            add_event(store, "work", "Bad", dt(MONDAY, 9), dt(MONDAY, 10),
                      [{"name": "X", "email": "no-at-sign"}])
        event = add_event(store, "personal", "Dentist",
                          dt(MONDAY, 9), dt(MONDAY, 10),
                          [{"name": "Ada", "email": "ada@example.com"}])
        self.assertEqual(event["id"], 1)
        self.assertEqual(event["calendar"], "personal")
        self.assertEqual(len(store["events"]), 1)

    def test_availability_set_clear_bad(self):
        store = scheduler.fresh_store()
        self.assertEqual(set_availability(store, "mon", time(8, 0),
                                          time(17, 30)), "mon")
        self.assertEqual(availability_window(store, "mon"),
                         (time(8, 0), time(17, 30)))
        with self.assertRaises(SchedulerError):
            set_availability(store, "tue", time(17, 30), time(8, 0))
        with self.assertRaises(SchedulerError):
            set_availability(store, "funday", time(8, 0), time(9, 0))
        clear_availability(store, "mon")
        self.assertIsNone(availability_window(store, "mon"))

    def test_cancel_and_id_not_reused(self):
        store = scheduler.fresh_store()
        e1 = add_event(store, "work", "A", dt(MONDAY, 9), dt(MONDAY, 10))
        e2 = add_event(store, "work", "B", dt(MONDAY, 11), dt(MONDAY, 12))
        cancel_event(store, e1["id"])
        self.assertEqual([e["id"] for e in store["events"]], [e2["id"]])
        with self.assertRaises(SchedulerError):
            cancel_event(store, 999)
        e3 = add_event(store, "work", "C", dt(MONDAY, 13), dt(MONDAY, 14))
        self.assertEqual(e3["id"], 3)  # counter advanced, not reused

    def test_list_events_sort_and_filter(self):
        store = scheduler.fresh_store()
        add_event(store, "work", "Late", dt(MONDAY, 14), dt(MONDAY, 15))
        add_event(store, "personal", "Early", dt(MONDAY, 9), dt(MONDAY, 10))
        titles = [e["title"] for e in list_events(store)]
        self.assertEqual(titles, ["Early", "Late"])
        self.assertEqual([e["title"] for e in
                          list_events(store, calendar="personal")], ["Early"])
        self.assertEqual(list_events(store, from_date=date(2026, 10, 27)), [])
        self.assertEqual(len(list_events(store, to_date=MONDAY)), 2)


class TestFreeSlotsAndBooking(unittest.TestCase):
    def test_free_slots_weekday_no_events(self):
        store = store_with_weekday_window()
        slots = free_slots(store, MONDAY, 60, step_min=60)
        # 08:00..16:00 starts, last slot ends 17:00 <= 17:30 window end.
        self.assertEqual([s.strftime("%H:%M") for s in slots],
                         ["08:00", "09:00", "10:00", "11:00", "12:00",
                          "13:00", "14:00", "15:00", "16:00"])

    def test_free_slots_blocked_by_event(self):
        store = store_with_weekday_window()
        add_event(store, "work", "Standup", dt(MONDAY, 9), dt(MONDAY, 10))
        slots = free_slots(store, MONDAY, 60, step_min=60)
        self.assertNotIn(dt(MONDAY, 9), slots)
        self.assertIn(dt(MONDAY, 10), slots)
        # Partial overlap also kills the slot: 09:30-10:30 event.
        store2 = store_with_weekday_window()
        add_event(store2, "work", "Call", dt(MONDAY, 9, 30), dt(MONDAY, 10, 30))
        slots2 = free_slots(store2, MONDAY, 60, step_min=30)
        self.assertNotIn(dt(MONDAY, 9, 30), slots2)
        self.assertNotIn(dt(MONDAY, 10), slots2)  # 10:00-11:00 overlaps
        self.assertIn(dt(MONDAY, 10, 30), slots2)

    def test_free_slots_no_window_day(self):
        store = store_with_weekday_window()
        self.assertEqual(free_slots(store, SATURDAY, 60), [])

    def test_free_slots_never_cross_window_end(self):
        store = store_with_weekday_window()
        slots = free_slots(store, MONDAY, 60, step_min=15)
        for slot in slots:
            self.assertLessEqual(slot + timedelta(minutes=60),
                                 dt(MONDAY, 17, 30))

    def test_consolidated_calendars_block_booking(self):
        # A personal event blocks a work booking: all calendars count.
        store = store_with_weekday_window()
        add_event(store, "personal", "Dentist", dt(MONDAY, 9), dt(MONDAY, 10))
        with self.assertRaises(SchedulerError):
            book_event(store, "work", "Interview", dt(MONDAY, 9), 60,
                       "Bob", "bob@example.com")
        self.assertFalse(is_free(store, dt(MONDAY, 9), dt(MONDAY, 10)))
        self.assertTrue(is_free(store, dt(MONDAY, 10), dt(MONDAY, 11)))

    def test_booking_rules(self):
        store = store_with_weekday_window()
        event = book_event(store, "work", "Interview", dt(MONDAY, 10), 60,
                           "Bob", "bob@example.com")
        self.assertEqual(event["attendees"],
                         [{"name": "Bob", "email": "bob@example.com"}])
        # Double booking the same slot fails.
        with self.assertRaises(SchedulerError):
            book_event(store, "work", "Again", dt(MONDAY, 10), 60,
                       "Carol", "carol@example.com")
        # Outside the window fails, as does a no-window day.
        with self.assertRaises(SchedulerError):
            book_event(store, "work", "Early", dt(MONDAY, 7), 60,
                       "Bob", "bob@example.com")
        with self.assertRaises(SchedulerError):
            book_event(store, "work", "Weekend", dt(SATURDAY, 10), 60,
                       "Bob", "bob@example.com")
        # Bad booker email fails, and nothing was added by failures.
        with self.assertRaises(SchedulerError):
            book_event(store, "work", "Bad", dt(MONDAY, 12), 60,
                       "Bob", "not-an-email")
        self.assertEqual(len(store["events"]), 1)

    def test_persistence_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.json")
            store = store_with_weekday_window()
            add_event(store, "work", "Standup", dt(MONDAY, 9), dt(MONDAY, 10))
            save_store(path, store)
            loaded = load_store(path)
            self.assertEqual(loaded, store)
            self.assertEqual(loaded["next_id"], 2)
            # Missing file loads fresh; corrupt file fails loudly.
            self.assertEqual(load_store(os.path.join(tmp, "none.json")),
                             scheduler.fresh_store())
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w") as fh:
                fh.write("{not json")
            with self.assertRaises(SchedulerError):
                load_store(bad)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "sched.json")
        self.script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scheduler.py")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, self.script, "--db", self.db, *args],
            capture_output=True, text=True)

    def test_end_to_end(self):
        self.assertEqual(self.cli("set-availability", "mon",
                                  "08:00", "17:30").returncode, 0)
        self.assertEqual(self.cli(
            "add-event", "--calendar", "work", "--title", "Standup",
            "--start", "2026-10-26T09:00",
            "--end", "2026-10-26T10:00").returncode, 0)
        slots = self.cli("free-slots", "--date", "2026-10-26",
                         "--duration", "60", "--step", "60")
        self.assertEqual(slots.returncode, 0)
        self.assertIn("2026-10-26T08:00", slots.stdout)
        self.assertNotIn("2026-10-26T09:00", slots.stdout)
        booked = self.cli("book", "--title", "Interview",
                          "--start", "2026-10-26T10:00", "--duration", "60",
                          "--name", "Bob", "--email", "bob@example.com")
        self.assertEqual(booked.returncode, 0)
        self.assertIn("Bob <bob@example.com>", booked.stdout)
        listing = self.cli("list-events")
        self.assertIn("Standup", listing.stdout)
        self.assertIn("Interview", listing.stdout)
        cancelled = self.cli("cancel-event", "2")
        self.assertEqual(cancelled.returncode, 0)
        listing2 = self.cli("list-events")
        self.assertIn("Standup", listing2.stdout)
        self.assertNotIn("Interview", listing2.stdout)
        # Store file is valid JSON with both remaining pieces.
        with open(self.db) as fh:
            data = json.load(fh)
        self.assertEqual(data["availability"]["mon"], ["08:00", "17:30"])
        self.assertEqual(len(data["events"]), 1)

    def test_cli_failures(self):
        self.cli("set-availability", "mon", "08:00", "17:30")
        self.cli("add-event", "--calendar", "work", "--title", "Busy",
                 "--start", "2026-10-26T09:00", "--end", "2026-10-26T10:00")
        busy = self.cli("book", "--title", "Clash",
                        "--start", "2026-10-26T09:30", "--duration", "60",
                        "--name", "Bob", "--email", "bob@example.com")
        self.assertNotEqual(busy.returncode, 0)
        self.assertIn("not free", busy.stderr)
        outside = self.cli("book", "--title", "Early",
                           "--start", "2026-10-26T07:00", "--duration", "60",
                           "--name", "Bob", "--email", "bob@example.com")
        self.assertNotEqual(outside.returncode, 0)
        bad = self.cli("add-event", "--calendar", "work", "--title", "Bad",
                       "--start", "tomorrow", "--end", "2026-10-26T10:00")
        self.assertNotEqual(bad.returncode, 0)
        unknown = self.cli("cancel-event", "42")
        self.assertNotEqual(unknown.returncode, 0)
        self.assertIn("no event", unknown.stderr)
        saturday = self.cli("free-slots", "--date", "2026-10-31",
                            "--duration", "60")
        self.assertEqual(saturday.returncode, 0)
        self.assertIn("(no free slots)", saturday.stdout)

    def test_show_availability_cli(self):
        self.cli("set-availability", "mon", "08:00", "17:30")
        out = self.cli("show-availability")
        self.assertEqual(out.returncode, 0)
        self.assertIn("mon: 08:00 - 17:30", out.stdout)
        self.assertIn("sat: (unavailable)", out.stdout)


if __name__ == "__main__":
    unittest.main()

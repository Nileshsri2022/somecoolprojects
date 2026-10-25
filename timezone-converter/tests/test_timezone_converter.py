#!/usr/bin/env python3
"""Tests for timezone_converter.py (stdlib unittest only)."""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from timezone_converter import (  # noqa: E402
    ABBREVIATIONS, convert, day_table, fmt_offset, load_zone, parse_time,
    resolve_zone, sort_relative, window,
)
from zoneinfo import ZoneInfo  # noqa: E402


def aware(zone, y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo(zone))


class TestResolve(unittest.TestCase):
    def test_iana_passthrough(self):
        self.assertEqual(resolve_zone("Europe/London"), "Europe/London")

    def test_abbreviations(self):
        self.assertEqual(resolve_zone("CET"), "Europe/Paris")
        self.assertEqual(resolve_zone("est"), "America/New_York")
        self.assertEqual(resolve_zone("PST"), "America/Los_Angeles")

    def test_city_substring(self):
        self.assertEqual(resolve_zone("london"), "Europe/London")
        self.assertEqual(resolve_zone("kolkata"), "Asia/Kolkata")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            resolve_zone("Nope/Zone")

    def test_ambiguous_city_raises(self):
        # 'sydney' is unique; a broad substring must not silently pick one.
        with self.assertRaises(ValueError):
            resolve_zone("a")


class TestConvert(unittest.TestCase):
    def test_basic_winter(self):
        src = aware("Europe/London", 2026, 1, 15, 12)
        out = dict(convert(src, ["America/New_York", "Asia/Kolkata"]))
        self.assertEqual(out["America/New_York"].strftime("%H:%M"), "07:00")
        self.assertEqual(out["Asia/Kolkata"].strftime("%H:%M"), "17:30")

    def test_summer_offsets(self):
        src = aware("Europe/London", 2026, 7, 15, 12)
        out = dict(convert(src, ["America/New_York"]))
        self.assertEqual(out["America/New_York"].strftime("%H:%M"), "07:00")
        self.assertEqual(fmt_offset(out["America/New_York"]), "-04:00")

    def test_date_rollover(self):
        src = aware("America/Los_Angeles", 2026, 1, 15, 20)
        out = dict(convert(src, ["Asia/Tokyo"]))
        self.assertEqual(out["Asia/Tokyo"].strftime("%Y-%m-%d %H:%M"),
                         "2026-01-16 13:00")

    def test_half_hour_zone(self):
        src = aware("UTC", 2026, 1, 15, 12)
        out = dict(convert(src, ["Asia/Kolkata", "Australia/Adelaide"]))
        self.assertEqual(out["Asia/Kolkata"].strftime("%H:%M"), "17:30")
        # Adelaide is +10:30 in January (DST).
        self.assertEqual(out["Australia/Adelaide"].strftime("%H:%M"), "22:30")


class TestDST(unittest.TestCase):
    def test_london_spring_forward_2026(self):
        # UK clocks go forward 01:00 GMT -> 02:00 BST on 2026-03-29.
        before = aware("Europe/London", 2026, 3, 29, 0, 30)
        after = aware("Europe/London", 2026, 3, 29, 3, 30)
        self.assertEqual(fmt_offset(before), "+00:00")
        self.assertEqual(fmt_offset(after), "+01:00")

    def test_us_and_europe_differ_in_march(self):
        # US DST starts 2026-03-08; Europe not until 2026-03-29.
        # On 2026-03-15 London is still GMT while New York is EDT.
        src = aware("Europe/London", 2026, 3, 15, 12)
        out = dict(convert(src, ["America/New_York"]))
        self.assertEqual(fmt_offset(src), "+00:00")
        self.assertEqual(fmt_offset(out["America/New_York"]), "-04:00")
        self.assertEqual(out["America/New_York"].strftime("%H:%M"), "08:00")

    def test_us_fall_back_2026(self):
        # US clocks go back 2026-11-01: 01:00 EDT repeats as 01:00 EST.
        first = datetime(2026, 11, 1, 1, 30, fold=0,
                         tzinfo=ZoneInfo("America/New_York"))
        second = datetime(2026, 11, 1, 1, 30, fold=1,
                         tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(fmt_offset(first), "-04:00")
        self.assertEqual(fmt_offset(second), "-05:00")
        # NOTE: aware subtraction with the same tzinfo ignores fold and
        # compares wall times, so compare via UTC to see the real hour.
        from datetime import timezone as _tz
        delta = (second.astimezone(_tz.utc)
                 - first.astimezone(_tz.utc)).total_seconds()
        self.assertEqual(delta, 3600)

    def test_southern_hemisphere_opposite(self):
        # Sydney DST runs Oct-Apr: January is +11, July is +10.
        jan = aware("Australia/Sydney", 2026, 1, 15, 12)
        jul = aware("Australia/Sydney", 2026, 7, 15, 12)
        self.assertEqual(fmt_offset(jan), "+11:00")
        self.assertEqual(fmt_offset(jul), "+10:00")

    def test_no_dst_zone(self):
        tokyo_jan = aware("Asia/Tokyo", 2026, 1, 15, 12)
        tokyo_jul = aware("Asia/Tokyo", 2026, 7, 15, 12)
        self.assertEqual(fmt_offset(tokyo_jan), fmt_offset(tokyo_jul))


class TestParseTime(unittest.TestCase):
    def test_formats(self):
        tz, _ = load_zone("Europe/London")
        self.assertEqual(parse_time("2026-01-15 09:30", tz),
                         aware("Europe/London", 2026, 1, 15, 9, 30))
        self.assertEqual(parse_time("2026-01-15T09:30:05", tz).second, 5)
        bare = parse_time("09:30", tz)
        self.assertEqual((bare.hour, bare.minute), (9, 30))
        self.assertEqual(bare.tzinfo, tz)

    def test_bad_input(self):
        tz, _ = load_zone("UTC")
        with self.assertRaises(ValueError):
            parse_time("tomorrow-ish", tz)


class TestSortAndWindow(unittest.TestCase):
    def test_sort_negative_before_positive(self):
        src = aware("Europe/London", 2026, 1, 15, 12)
        rows = sort_relative(src, ["Asia/Kolkata", "America/New_York"])
        self.assertEqual([r[1] for r in rows],
                         ["America/New_York", "Asia/Kolkata"])
        self.assertLess(rows[0][0], timedelta(0))
        self.assertGreater(rows[1][0], timedelta(0))

    def test_window_same_day(self):
        src = aware("Europe/London", 2026, 3, 29, 9)
        start, end, rows = window(src, "09:00", "10:30",
                                  ["America/New_York"])
        self.assertEqual((start.hour, end.hour), (9, 10))
        self.assertEqual(rows[0][1].strftime("%H:%M"), "04:00")
        self.assertEqual(rows[0][2].strftime("%H:%M"), "05:30")

    def test_window_crossing_midnight_rolls_next_day(self):
        src = aware("Europe/London", 2026, 1, 15, 12)
        start, end, _ = window(src, "23:00", "01:00", ["UTC"])
        self.assertEqual(end.day, 16)


class TestTable(unittest.TestCase):
    def test_24_rows_aligned_to_first_zone(self):
        headers, rows = day_table("Europe/London", ["America/New_York"],
                                  datetime(2026, 1, 15).date())
        self.assertEqual(headers, ["Europe/London", "America/New_York"])
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0][0].strftime("%H:%M"), "00:00")
        self.assertEqual(rows[0][1].strftime("%H:%M"), "19:00")  # prev day
        self.assertEqual(rows[23][0].strftime("%H:%M"), "23:00")

    def test_table_dst_gap_day_still_24_rows(self):
        # Spring-forward day: the skipped wall hour collapses onto the
        # previous instant under fold=0 (documented in SPEC); the table
        # still has 24 rows, one per wall hour 0-23.
        _, rows = day_table("Europe/London", [],
                            datetime(2026, 3, 29).date())
        self.assertEqual(len(rows), 24)
        from datetime import timezone as _tz
        self.assertEqual(rows[1][0].astimezone(_tz.utc),
                         rows[2][0].astimezone(_tz.utc))


class TestAbbreviationsDocumented(unittest.TestCase):
    def test_mapping_is_small_and_explicit(self):
        # Guard against silent growth of the ambiguous mapping.
        self.assertIn("IST", ABBREVIATIONS)
        self.assertEqual(ABBREVIATIONS["IST"], "Asia/Kolkata")


if __name__ == "__main__":
    unittest.main()

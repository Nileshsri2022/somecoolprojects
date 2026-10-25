"""Tests for crontab.py. Stdlib unittest only; no system crontab use."""
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crontab import (  # noqa: E402
    CronError, describe, next_runs, parse_crontab_text, parse_expression,
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(HERE, "crontab.py")


def expr(text):
    return parse_expression(text)


def dt(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M")


class TestParsing(unittest.TestCase):
    def test_star_and_single(self):
        e = expr("* * * * *")
        self.assertEqual(e.minutes, frozenset(range(60)))
        self.assertEqual(expr("0 9 * * 6").hours, frozenset({9}))

    def test_lists_ranges_steps(self):
        e = expr("0,30 9-17/2 * * *")
        self.assertEqual(e.minutes, frozenset({0, 30}))
        self.assertEqual(e.hours, frozenset({9, 11, 13, 15, 17}))
        self.assertEqual(expr("*/15 * * * *").minutes,
                         frozenset({0, 15, 30, 45}))
        self.assertEqual(expr("5/15 * * * *").minutes,
                         frozenset({5, 20, 35, 50}))
        self.assertEqual(expr("1,15,30-45/5 * * * *").minutes,
                         frozenset({1, 15, 30, 35, 40, 45}))

    def test_whitespace(self):
        e = expr("0\t9  *\t*   6")
        self.assertEqual(e.hours, frozenset({9}))
        self.assertEqual(e.days_of_week, frozenset({6}))

    def test_names(self):
        e = expr("0 9 * JAN-MAR MON-FRI")
        self.assertEqual(e.months, frozenset({1, 2, 3}))
        self.assertEqual(e.days_of_week, frozenset({1, 2, 3, 4, 5}))
        e2 = expr("0 0 * january saturday")
        self.assertEqual(e2.months, frozenset({1}))
        self.assertEqual(e2.days_of_week, frozenset({6}))
        self.assertEqual(expr("0 0 * * SUN").days_of_week, frozenset({0}))

    def test_dow_seven_is_sunday(self):
        self.assertEqual(expr("0 0 * * 7").days_of_week, frozenset({0}))
        self.assertEqual(expr("0 0 * * 0,7").days_of_week, frozenset({0}))
        self.assertEqual(expr("0 0 * * 5-7").days_of_week, frozenset({5, 6, 0}))

    def test_specials(self):
        self.assertEqual(expr("@yearly").raw_fields, ("0", "0", "1", "1", "*"))
        self.assertEqual(expr("@annually").raw_fields, ("0", "0", "1", "1", "*"))
        self.assertEqual(expr("@monthly").raw_fields, ("0", "0", "1", "*", "*"))
        self.assertEqual(expr("@weekly").raw_fields, ("0", "0", "*", "*", "0"))
        self.assertEqual(expr("@daily").raw_fields, ("0", "0", "*", "*", "*"))
        self.assertEqual(expr("@midnight").raw_fields, ("0", "0", "*", "*", "*"))
        self.assertEqual(expr("@hourly").raw_fields, ("0", "*", "*", "*", "*"))
        self.assertTrue(expr("@reboot").reboot)

    def test_command_preserved(self):
        e = expr("0 9 * * 6 send newsletter --fast")
        self.assertEqual(e.command, "send newsletter --fast")
        e2 = expr("@daily /usr/bin/backup.sh")
        self.assertEqual(e2.command, "/usr/bin/backup.sh")


class TestValidation(unittest.TestCase):
    def assertFieldError(self, text, field_word):
        with self.assertRaises(CronError) as ctx:
            expr(text)
        self.assertIn(field_word, str(ctx.exception))

    def test_field_counts(self):
        self.assertFieldError("0 9 * *", "5 fields")
        self.assertFieldError("", "empty")

    def test_out_of_range(self):
        self.assertFieldError("60 * * * *", "minute")
        self.assertFieldError("* 24 * * *", "hour")
        self.assertFieldError("* * 0 * *", "day of month")
        self.assertFieldError("* * 32 * *", "day of month")
        self.assertFieldError("* * * 13 *", "month")
        self.assertFieldError("* * * * 8", "day of week")

    def test_bad_syntax(self):
        self.assertFieldError("* * 5-1 * *", "day of month")
        self.assertFieldError("*/0 * * * *", "minute")
        self.assertFieldError("*/x * * * *", "minute")
        self.assertFieldError("1,,2 * * * *", "minute")
        self.assertFieldError("* * * FOO *", "month")
        self.assertFieldError("* * * * FUNDAY", "day of week")
        self.assertFieldError("61 61 * * *", "minute")

    def test_sixth_token_is_command_not_seconds(self):
        # Standard crontab: tokens after the five fields are the
        # command. So a six-token line is NOT a seconds field;
        # the sixth token is stored as the command, verbatim.
        e = expr("0 0 * * * /bin/true")
        self.assertEqual(e.command, "/bin/true")
        self.assertEqual(e.minutes, frozenset({0}))

    def test_unsupported_extensions(self):
        self.assertFieldError("* * ? * *", "day of month")
        self.assertFieldError("* * L * *", "day of month")
        self.assertFieldError("* * * * 5#2", "day of week")
        self.assertFieldError("@sometimes", "unknown special")

    def test_seconds_field_not_supported(self):
        # There is no seconds field: a schedule is always five
        # fields. A bad first field is still caught even when a
        # command follows it.
        self.assertFieldError("61 * * * * /bin/true", "minute")


class TestMatching(unittest.TestCase):
    def test_page_example(self):
        e = expr("0 9 * * 6")
        self.assertTrue(e.matches(dt("2026-10-31T09:00")))  # Saturday
        self.assertFalse(e.matches(dt("2026-10-31T10:00")))
        self.assertFalse(e.matches(dt("2026-10-30T09:00")))  # Friday

    def test_dom_dow_or_rule(self):
        e = expr("0 0 15 * 5")  # 15th OR Friday
        self.assertTrue(e.matches(dt("2026-10-15T00:00")))  # 15th, Thursday
        self.assertTrue(e.matches(dt("2026-10-16T00:00")))  # Friday, 16th
        self.assertFalse(e.matches(dt("2026-10-14T00:00")))  # neither

    def test_dom_only_and_dow_only(self):
        self.assertTrue(expr("0 0 15 * *").matches(dt("2026-10-15T00:00")))
        self.assertFalse(expr("0 0 15 * *").matches(dt("2026-10-16T00:00")))
        self.assertTrue(expr("0 0 * * 5").matches(dt("2026-10-16T00:00")))
        self.assertFalse(expr("0 0 * * 5").matches(dt("2026-10-15T00:00")))

    def test_star_dow_is_unrestricted(self):
        # */1 expands to the full range, so it must not force the OR rule.
        e = expr("0 0 15 * */1")
        self.assertTrue(e.matches(dt("2026-10-15T00:00")))
        self.assertFalse(e.matches(dt("2026-10-16T00:00")))

    def test_month_and_step(self):
        self.assertTrue(expr("*/30 * * JAN *").matches(dt("2026-01-10T00:30")))
        self.assertFalse(expr("*/30 * * JAN *").matches(dt("2026-02-10T00:30")))


class TestNextRuns(unittest.TestCase):
    def test_quarter_hour_strictly_after(self):
        runs = next_runs(expr("*/15 * * * *"), dt("2026-10-25T10:07"), count=3)
        self.assertEqual(runs, [dt("2026-10-25T10:15"), dt("2026-10-25T10:30"),
                                dt("2026-10-25T10:45")])

    def test_exact_moment_excluded(self):
        runs = next_runs(expr("0 9 * * 6"), dt("2026-10-31T09:00"), count=1)
        self.assertEqual(runs, [dt("2026-11-07T09:00")])

    def test_weekly_across_boundary(self):
        runs = next_runs(expr("0 9 * * 6"), dt("2026-10-25T10:00"), count=2)
        self.assertEqual(runs, [dt("2026-10-31T09:00"), dt("2026-11-07T09:00")])

    def test_leap_day(self):
        runs = next_runs(expr("0 0 29 2 *"), dt("2026-01-01T00:00"), count=1)
        self.assertEqual(runs, [dt("2028-02-29T00:00")])

    def test_impossible_raises(self):
        with self.assertRaises(CronError):
            next_runs(expr("0 0 31 2 *"), dt("2026-01-01T00:00"),
                      count=1, max_years=1)

    def test_reboot_has_no_next(self):
        with self.assertRaises(CronError):
            next_runs(expr("@reboot"), dt("2026-01-01T00:00"), count=1)


class TestDescribe(unittest.TestCase):
    def test_page_example(self):
        text = describe(expr("0 9 * * 6"))
        self.assertIn("09:00", text)
        self.assertIn("Saturday", text)

    def test_daily_and_steps(self):
        self.assertIn("00:00", describe(expr("@daily")))
        self.assertIn("every 5 minutes", describe(expr("*/5 * * * *")))
        self.assertIn("every minute", describe(expr("* * * * *")))
        self.assertIn("January", describe(expr("0 0 * JAN *")))
        self.assertEqual(describe(expr("@reboot")), "On system reboot.")


class TestCrontabFile(unittest.TestCase):
    def test_parse_file(self):
        text = (
            "# newsletter\n"
            "\n"
            "PATH=/usr/bin:/bin\n"
            "0 9 * * 6 send-newsletter --all\n"
            "@daily /usr/bin/backup.sh\n"
            "61 * * * * broken\n"
            "30 2 * * * nightly job\n"
        )
        jobs, errors = parse_crontab_text(text)
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0].command, "send-newsletter --all")
        self.assertEqual(jobs[1].expression.special, "@daily")
        self.assertEqual(jobs[2].lineno, 7)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], 6)
        self.assertIn("minute", errors[0][2])


class TestCLI(unittest.TestCase):
    def run_cli(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, PY, *args], input=stdin,
            capture_output=True, text=True, timeout=60)

    def test_explain_and_validate(self):
        out = self.run_cli("explain", "0 9 * * SAT")
        self.assertEqual(out.returncode, 0)
        self.assertIn("Saturday", out.stdout)
        out = self.run_cli("validate", "61 * * * *")
        self.assertEqual(out.returncode, 2)
        self.assertIn("minute", out.stderr)
        out = self.run_cli("validate", "0 9 * * 6")
        self.assertEqual(out.returncode, 0)

    def test_bare_expression_shorthand(self):
        out = self.run_cli("0 9 * * 6 send-newsletter")
        self.assertEqual(out.returncode, 0)
        self.assertIn("Saturday", out.stdout)

    def test_next_and_matches(self):
        out = self.run_cli("next", "*/15 * * * *",
                           "--from", "2026-10-25T10:07", "--count", "2")
        self.assertEqual(out.returncode, 0)
        self.assertIn("2026-10-25 10:15", out.stdout)
        self.assertIn("2026-10-25 10:30", out.stdout)
        out = self.run_cli("matches", "0 9 * * 6", "--at", "2026-10-31T09:00")
        self.assertEqual(out.stdout.strip(), "yes")
        out = self.run_cli("matches", "0 9 * * 6", "--at", "2026-10-30T09:00")
        self.assertEqual(out.stdout.strip(), "no")

    def test_list_file_and_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "jobs.txt")
            with open(path, "w") as fh:
                fh.write("# jobs\n0 9 * * 6 send-newsletter\n"
                         "@daily backup\n")
            out = self.run_cli("list", path, "--at", "2026-10-31T09:00",
                               "--next", "1")
            self.assertEqual(out.returncode, 0)
            self.assertIn("send-newsletter", out.stdout)
            self.assertIn("due at 2026-10-31T09:00: yes", out.stdout)
            out = self.run_cli("list", "-", stdin="0 9 * * 6 hi\n")
            self.assertEqual(out.returncode, 0)
            self.assertIn("hi", out.stdout)

    def test_unknown_subcommand(self):
        out = self.run_cli("frobnicate")
        # "frobnicate" is treated as a bare expression and fails validation.
        self.assertNotEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()

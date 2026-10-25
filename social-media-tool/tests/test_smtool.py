"""Tests for smtool.py. Stdlib only, temp DBs, no network, no real platform."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import smtool
from smtool import FakeAdapter, SmError, Store, get_adapter, main, parse_time


def past():
    return datetime.now(timezone.utc) - timedelta(hours=1)


def future():
    return datetime.now(timezone.utc) + timedelta(hours=1)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()


class TestCreate(Base):
    def test_create_draft_defaults(self):
        p = self.store.create_post("ada", "x", "hello")
        self.assertEqual(p["status"], "draft")
        self.assertEqual(p["visibility"], "public")
        self.assertEqual(p["author"], "ada")
        self.assertIsNone(p["scheduled_at"])
        self.assertIsNone(p["platform_post_id"])

    def test_create_linkedin_and_case_insensitive_platform(self):
        p = self.store.create_post("ada", "LinkedIn", "hello",
                                  visibility="connections")
        self.assertEqual(p["platform"], "linkedin")
        self.assertEqual(p["visibility"], "connections")

    def test_create_now_posts_via_fake_adapter(self):
        p = self.store.create_post("ada", "x", "hello now", now=True)
        self.assertEqual(p["status"], "posted")
        self.assertEqual(p["platform_post_id"], f"x:{p['id']}")
        self.assertIsNotNone(p["posted_at"])

    def test_create_now_linkedin_fake_id(self):
        p = self.store.create_post("ada", "linkedin", "hello", now=True)
        self.assertEqual(p["platform_post_id"], f"linkedin:{p['id']}")

    def test_create_scheduled_not_posted(self):
        p = self.store.create_post("ada", "x", "later", scheduled_at=future())
        self.assertEqual(p["status"], "scheduled")
        self.assertIsNotNone(p["scheduled_at"])
        self.assertIsNone(p["posted_at"])
        self.assertEqual(self.store.run_due(), [])

    def test_rejects_blank_author_and_body(self):
        for author, body in [("", "hi"), ("ada", ""), ("ada", "   ")]:
            with self.assertRaises(SmError):
                self.store.create_post(author, "x", body)
        self.assertEqual(self.store.list_posts(), [])

    def test_rejects_unknown_platform(self):
        with self.assertRaises(SmError):
            self.store.create_post("ada", "tiktok", "hi")

    def test_rejects_over_limit_bodies(self):
        with self.assertRaises(SmError):
            self.store.create_post("ada", "x", "x" * 281)
        with self.assertRaises(SmError):
            self.store.create_post("ada", "linkedin", "x" * 3001)
        # At the limit is fine.
        self.store.create_post("ada", "x", "x" * 280)
        self.store.create_post("ada", "linkedin", "x" * 3000)

    def test_rejects_bad_visibility(self):
        with self.assertRaises(SmError):
            self.store.create_post("ada", "x", "hi", visibility="connections")
        with self.assertRaises(SmError):
            self.store.create_post("ada", "linkedin", "hi", visibility="friends")

    def test_rejects_now_plus_schedule(self):
        with self.assertRaises(SmError):
            self.store.create_post("ada", "x", "hi", now=True,
                                  scheduled_at=future())

    def test_parse_time(self):
        self.assertEqual(parse_time("2026-10-26T10:00:00Z").tzinfo, timezone.utc)
        naive = parse_time("2026-10-26T10:00:00")
        self.assertEqual(naive.tzinfo, timezone.utc)
        with self.assertRaises(SmError):
            parse_time("not a time")


class TestListShow(Base):
    def test_list_newest_first_and_filters(self):
        a = self.store.create_post("ada", "x", "one")
        b = self.store.create_post("bob", "linkedin", "two",
                                  scheduled_at=future())
        c = self.store.create_post("ada", "x", "three", now=True)
        self.assertEqual([p["id"] for p in self.store.list_posts()],
                         [c["id"], b["id"], a["id"]])
        self.assertEqual([p["id"] for p in self.store.list_posts(status="posted")],
                         [c["id"]])
        self.assertEqual([p["id"] for p in self.store.list_posts(platform="linkedin")],
                         [b["id"]])
        self.assertEqual([p["id"] for p in self.store.list_posts(author="ada")],
                         [c["id"], a["id"]])
        with self.assertRaises(SmError):
            self.store.list_posts(status="bogus")

    def test_show_and_unknown_id(self):
        p = self.store.create_post("ada", "x", "hi")
        self.assertEqual(self.store.get_post(p["id"])["body"], "hi")
        with self.assertRaises(SmError):
            self.store.get_post(9999)


class TestEditCancel(Base):
    def test_edit_scheduled_body_time_visibility(self):
        p = self.store.create_post("ada", "linkedin", "old",
                                  scheduled_at=future())
        edited = self.store.edit_post(p["id"], body="new",
                                      visibility="connections",
                                      scheduled_at=future())
        self.assertEqual(edited["body"], "new")
        self.assertEqual(edited["visibility"], "connections")
        self.assertEqual(edited["status"], "scheduled")

    def test_edit_clear_schedule_returns_to_draft(self):
        p = self.store.create_post("ada", "x", "hi", scheduled_at=future())
        edited = self.store.edit_post(p["id"], clear_schedule=True)
        self.assertEqual(edited["status"], "draft")
        self.assertIsNone(edited["scheduled_at"])

    def test_edit_no_changes_and_conflict_rejected(self):
        p = self.store.create_post("ada", "x", "hi", scheduled_at=future())
        with self.assertRaises(SmError):
            self.store.edit_post(p["id"])
        with self.assertRaises(SmError):
            self.store.edit_post(p["id"], clear_schedule=True,
                                 scheduled_at=future())

    def test_edit_posted_or_cancelled_rejected_unchanged(self):
        posted = self.store.create_post("ada", "x", "hi", now=True)
        with self.assertRaises(SmError):
            self.store.edit_post(posted["id"], body="nope")
        self.assertEqual(self.store.get_post(posted["id"])["body"], "hi")
        draft = self.store.create_post("ada", "x", "bye")
        self.store.cancel_post(draft["id"])
        with self.assertRaises(SmError):
            self.store.edit_post(draft["id"], body="nope")

    def test_edit_validates_new_body(self):
        p = self.store.create_post("ada", "x", "hi", scheduled_at=future())
        with self.assertRaises(SmError):
            self.store.edit_post(p["id"], body="x" * 281)

    def test_cancel(self):
        p = self.store.create_post("ada", "x", "hi", scheduled_at=future())
        self.assertEqual(self.store.cancel_post(p["id"])["status"], "cancelled")
        with self.assertRaises(SmError):
            self.store.cancel_post(p["id"])
        posted = self.store.create_post("ada", "x", "hi", now=True)
        with self.assertRaises(SmError):
            self.store.cancel_post(posted["id"])


class TestSchedulerQueue(Base):
    def test_run_due_posts_only_due(self):
        due = self.store.create_post("ada", "x", "due", scheduled_at=past())
        soon = self.store.create_post("ada", "x", "soon", scheduled_at=future())
        posted = self.store.run_due()
        self.assertEqual([p["id"] for p in posted], [due["id"]])
        self.assertEqual(self.store.get_post(due["id"])["status"], "posted")
        self.assertEqual(self.store.get_post(soon["id"])["status"], "scheduled")

    def test_run_due_does_not_repost_or_post_cancelled(self):
        due = self.store.create_post("ada", "x", "due", scheduled_at=past())
        self.store.run_due()
        self.assertEqual(self.store.run_due(), [])
        cancelled = self.store.create_post("ada", "x", "c",
                                          scheduled_at=past())
        self.store.cancel_post(cancelled["id"])
        # cancel of a past-scheduled post: run_due must skip it
        self.assertEqual(self.store.run_due(), [])

    def test_run_due_posts_multiple(self):
        a = self.store.create_post("ada", "x", "a", scheduled_at=past())
        b = self.store.create_post("ada", "linkedin", "b", scheduled_at=past())
        self.assertEqual(len(self.store.run_due()), 2)
        self.assertEqual(self.store.get_post(a["id"])["status"], "posted")
        self.assertEqual(self.store.get_post(b["id"])["status"], "posted")

    def test_post_now(self):
        draft = self.store.create_post("ada", "x", "draft")
        now = self.store.post_now(draft["id"])
        self.assertEqual(now["status"], "posted")
        self.assertEqual(now["platform_post_id"], f"x:{draft['id']}")
        with self.assertRaises(SmError):
            self.store.post_now(draft["id"])
        sched = self.store.create_post("ada", "x", "s", scheduled_at=future())
        self.store.post_now(sched["id"])
        self.assertEqual(self.store.run_due(), [])  # not re-posted later

    def test_queue_job_lifecycle(self):
        p = self.store.create_post("ada", "x", "queued")
        job_id = self.store.enqueue_job(p["id"])
        jobs = self.store.drain_queue()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["status"], "done")
        self.assertEqual(self.store.get_post(p["id"])["status"], "posted")

    def test_failing_adapter_marks_failed(self):
        class Boom(FakeAdapter):
            def post(self, post):
                raise RuntimeError("simulated adapter failure")
        original = smtool.ADAPTERS["x"]
        smtool.ADAPTERS["x"] = Boom("x")
        try:
            p = self.store.create_post("ada", "x", "hi")
            self.store.enqueue_job(p["id"])
            jobs = self.store.drain_queue()
            self.assertEqual(jobs[0]["status"], "failed")
            after = self.store.get_post(p["id"])
            self.assertEqual(after["status"], "failed")
            self.assertIn("simulated adapter failure", after["error"])
        finally:
            smtool.ADAPTERS["x"] = original

    def test_adapter_rejects_bad_input_directly(self):
        adapter = get_adapter("x")
        with self.assertRaises(SmError):
            adapter.post({"id": 1, "platform": "x", "body": "x" * 281,
                          "visibility": "public"})
        self.assertEqual(adapter.post({"id": 7, "platform": "x",
                                       "body": "ok", "visibility": "public"}),
                         "x:7")


class TestPersistenceAndCLI(Base):
    def test_persistence_round_trip(self):
        p = self.store.create_post("ada", "x", "persist",
                                  scheduled_at=future())
        self.store.close()
        reopened = Store(self.db)
        try:
            self.assertEqual(reopened.get_post(p["id"])["body"], "persist")
        finally:
            reopened.close()
        self.store = Store(self.db)  # tearDown closes this one

    def test_cli_end_to_end(self):
        self.assertEqual(main(["--db", self.db, "create", "--platform", "x",
                               "--author", "ada", "--body", "cli hi",
                               "--schedule-at", "2030-01-01T00:00:00Z"]), 0)
        self.assertEqual(main(["--db", self.db, "list"]), 0)
        post = self.store.list_posts()[0]
        self.assertEqual(main(["--db", self.db, "show", str(post["id"])]), 0)
        self.assertEqual(main(["--db", self.db, "edit", str(post["id"]),
                               "--body", "cli edited"]), 0)
        self.assertEqual(main(["--db", self.db, "run-due"]), 0)
        self.assertEqual(main(["--db", self.db, "cancel", str(post["id"])]), 0)
        self.assertEqual(main(["--db", self.db, "create", "--platform", "x",
                               "--author", "ada", "--body", "bad",
                               "--visibility", "connections"]), 1)


if __name__ == "__main__":
    unittest.main()

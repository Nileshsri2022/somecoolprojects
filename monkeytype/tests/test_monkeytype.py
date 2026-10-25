"""Headless tests for monkeytype.py (no curses, TTY, network, or home dir)."""

import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monkeytype as mt


def result(wpm, accuracy, date="2026-10-25T00:00:00+00:00"):
    return {"wpm": wpm, "raw_wpm": wpm, "accuracy": accuracy,
            "correct": 10, "total": 10, "incorrect": 0,
            "elapsed_seconds": 60.0, "date": date}


class TestWords(unittest.TestCase):
    def test_generate_count_and_pool(self):
        words = mt.generate_words(count=25, rng=random.Random(1))
        self.assertEqual(len(words), 25)
        self.assertTrue(all(w in mt.COMMON_WORDS for w in words))
        self.assertEqual(mt.make_prompt(words).count(" "), 24)

    def test_generate_seeded_reproducible(self):
        a = mt.generate_words(count=10, rng=random.Random(42))
        b = mt.generate_words(count=10, rng=random.Random(42))
        self.assertEqual(a, b)

    def test_generate_beyond_pool_uses_replacement(self):
        words = mt.generate_words(pool=["a", "b"], count=5,
                                  rng=random.Random(0))
        self.assertEqual(len(words), 5)

    def test_generate_bad_args(self):
        with self.assertRaises(ValueError):
            mt.generate_words(pool=[], count=5)
        with self.assertRaises(ValueError):
            mt.generate_words(count=0)

    def test_common_words_clean(self):
        self.assertGreater(len(mt.COMMON_WORDS), 100)
        self.assertEqual(len(mt.COMMON_WORDS), len(set(mt.COMMON_WORDS)))
        self.assertTrue(all(w.isalpha() and w.islower()
                            for w in mt.COMMON_WORDS))


class TestScoring(unittest.TestCase):
    def test_perfect_typing(self):
        s = mt.score_test("hello world", "hello world", 60)
        self.assertEqual(s["accuracy"], 100.0)
        self.assertEqual(s["wpm"], s["raw_wpm"])
        self.assertEqual(s["correct"], 11)
        self.assertEqual(s["incorrect"], 0)

    def test_page_definition_worked_example(self):
        # 50 correct chars in 60 s -> 10 WPM; 60 typed -> 12 raw WPM.
        s = mt.score_test("x" * 50, "x" * 50, 60)
        self.assertEqual(s["wpm"], 10.0)
        self.assertEqual(s["raw_wpm"], 10.0)
        s = mt.score_test("x" * 50, "x" * 50 + "y" * 10, 60)
        self.assertEqual(s["wpm"], 10.0)
        self.assertEqual(s["raw_wpm"], 12.0)

    def test_all_wrong(self):
        s = mt.score_test("abc", "xyz", 60)
        self.assertEqual(s["wpm"], 0.0)
        self.assertEqual(s["accuracy"], 0.0)
        self.assertGreater(s["raw_wpm"], 0.0)

    def test_right_letter_wrong_position_not_correct(self):
        s = mt.score_test("ab", "ba", 60)
        self.assertEqual(s["correct"], 0)

    def test_mixed_typing(self):
        s = mt.score_test("hello", "hezlo", 30)
        self.assertEqual(s["correct"], 4)
        self.assertEqual(s["accuracy"], 80.0)

    def test_extra_chars_are_incorrect(self):
        s = mt.score_test("hi", "hix", 60)
        self.assertEqual(s["correct"], 2)
        self.assertEqual(s["incorrect"], 1)
        self.assertEqual(len(mt.char_results("hi", "hix")), 3)

    def test_empty_typed(self):
        s = mt.score_test("hello", "", 60)
        self.assertEqual(s["accuracy"], 0.0)
        self.assertEqual(s["wpm"], 0.0)
        self.assertEqual(s["raw_wpm"], 0.0)

    def test_zero_elapsed_no_crash(self):
        s = mt.score_test("hello", "hello", 0)
        self.assertEqual(s["wpm"], 0.0)
        self.assertEqual(s["raw_wpm"], 0.0)
        self.assertEqual(s["accuracy"], 100.0)

    def test_char_results_length_and_values(self):
        self.assertEqual(mt.char_results("abc", "axc"), [True, False, True])


class TestAccounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mt.UserStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_verify(self):
        self.store.create_user("alice", "secret")
        self.assertTrue(self.store.verify_user("alice", "secret"))
        self.assertFalse(self.store.verify_user("alice", "wrong"))
        self.assertFalse(self.store.verify_user("nobody", "secret"))

    def test_duplicate_and_empty_rejected(self):
        self.store.create_user("alice", "secret")
        with self.assertRaises(ValueError):
            self.store.create_user("alice", "other")
        with self.assertRaises(ValueError):
            self.store.create_user("", "secret")
        with self.assertRaises(ValueError):
            self.store.create_user("bob", "")

    def test_password_not_stored_plaintext_and_salted(self):
        self.store.create_user("alice", "same-pass")
        self.store.create_user("bob", "same-pass")
        data = self.store._load()["users"]
        self.assertNotIn("same-pass", str(data["alice"]))
        self.assertNotEqual(data["alice"]["salt"], data["bob"]["salt"])
        self.assertNotEqual(data["alice"]["password_hash"],
                            data["bob"]["password_hash"])

    def test_reset_password(self):
        self.store.create_user("alice", "old")
        with self.assertRaises(ValueError):
            self.store.reset_password("alice", "wrong", "new")
        self.assertTrue(self.store.verify_user("alice", "old"))
        self.store.reset_password("alice", "old", "new")
        self.assertTrue(self.store.verify_user("alice", "new"))
        self.assertFalse(self.store.verify_user("alice", "old"))
        with self.assertRaises(ValueError):
            self.store.reset_password("nobody", "x", "y")

    def test_delete_user(self):
        self.store.create_user("alice", "secret")
        with self.assertRaises(ValueError):
            self.store.delete_user("nobody")
        self.store.delete_user("alice")
        self.assertFalse(self.store.user_exists("alice"))
        self.assertEqual(self.store.results_for("alice"), [])

    def test_results_round_trip(self):
        self.store.create_user("alice", "secret")
        self.store.add_result("alice", result(42.0, 95.0))
        fresh = mt.UserStore(self.tmp.name)
        results = fresh.results_for("alice")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["wpm"], 42.0)
        self.assertEqual(results[0]["date"], "2026-10-25T00:00:00+00:00")
        with self.assertRaises(ValueError):
            fresh.add_result("nobody", result(1.0, 100.0))

    def test_session_round_trip(self):
        self.assertIsNone(mt.current_user(self.tmp.name))
        mt.set_current_user(self.tmp.name, "alice")
        self.assertEqual(mt.current_user(self.tmp.name), "alice")
        mt.clear_current_user(self.tmp.name)
        self.assertIsNone(mt.current_user(self.tmp.name))


class TestLeaderboardAndSummary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mt.UserStore(self.tmp.name)
        self.store.create_user("alice", "pw")
        self.store.create_user("bob", "pw")
        self.store.add_result("alice", result(50.0, 95.0,
                                             "2026-10-25T00:00:00+00:00"))
        self.store.add_result("alice", result(99.0, 80.0))  # below threshold
        self.store.add_result("bob", result(60.0, 90.0,
                                           "2026-10-25T01:00:00+00:00"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_leaderboard_order_and_threshold(self):
        board = self.store.leaderboard()
        self.assertEqual([e["username"] for e in board], ["bob", "alice"])
        self.assertEqual([e["wpm"] for e in board], [60.0, 50.0])
        # Exactly 90.0 is included; 80.0 is excluded.
        self.assertNotIn(99.0, [e["wpm"] for e in board])

    def test_leaderboard_cap_50(self):
        for i in range(60):
            self.store.add_result("bob", result(float(i), 100.0))
        self.assertEqual(len(self.store.leaderboard()), 50)

    def test_leaderboard_empty(self):
        empty = mt.UserStore(tempfile.mkdtemp())
        self.assertEqual(empty.leaderboard(), [])

    def test_summary(self):
        s = mt.summarise_results(self.store.results_for("alice"))
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["best_wpm"], 99.0)
        self.assertEqual(s["avg_wpm"], 74.5)
        self.assertEqual(s["avg_accuracy"], 87.5)

    def test_summary_empty(self):
        self.assertEqual(mt.summarise_results([]),
                         {"count": 0, "best_wpm": 0.0,
                          "avg_wpm": 0.0, "avg_accuracy": 0.0})


class TestFormat(unittest.TestCase):
    def test_format_result_contains_stats(self):
        text = mt.format_result(mt.score_test("hello", "hello", 60))
        self.assertIn("WPM", text)
        self.assertIn("Raw WPM", text)
        self.assertIn("Accuracy", text)
        self.assertIn("5 correct / 5 typed", text)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spell_correct import (  # noqa: E402
    correct,
    correct_text,
    edits1,
    is_correct,
    known,
    load_dictionary,
    rank,
    suggest,
)


class TestLoadDictionary(unittest.TestCase):
    def _load(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return load_dictionary(path)
        finally:
            os.unlink(path)

    def test_bare_words_default_to_one(self):
        self.assertEqual(self._load("hello\nworld\n"), {"hello": 1, "world": 1})

    def test_frequencies_space_tab_comma(self):
        freq = self._load("hello 10\nworld\t20\nfoo,30\n")
        self.assertEqual(freq, {"hello": 10, "world": 20, "foo": 30})

    def test_duplicates_add_blank_and_comment_ignored(self):
        freq = self._load("# comment\n\nhello 5\nHello 3\n")
        self.assertEqual(freq, {"hello": 8})

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_dictionary("/nonexistent/dict.txt")

    def test_bad_frequency(self):
        with self.assertRaises(ValueError):
            self._load("hello abc\n")


class TestEdits(unittest.TestCase):
    def test_each_edit_type_present(self):
        edits = edits1("cat")
        self.assertIn("at", edits)  # deletion
        self.assertIn("cats", edits)  # insertion
        self.assertIn("act", edits)  # transposition
        self.assertIn("bat", edits)  # replacement

    def test_count_bounded_by_formula(self):
        # 54n + 25 before deduplication; the set can only be smaller.
        self.assertLessEqual(len(edits1("ab")), 54 * 2 + 25)

    def test_known_filters(self):
        self.assertEqual(known({"cat", "dog", "zzz"}, {"cat": 1}), {"cat"})


class TestCorrection(unittest.TestCase):
    def setUp(self):
        self.freq = {
            "spelling": 100,
            "mistake": 90,
            "execution": 80,
            "mechanism": 70,
            "coding": 60,
            "challenges": 50,
            "cat": 40,
            "bat": 30,
            "car": 20,
        }

    def test_is_correct_case_insensitive(self):
        self.assertTrue(is_correct("Spelling", self.freq))
        self.assertFalse(is_correct("speiling", self.freq))

    def test_known_word_echoes(self):
        self.assertEqual(correct("coding", self.freq), "coding")
        self.assertEqual(correct("Coding", self.freq), "coding")

    def test_deletion_typo_fixed_by_insertion(self):
        self.assertEqual(correct("speling", self.freq), "spelling")

    def test_insertion_typo_fixed_by_deletion(self):
        self.assertEqual(correct("executionw", self.freq), "execution")

    def test_transposition_typo(self):
        self.assertEqual(correct("mistkae", self.freq), "mistake")

    def test_replacement_typo(self):
        self.assertEqual(correct("mekanism", self.freq), "mechanism")

    def test_frequency_ranking(self):
        # "cqt" is distance 1 from "cat" (q->a) and "cut" (q->u);
        # the more frequent word wins.
        freq = {"cat": 40, "bat": 30, "cut": 10}
        self.assertEqual(correct("cqt", freq), "cat")
        self.assertEqual(suggest("cqt", freq), ["cat", "cut"])

    def test_alphabetical_tie_break(self):
        # "cot" is distance 1 from both "cat" and "cut".
        freq = {"cat": 10, "cut": 10}
        self.assertEqual(suggest("cot", freq), ["cat", "cut"])

    def test_distance1_beats_frequent_distance2(self):
        # "cax" -> "cat" distance 1 (freq 1); "cart" is distance 2
        # (insert r, replace x with t) despite freq 1000.
        freq = {"cat": 1, "cart": 1000}
        self.assertEqual(correct("cax", freq), "cat")

    def test_distance2_correction(self):
        freq = {"spelling": 100}
        # "speling" is distance 1; "spelng" is distance 2 from "spelling"
        # (insert l, insert i) and distance 1 from nothing in the table.
        self.assertEqual(correct("spelng", freq), "spelling")

    def test_no_candidate_echoes(self):
        self.assertEqual(correct("zzzzqqq", self.freq), "zzzzqqq")

    def test_suggest_limit_and_order(self):
        freq = {"cat": 40, "bat": 30, "car": 20}
        # "cax": cat (1 edit), car (1 edit) -> freq order.
        # "bat" is 2 edits away and is NOT mixed into a
        # distance-1 result (lowest distance wins).
        self.assertEqual(suggest("cax", freq), ["cat", "car"])
        self.assertEqual(suggest("cax", freq, limit=1), ["cat"])
    def test_suggest_distance2_only(self):
        # "spelng" has no distance-1 neighbour in this table,
        # only the distance-2 "spelling".
        self.assertEqual(suggest("spelng", {"spelling": 100}), ["spelling"])

    def test_suggest_correct_word_empty(self):
        self.assertEqual(suggest("coding", self.freq), [])

    def test_correct_text_preserves_punctuation_and_capital(self):
        # A table without short words: "a" must not be pulled to
        # a distance-2 short word (see test_distance2_correction
        # for why a bare "a" legitimately corrects to "cat" in
        # the shared table, which contains cat/bat/car).
        freq = {"spelling": 100, "mistake": 90, "coding": 60}
        text = "Speiling is a misteke, coding!"
        self.assertEqual(
            correct_text(text, freq), "Spelling is a mistake, coding!"
        )

    def test_correct_text_unknown_unchanged(self):
        self.assertEqual(correct_text("zzzzqqq here.", self.freq), "zzzzqqq here.")


if __name__ == "__main__":
    unittest.main()

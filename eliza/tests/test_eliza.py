#!/usr/bin/env python3
"""Unittest suite for ELIZA. See docs/TEST_PLAN.md for the coverage map."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eliza import (  # noqa: E402
    Eliza,
    format_reply,
    is_quit,
    load_script,
    match_decomposition,
    reassemble,
    reflect,
    tokenize,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SCRIPT_PATH = os.path.join(PROJECT, "doctor.json")
ELIZA_PY = os.path.join(PROJECT, "eliza.py")

TINY_SCRIPT = {
    "initial": [],
    "final": ["Bye."],
    "fallbacks": ["I see.", "Please go on."],
    "memory_capacity": 2,
    "rules": [
        {
            "keyword": "why",
            "decompositions": [
                {
                    "pattern": ["0", "why", "dont", "i", "0"],
                    "reassemblies": [
                        ["Do", "you", "believe", "I", "don't", "5", "?"],
                        ["Perhaps", "I", "will", "5", "in", "good", "time", "."],
                        ["Should", "you", "5", "yourself", "?"],
                        ["You", "want", "me", "to", "5", "?"],
                    ],
                }
            ],
            "redirect": "what",
        },
        {
            "keyword": "dream",
            "decompositions": [
                {
                    "pattern": ["0", "dream", "0"],
                    "reassemblies": [["Dreaming", "3", "means", "something", "."]],
                    "memory": True,
                }
            ],
        },
        {
            "keyword": "what",
            "decompositions": [
                {
                    "pattern": ["0", "what", "0"],
                    "reassemblies": [["Why", "do", "you", "ask", "?"]],
                },
                {
                    "pattern": ["0"],
                    "reassemblies": [["What", "do", "you", "mean", "by", "that", "?"]],
                },
            ],
        },
        {
            "keyword": "maybe",
            "decompositions": [
                {
                    "pattern": ["0", "maybe", "0"],
                    "reassemblies": [["=what"]],
                }
            ],
        },
        {
            "keyword": "bogus",
            "decompositions": [
                {
                    "pattern": ["0", "bogus", "0"],
                    "reassemblies": [["=nosuchkeyword"]],
                }
            ],
        },
        {
            "keyword": "hello",
            "decompositions": [
                {
                    "pattern": ["0", "hello", "0"],
                    "reassemblies": [["Hello, how are you feeling today?"]],
                }
            ],
        },
        {
            "keyword": "go",
            "decompositions": [
                {
                    "pattern": ["0", "go", "0"],
                    "reassemblies": [["=what"]],
                }
            ],
        },
    ],
}


def tiny_engine():
    return Eliza(TINY_SCRIPT)


class TestQuit(unittest.TestCase):
    def test_quit_words(self):
        for word in ("quit", "Quit", "QUIT", "goodbye", "Goodbye!", "bye", "Bye."):
            self.assertTrue(is_quit(word), word)

    def test_not_quit(self):
        for text in ("exit", "bye for now", "", "   ", "goodbyes", "quit now",
                     "i want to quit"):
            self.assertFalse(is_quit(text), text)


class TestTokenizeReflect(unittest.TestCase):
    def test_tokenize(self):
        self.assertEqual(tokenize("Why don't I go outside?"),
                         ["why", "dont", "i", "go", "outside"])
        self.assertEqual(tokenize("Hello,  WORLD!"), ["hello", "world"])
        self.assertEqual(tokenize("..."), [])

    def test_reflect_all_entries(self):
        pairs = [("i", "you"), ("you", "i"), ("me", "you"), ("my", "your"),
                 ("your", "my"), ("yours", "mine"), ("mine", "yours"),
                 ("am", "are"), ("are", "am"), ("myself", "yourself"),
                 ("yourself", "myself"), ("we", "you"), ("us", "you"),
                 ("our", "your")]
        for before, after in pairs:
            self.assertEqual(reflect([before]), [after], before)
        self.assertEqual(reflect(["cats", "are", "fun"]), ["cats", "am", "fun"])


class TestDecomposition(unittest.TestCase):
    def test_literal_only(self):
        self.assertEqual(match_decomposition(["hello"], ["hello"]), [["hello"]])
        self.assertIsNone(match_decomposition(["hello"], ["hello", "there"]))

    def test_wildcards(self):
        result = match_decomposition(["0", "why", "dont", "i", "0"],
                                     ["why", "dont", "i", "try", "harder"])
        self.assertEqual(result, [[], ["why"], ["dont"], ["i"], ["try", "harder"]])

    def test_empty_wildcard_and_middle(self):
        self.assertEqual(match_decomposition(["0", "sad", "0"], ["sad"]),
                         [[], ["sad"], []])
        self.assertEqual(match_decomposition(["0", "i", "am", "0"],
                                             ["sometimes", "i", "am", "tired"]),
                         [["sometimes"], ["i"], ["am"], ["tired"]])

    def test_no_match(self):
        self.assertIsNone(match_decomposition(["0", "why", "0"], ["hello"]))
        self.assertIsNone(match_decomposition(["i", "am"], ["i", "am", "sad"]))


class TestReassembly(unittest.TestCase):
    def test_page_why_numbering(self):
        # Component 5 is the trailing wildcard, per the page's example.
        components = [[], ["why"], ["dont"], ["i"], ["try", "harder"]]
        wildcards = [True, False, False, False, True]
        self.assertEqual(
            reassemble(["Do", "you", "believe", "I", "don't", "5", "?"],
                       components, wildcards),
            "Do you believe I don't try harder?")

    def test_reflection_applies_to_wildcards_only(self):
        components = [[], ["i"], ["am"], ["my", "cat"]]
        wildcards = [True, False, False, True]
        self.assertEqual(reassemble(["How", "long", "have", "you", "been", "4", "?"],
                                    components, wildcards),
                         "How long have you been your cat?")


class TestEngineTiny(unittest.TestCase):
    def test_hello_step2_example(self):
        self.assertEqual(tiny_engine().reply("hello"),
                         "Hello, how are you feeling today?")

    def test_why_all_four_reassemblies_cycle(self):
        engine = tiny_engine()
        expected = [
            "Do you believe I don't try harder?",
            "Perhaps I will try harder in good time.",
            "Should you try harder yourself?",
            "You want me to try harder?",
            "Do you believe I don't try harder?",  # wraps around
        ]
        for want in expected:
            self.assertEqual(engine.reply("Why don't I try harder?"), want)

    def test_why_reflects_captured_fragment(self):
        self.assertEqual(tiny_engine().reply("Why don't I love my job?"),
                         "Do you believe I don't love your job?")

    def test_redirection_via_reassembly(self):
        # "maybe" redirects to WHAT; WHAT's first decomposition needs the
        # word "what", which is absent, so its catch-all ["0"] answers.
        self.assertEqual(tiny_engine().reply("maybe later"),
                         "What do you mean by that?")

    def test_unknown_redirect_falls_back(self):
        self.assertEqual(tiny_engine().reply("bogus thing"), "I see.")

    def test_redirect_when_no_decomposition_matches(self):
        # WHY's decompositions do not fit "why is the sky blue", so its
        # redirect to WHAT applies, and WHAT's catch-all answers.
        self.assertEqual(tiny_engine().reply("why is the sky blue"),
                         "What do you mean by that?")

    def test_earlier_keyword_wins_when_both_fit(self):
        # HELLO is earlier in the tiny script than GO, and both patterns
        # fit "hello go", so the HELLO reply wins regardless of input order.
        self.assertEqual(tiny_engine().reply("go hello"),
                         "Hello, how are you feeling today?")

    def test_keyword_priority_is_script_order_not_input_order(self):
        # WHY is earlier in the tiny script than HELLO. WHY's own pattern
        # does not fit "hello why is this", but its redirect to WHAT's
        # catch-all does produce a reply, so the WHY chain answers before
        # the later HELLO rule is ever tried.
        engine = tiny_engine()
        self.assertEqual(engine.reply("hello why is this"),
                         "What do you mean by that?")

    def test_fallback_cycles(self):
        engine = tiny_engine()
        self.assertEqual(engine.reply("blorpt wuzzle"), "I see.")
        self.assertEqual(engine.reply("flibberty gibbet"), "Please go on.")
        self.assertEqual(engine.reply("snorp"), "I see.")

    def test_memory_recalled_before_fallback_and_consumed(self):
        engine = tiny_engine()
        engine.reply("i had a dream about flying")
        self.assertEqual(engine.reply("blorpt wuzzle"),
                         "Dreaming about flying means something.")
        # Consumed: next no-keyword input gets the plain fallback.
        self.assertEqual(engine.reply("blorpt wuzzle"), "I see.")

    def test_memory_capacity_drops_oldest(self):
        engine = tiny_engine()  # capacity 2
        engine.reply("i had a dream about one")
        engine.reply("i had a dream about two")
        engine.reply("i had a dream about three")
        self.assertEqual(engine.reply("zzzz"), "Dreaming about two means something.")
        self.assertEqual(engine.reply("zzzz"), "Dreaming about three means something.")

    def test_empty_input_returns_none(self):
        self.assertIsNone(tiny_engine().reply("..."))
        self.assertIsNone(tiny_engine().reply(""))

    def test_determinism(self):
        inputs = ["hello", "why don't i try harder?", "blorpt", "i dream about x"]
        first = [tiny_engine().reply(t) for t in inputs]
        # Fresh engine, same inputs, same replies (fresh engine per input
        # would differ on cycling, so replay the whole sequence twice).
        engine_a, engine_b = tiny_engine(), tiny_engine()
        self.assertEqual([engine_a.reply(t) for t in inputs],
                         [engine_b.reply(t) for t in inputs])
        self.assertIsNotNone(first)


class TestShippedScript(unittest.TestCase):
    def test_loads_and_has_why_rule(self):
        script = load_script(SCRIPT_PATH)
        keywords = [rule["keyword"] for rule in script["rules"]]
        self.assertIn("why", keywords)
        self.assertIn("hello", keywords)
        self.assertIn("I see.", script["fallbacks"])

    def test_shipped_why_example(self):
        engine = Eliza(load_script(SCRIPT_PATH))
        self.assertEqual(engine.reply("Why don't I try harder?"),
                         "Do you believe I don't try harder?")

    def test_shipped_scripted_exchange(self):
        engine = Eliza(load_script(SCRIPT_PATH))
        self.assertEqual(engine.reply("hello"), "Hello, how are you feeling today?")
        self.assertEqual(engine.reply("i feel sad"),
                         "Do you often feel sad?")
        self.assertEqual(engine.reply("i am tired"),
                         "How long have you been tired?")
        # No keyword at all -> fallback, starting with "I see."
        self.assertEqual(engine.reply("quux zorp"), "I see.")

    def test_missing_and_malformed_script_raise(self):
        with self.assertRaises(ValueError):
            load_script(os.path.join(PROJECT, "no-such-file.json"))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{not json")
            bad = fh.name
        try:
            with self.assertRaises(ValueError):
                load_script(bad)
        finally:
            os.unlink(bad)

    def test_temp_script_file_drives_replies(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(TINY_SCRIPT, fh)
            path = fh.name
        try:
            engine = Eliza(load_script(path))
            self.assertEqual(engine.reply("hello"),
                             "Hello, how are you feeling today?")
        finally:
            os.unlink(path)


class TestReplSubprocess(unittest.TestCase):
    def run_repl(self, stdin_text, extra_args=()):
        proc = subprocess.run(
            [sys.executable, ELIZA_PY, *extra_args],
            input=stdin_text, capture_output=True, text=True, timeout=30,
        )
        return proc

    def test_hello_then_quit(self):
        proc = self.run_repl("hello\nquit\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ELIZA", proc.stdout)
        self.assertIn("How do you do.", proc.stdout)
        self.assertIn("Hello, how are you feeling today?", proc.stdout)
        self.assertIn("Goodbye.", proc.stdout)

    def test_eof_exits_cleanly(self):
        proc = self.run_repl("")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Goodbye.", proc.stdout)

    def test_help_exits_zero(self):
        proc = self.run_repl("", extra_args=("--help",))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("rule-based", proc.stdout)

    def test_missing_script_exits_nonzero(self):
        proc = self.run_repl("", extra_args=("--script", "/nonexistent/x.json"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot read script", proc.stderr)


if __name__ == "__main__":
    unittest.main()

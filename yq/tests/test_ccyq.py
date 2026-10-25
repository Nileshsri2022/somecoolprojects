#!/usr/bin/env python3
"""Unit + CLI tests for ccyq. Run from the yq/ directory:
    python3 -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ccyq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "ccyq.py")
QUOTES = os.path.join(HERE, "quotes.yaml")

Q1 = ("It is bad for a young man to sin; but it is worse for an old "
      "man to sin.")
Q2 = "If You Are Out To Describe The Truth, Leave Elegance To The Tailor."
Q3 = ("O man you are busy working for the world, and the world is busy "
      "trying to turn you out.")
Q4 = ("While children are struggling to be unique, the world around "
      "them is trying all means to make them look like everybody else.")
Q5 = ("These Capitalists Generally Act Harmoniously And In Concert, "
      "To Fleece The People.")


def run_cli(args, stdin_text=None):
    return subprocess.run(
        [sys.executable, TOOL] + args, input=stdin_text,
        capture_output=True, text=True, timeout=30)


def query(filter_text, doc):
    return ccyq.eval_filter(ccyq.parse_filter(filter_text),
                            ccyq.parse_yaml(doc))


def read_quotes():
    with open(QUOTES, encoding="utf-8") as fh:
        return fh.read()


class TestParserScalars(unittest.TestCase):
    def test_plain_typed_scalars(self):
        doc = ccyq.parse_yaml(
            "a: 42\nb: -7\nc: 3.5\nd: true\ne: false\n"
            "f: null\ng: ~\nh:\ni: 0x1F\nj: 0o17\nk: hello\n")
        self.assertEqual(doc, {"a": 42, "b": -7, "c": 3.5, "d": True,
                               "e": False, "f": None, "g": None,
                               "h": None, "i": 31, "j": 15, "k": "hello"})

    def test_quoted_scalars_stay_strings(self):
        doc = ccyq.parse_yaml('a: "123"\nb: \'true\'\nc: "a: b"\n')
        self.assertEqual(doc, {"a": "123", "b": "true", "c": "a: b"})

    def test_single_quote_escape(self):
        self.assertEqual(ccyq.parse_yaml("a: 'it''s'\n"), {"a": "it's"})

    def test_comments(self):
        doc = ccyq.parse_yaml(
            "# header\na: 1 # trailing\n# full line\nb: keep # me\n"
            "c: \"has # inside\"\nd: Tailor's\n")
        self.assertEqual(doc, {"a": 1, "b": "keep",
                               "c": "has # inside", "d": "Tailor's"})


class TestParserStructure(unittest.TestCase):
    def test_nested_mapping_and_sequence(self):
        doc = ccyq.parse_yaml(
            "outer:\n  inner:\n    x: 1\n  list:\n    - a\n    - b\n")
        self.assertEqual(doc, {"outer": {"inner": {"x": 1},
                                         "list": ["a", "b"]}})

    def test_indentless_sequence(self):
        doc = ccyq.parse_yaml("quotes:\n- id: 1\n- id: 2\n")
        self.assertEqual(doc, {"quotes": [{"id": 1}, {"id": 2}]})

    def test_sequence_of_mappings(self):
        doc = ccyq.parse_yaml(
            "- id: 1\n  name: one\n- id: 2\n  name: two\n")
        self.assertEqual(doc, [{"id": 1, "name": "one"},
                               {"id": 2, "name": "two"}])

    def test_top_level_sequence_and_scalar(self):
        self.assertEqual(ccyq.parse_yaml("- a\n- b\n"), ["a", "b"])
        self.assertEqual(ccyq.parse_yaml("just a string\n"), "just a string")

    def test_flow_collections(self):
        doc = ccyq.parse_yaml("a: [1, two, true]\nb: {k: v, n: 2}\n")
        self.assertEqual(doc, {"a": [1, "two", True], "b": {"k": "v", "n": 2}})

    def test_empty_document_and_doc_markers(self):
        self.assertIsNone(ccyq.parse_yaml(""))
        self.assertIsNone(ccyq.parse_yaml("# only a comment\n"))
        self.assertEqual(ccyq.parse_yaml("---\na: 1\n"), {"a": 1})

    def test_block_scalars(self):
        doc = ccyq.parse_yaml(
            "folded: >-\n  line one\n  line two\nauthor: me\n"
            "literal: |-\n  keep\n  newlines\nnext: 1\n"
            "clipped: |\n  one\n  two\n")
        self.assertEqual(doc["folded"], "line one line two")
        self.assertEqual(doc["literal"], "keep\nnewlines")
        self.assertEqual(doc["clipped"], "one\ntwo\n")

    def test_folded_with_blank_line(self):
        doc = ccyq.parse_yaml("a: >\n  para one\n\n  para two\n")
        self.assertEqual(doc["a"], "para one\npara two\n")

    def test_rejected_features(self):
        with self.assertRaises(ccyq.YQError):
            ccyq.parse_yaml("a: &anchor 1\n")
        with self.assertRaises(ccyq.YQError):
            ccyq.parse_yaml("a: *anchor\n")
        with self.assertRaises(ccyq.YQError):
            ccyq.parse_yaml("a: 1\n---\nb: 2\n")
        with self.assertRaises(ccyq.YQError):
            ccyq.parse_yaml("a:\n\tb: 1\n")


class TestQuotesFixture(unittest.TestCase):
    def setUp(self):
        with open(QUOTES, encoding="utf-8") as fh:
            self.doc = ccyq.parse_yaml(fh.read())

    def test_five_quotes_page_values(self):
        quotes = self.doc["quotes"]
        self.assertEqual(len(quotes), 5)
        self.assertEqual([q["id"] for q in quotes], [1, 2, 3, 4, 5])
        self.assertEqual([q["quote"] for q in quotes],
                         [Q1, Q2, Q3, Q4, Q5])
        # Authors actually printed on the page: ids 1 and 5 only.
        self.assertEqual(quotes[0]["author"], "Abu Bakr (R.A)")
        self.assertEqual(quotes[4]["author"], "Abraham Lincoln")

    def test_step2_object_identifier(self):
        for filt in (".quotes", ".[quotes]", '.["quotes"]',
                     ".['quotes']", ".quotes?"):
            self.assertEqual(query(filt, read_quotes())[0],
                             self.doc["quotes"])

    def test_step3_array_index(self):
        got = query(".quotes[0]", read_quotes())[0]
        self.assertEqual(got["id"], 1)
        self.assertEqual(got["quote"], Q1)
        self.assertEqual(got["author"], "Abu Bakr (R.A)")

    def test_step4_pipe(self):
        self.assertEqual(query(".quotes[1] | .quote",
                               read_quotes())[0], Q2)

    def test_step5_collect(self):
        got = query("[.quotes[].quote]", read_quotes())[0]
        self.assertEqual(got, [Q1, Q2, Q3, Q4, Q5])

    def test_collect_authors_and_ids(self):
        text = read_quotes()
        self.assertEqual(query("[.quotes[].id]", text)[0], [1, 2, 3, 4, 5])
        self.assertEqual(len(query("[.quotes[].author]", text)[0]), 5)


class TestQuerySemantics(unittest.TestCase):
    DOC = "a:\n  b:\n    - 10\n    - 20\n    - 30\n  c: hi\n"

    def test_identity_and_chaining(self):
        self.assertEqual(query(".", self.DOC), [ccyq.parse_yaml(self.DOC)])
        self.assertEqual(query(".a.b[1]", self.DOC), [20])
        self.assertEqual(query(".a.c", self.DOC), ["hi"])

    def test_negative_and_out_of_range_index(self):
        self.assertEqual(query(".a.b[-1]", self.DOC), [30])
        self.assertEqual(query(".a.b[3]", self.DOC), [None])
        self.assertEqual(query(".a.b[99]", self.DOC), [None])
        self.assertEqual(query(".a.b[-99]", self.DOC), [None])

    def test_missing_key_is_null(self):
        self.assertEqual(query(".a.nope", self.DOC), [None])
        self.assertEqual(query(".a.nope?", self.DOC), [None])

    def test_optional_suppresses_wrong_type(self):
        self.assertEqual(query(".a.c?", self.DOC), ["hi"])
        self.assertEqual(query(".a.c.x?", self.DOC), [None])
        with self.assertRaises(ccyq.YQError):
            query(".a.c.x", self.DOC)
        with self.assertRaises(ccyq.YQError):
            query(".a.b.foo", self.DOC)
        self.assertEqual(query(".a.b[0]?", self.DOC), [10])

    def test_bracket_index_and_key_forms(self):
        self.assertEqual(query(".a.[b]", self.DOC),
                         [[10, 20, 30]])
        self.assertEqual(query('.a.["b"]', self.DOC), [[10, 20, 30]])
        self.assertEqual(query(".a.b.[1]", self.DOC), [20])

    def test_iterate_and_collect(self):
        self.assertEqual(query(".a.b[]", self.DOC), [10, 20, 30])
        self.assertEqual(query("[.a.b[]]", self.DOC), [[10, 20, 30]])
        self.assertEqual(query("[.a.b[] | .]", self.DOC), [[10, 20, 30]])
        self.assertEqual(query(".a.b[] | .", self.DOC), [10, 20, 30])

    def test_empty_sequence_collect(self):
        self.assertEqual(query("[.a.b[]]", "a:\n  b: []\n"), [[]])

    def test_malformed_filters(self):
        for bad in (".a[", ".a |", "a", ".a..b", ".a[foo", ".[\"a]"):
            with self.assertRaises(ccyq.YQError, msg=bad):
                query(bad, self.DOC)

    def test_pipe_missing_key(self):
        self.assertEqual(query(".a | .nope", self.DOC), [None])


class TestEmitter(unittest.TestCase):
    def test_round_trip(self):
        docs = [
            "a: 1\nb:\n  - x\n  - 2\n",
            "a: 'true'\nb: ''\nc: 'a: b'\n",
            "a:\n  b:\n    c: deep\n",
            "- id: 1\n  name: one\n- id: 2\n",
            "s: 'multi'\n",
        ]
        for text in docs:
            parsed = ccyq.parse_yaml(text)
            self.assertEqual(ccyq.parse_yaml(ccyq.dump_value(parsed)),
                             parsed, msg=text)

    def test_multiline_round_trip(self):
        doc = {"a": "line one\nline two"}
        self.assertEqual(ccyq.parse_yaml(ccyq.dump_value(doc)), doc)

    def test_exact_small_output(self):
        self.assertEqual(ccyq.dump_value({"a": 1, "b": ["x", "y"]}),
                         "a: 1\nb:\n  - x\n  - y")
        self.assertEqual(ccyq.dump_value([]), "[]")
        self.assertEqual(ccyq.dump_value({}), "{}")
        self.assertEqual(ccyq.dump_value(None), "null")


class TestCLI(unittest.TestCase):
    def test_step1_no_filter(self):
        res = run_cli([QUOTES])
        self.assertEqual(res.returncode, 0, res.stderr)
        doc = ccyq.parse_yaml(res.stdout)
        self.assertEqual(len(doc["quotes"]), 5)
        self.assertEqual(doc["quotes"][4]["author"], "Abraham Lincoln")

    def test_step3_cli_exact(self):
        res = run_cli([".quotes[0]", QUOTES])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("id: 1", res.stdout)
        self.assertIn(Q1, res.stdout)

    def test_step4_cli_exact(self):
        res = run_cli([".quotes[1] | .quote", QUOTES])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), Q2)

    def test_step5_cli(self):
        res = run_cli(["[.quotes[].quote]", QUOTES])
        self.assertEqual(res.returncode, 0, res.stderr)
        doc = ccyq.parse_yaml(res.stdout)
        self.assertEqual(doc, [Q1, Q2, Q3, Q4, Q5])

    def test_bare_iterate_separators(self):
        res = run_cli([".quotes[].id", QUOTES])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip().split("\n---\n"),
                         ["1", "2", "3", "4", "5"])

    def test_stdin_and_out_of_range(self):
        res = run_cli([".a[5]"], stdin_text="a:\n  - 1\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "null")
        res = run_cli([], stdin_text="a: 1\n")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "a: 1")

    def test_errors_exit_2_empty_stdout(self):
        res = run_cli([".a", "/nonexistent/file.yaml"])
        self.assertEqual(res.returncode, 2)
        self.assertEqual(res.stdout, "")
        res = run_cli([".a["], stdin_text="a: 1\n")
        self.assertEqual(res.returncode, 2)
        self.assertEqual(res.stdout, "")
        res = run_cli([".a"], stdin_text="a: &x 1\n")
        self.assertEqual(res.returncode, 2)
        self.assertEqual(res.stdout, "")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Static validation harness for the Coding Challenges New Tab extension.

Stdlib only. Never touches the network and never loads the extension in
a browser (see docs/TEST_PLAN.md for that honest scope limit).
Run:  python3 tests/test_extension.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_FILES = ["js/format.js", "js/quotes.js", "js/newtab.js"]
EXPECTED_IDS = ["clock", "date", "quote", "github-list", "substack-list",
                "settings-panel", "settings-toggle"]


def load_manifest():
    return json.loads((ROOT / "manifest.json").read_text())


class TestManifest(unittest.TestCase):
    def test_valid_and_mv3(self):
        m = load_manifest()
        self.assertEqual(m["manifest_version"], 3)
        self.assertTrue(m["name"])
        self.assertTrue(m["version"])

    def test_newtab_override(self):
        m = load_manifest()
        self.assertEqual(m["chrome_url_overrides"]["newtab"], "newtab.html")

    def test_storage_permission_and_github_host(self):
        m = load_manifest()
        self.assertIn("storage", m["permissions"])
        hosts = " ".join(m["host_permissions"])
        self.assertIn("api.github.com", hosts)

    def test_icons_exist(self):
        m = load_manifest()
        for path in m["icons"].values():
            self.assertTrue((ROOT / path).is_file(), f"missing icon {path}")


class TestFiles(unittest.TestCase):
    def test_required_files_exist(self):
        for rel in ["newtab.html", "css/newtab.css"] + JS_FILES:
            self.assertTrue((ROOT / rel).is_file(), f"missing {rel}")

    def test_no_pycache(self):
        self.assertEqual(list(ROOT.rglob("__pycache__")), [])


class TestHtmlCss(unittest.TestCase):
    def test_html_wiring(self):
        html = (ROOT / "newtab.html").read_text()
        for rel in ["css/newtab.css"] + JS_FILES:
            self.assertIn(rel, html, f"html does not reference {rel}")
        for el in EXPECTED_IDS:
            self.assertIn(f'id="{el}"', html, f"missing id {el}")
        self.assertIn("Coding Challenges", html)

    def test_css_brand_colour_and_centring(self):
        css = (ROOT / "css/newtab.css").read_text()
        self.assertIn("#04295B", css)
        self.assertIn("text-align: center", css)

    def test_no_innerhtml_with_network_data(self):
        js = (ROOT / "js/newtab.js").read_text()
        # Assignment form only: a mere mention in a comment must not fail.
        self.assertIsNone(re.search(r"\.innerHTML\s*=", js))
        self.assertIn("textContent", js)

    def test_no_credentials(self):
        blob = "".join(p.read_text(errors="ignore") for p in
                       [ROOT / "manifest.json", ROOT / "newtab.html",
                        ROOT / "css/newtab.css"] + [ROOT / f for f in JS_FILES])
        for bad in ["api_key", "apikey", "password", "secret_token", "Bearer "]:
            self.assertNotIn(bad.lower(), blob.lower(), f"suspicious string {bad}")


class TestJsSyntax(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_node_check(self):
        for rel in JS_FILES:
            r = subprocess.run(["node", "--check", str(ROOT / rel)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{rel}: {r.stderr}")

    def test_balanced_delimiters(self):
        for rel in JS_FILES:
            src = (ROOT / rel).read_text()
            for a, b in [("{", "}"), ("(", ")"), ("[", "]")]:
                self.assertEqual(src.count(a), src.count(b), f"{rel} unbalanced {a}{b}")


class TestPureFunctionsViaNode(unittest.TestCase):
    """Execute format.js in Node against fixed inputs."""
    NODE_SCRIPT = r"""
const f = require(process.argv[2]);
const assert = require('assert');
const d = (y, mo, da, h, mi, s) => new Date(y, mo, da, h, mi, s);
assert.strictEqual(f.formatTime(d(2026, 9, 25, 0, 0, 0)), '12:00:00 AM');
assert.strictEqual(f.formatTime(d(2026, 9, 25, 12, 0, 0)), '12:00:00 PM');
assert.strictEqual(f.formatTime(d(2026, 9, 25, 23, 7, 33)), '11:07:33 PM');
assert.strictEqual(f.formatTime(d(2026, 9, 25, 13, 5, 9)), '1:05:09 PM');
assert.strictEqual(f.formatDate(d(2026, 9, 25, 0, 0, 0)), 'Sunday, 25 October 2026');
assert.strictEqual(f.formatDate(d(2026, 0, 1, 0, 0, 0)), 'Thursday, 1 January 2026');
assert.strictEqual(f.dayOfYear(d(2026, 0, 1, 0, 0, 0)), 1);
assert.strictEqual(f.dayOfYear(d(2024, 1, 29, 0, 0, 0)), 60); // leap year
assert.strictEqual(f.dayOfYear(d(2026, 11, 31, 0, 0, 0)), 365);
const q = ['a', 'b', 'c'];
assert.strictEqual(f.pickDailyQuote(q, d(2026, 0, 1, 0, 0, 0)), 'b'); // day 1 -> idx 1
assert.strictEqual(f.pickDailyQuote(q, d(2026, 0, 1, 0, 0, 0)),
                   f.pickDailyQuote(q, d(2026, 0, 1, 23, 59, 59)));
assert.strictEqual(f.pickDailyQuote([], d(2026, 0, 1, 0, 0, 0)), null);
assert.strictEqual(f.buildGitHubApiUrl('CodingChallegesFYI', 'SharedSolutions'),
  'https://api.github.com/repos/CodingChallegesFYI/SharedSolutions/pulls?state=open&per_page=30');
assert.strictEqual(f.buildSubstackProxyUrl('https://api.allorigins.win/raw?url=', 'https://codingchallenges.substack.com/feed'),
  'https://api.allorigins.win/raw?url=https%3A%2F%2Fcodingchallenges.substack.com%2Ffeed');
assert.strictEqual(f.buildSubstackProxyUrl('', 'https://codingchallenges.substack.com/feed'),
  'https://codingchallenges.substack.com/feed');
assert.deepStrictEqual(f.parseGitHubPRs([{number: 7, title: 'T', user: {login: 'u'}, html_url: 'http://x'}]),
  [{number: 7, title: 'T', author: 'u', url: 'http://x'}]);
assert.deepStrictEqual(f.parseGitHubPRs(null), []);
assert.deepStrictEqual(f.parseGitHubPRs([{}]),
  [{number: null, title: '', author: '', url: ''}]);
console.log('node-assertions-ok');
"""

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_format_functions(self):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(self.NODE_SCRIPT)
            script = fh.name
        r = subprocess.run(["node", script, str(ROOT / "js/format.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("node-assertions-ok", r.stdout)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    r = result.result
    print(f"\nSUMMARY: {r.testsRun - len(r.failures) - len(r.errors) - len(r.skipped)} passed, "
          f"{len(r.failures) + len(r.errors)} failed, {len(r.skipped)} skipped, "
          f"{r.testsRun} total")
    sys.exit(0 if r.wasSuccessful() else 1)

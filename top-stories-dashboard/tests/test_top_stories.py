"""Tests for top_stories.py. No live network: fake HN + real API servers
on ephemeral ports, shut down in tearDown. Run from the project dir:
    python3 -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import top_stories as ts  # noqa: E402

FIXTURES = {
    "/v0/topstories.json": [1, 2, 3],
    "/v0/newstories.json": [3, 4],
    "/v0/item/1.json": {"by": "alice", "id": 1, "score": 142,
                        "time": 1700000000, "title": "Rust wins again",
                        "type": "story", "url": "https://example.com/rust"},
    "/v0/item/2.json": {"by": "bob", "id": 2, "score": 20,
                        "time": 1700000100, "title": "Python tips",
                        "type": "story"},
    "/v0/item/3.json": {"by": "carol", "id": 3, "score": 999,
                        "time": 1700000200, "title": "Hiring",
                        "type": "job", "url": "https://example.com/job"},
    "/v0/item/4.json": {"by": "dave", "id": 4, "score": 5,
                        "time": 1700000300, "title": "Rust for beginners",
                        "type": "story", "url": "https://example.com/rust2"},
}


class FakeHNHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in FIXTURES:
            body = json.dumps(FIXTURES[self.path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


class ServerMixin:
    def _start(self, handler):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class TestScraper(ServerMixin, unittest.TestCase):
    def setUp(self):
        # Real HN base ends in /v0; the fake server mirrors that layout.
        self.base = self._start(FakeHNHandler) + "/v0"

    def tearDown(self):
        self._stop()

    def test_fetch_ids(self):
        self.assertEqual(ts.fetch_story_ids(self.base, "top"), [1, 2, 3])
        self.assertEqual(ts.fetch_story_ids(self.base, "new"), [3, 4])

    def test_fetch_story_normalised(self):
        story = ts.fetch_story(self.base, 1)
        self.assertEqual(story["title"], "Rust wins again")
        self.assertEqual(story["score"], 142)
        self.assertEqual(story["source"], "hackernews")
        self.assertEqual(story["by"], "alice")

    def test_fetch_feed_skips_jobs_and_missing_url(self):
        stories = ts.fetch_feed(self.base, "top")
        ids = [s["id"] for s in stories]
        self.assertEqual(ids, [1, 2])  # job id 3 skipped
        self.assertEqual(stories[1]["url"], "")  # story 2 has no url
        self.assertEqual(stories[0]["feed"], "top")

    def test_fetch_feed_limit(self):
        self.assertEqual(len(ts.fetch_feed(self.base, "top", limit=1)), 1)


class TestConfig(unittest.TestCase):
    def test_parse_all_forms(self):
        cfg = ts.parse_config(
            "# comment\nmin_score: 50\nkeywords:\n  - rust\n  - python\n"
            "sources: [hackernews]\nmax_age_hours: 48\n")
        self.assertEqual(cfg["min_score"], 50)
        self.assertEqual(cfg["keywords"], ["rust", "python"])
        self.assertEqual(cfg["sources"], ["hackernews"])
        self.assertEqual(cfg["max_age_hours"], 48)

    def test_parse_defaults(self):
        cfg = ts.parse_config("")
        self.assertEqual(cfg["min_score"], 0)
        self.assertEqual(cfg["keywords"], [])
        self.assertIsNone(cfg["max_age_hours"])

    def test_parse_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            ts.parse_config("bogus: 1\n")

    def test_parse_bad_int_raises(self):
        with self.assertRaises(ValueError):
            ts.parse_config("min_score: lots\n")

    def test_story_matches(self):
        story = {"title": "Rust wins again", "score": 142,
                 "source": "hackernews", "time": 1700000000}
        cfg = {"min_score": 50, "keywords": ["rust"], "sources": ["hackernews"],
               "max_age_hours": None}
        self.assertTrue(ts.story_matches(story, cfg))
        self.assertFalse(ts.story_matches(story, {**cfg, "min_score": 200}))
        self.assertFalse(ts.story_matches(story, {**cfg, "keywords": ["go"]}))
        self.assertFalse(ts.story_matches(story, {**cfg, "sources": ["reddit"]}))
        # max_age_hours with explicit now: story is 3600s old, limit 0h -> out
        self.assertFalse(ts.story_matches(
            story, {**cfg, "max_age_hours": 0},
            now=1700000000 + 3600))
        self.assertTrue(ts.story_matches(
            story, {**cfg, "max_age_hours": 48}, now=1700000000 + 3600))

    def test_load_config_missing_file_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = ts.load_config(str(Path(td) / "nope.yaml"))
            self.assertEqual(cfg["min_score"], 0)


class TestTopicLog(unittest.TestCase):
    def test_append_dedup_and_read(self):
        with tempfile.TemporaryDirectory() as td:
            log = str(Path(td) / "hn-stories.jsonl")
            stories = [dict(FIXTURES["/v0/item/1.json"], source="hackernews"),
                       dict(FIXTURES["/v0/item/2.json"], source="hackernews")]
            self.assertEqual(ts.append_to_log(log, stories), 2)
            self.assertEqual(ts.append_to_log(log, stories), 0)  # dedup
            store = ts.read_log(log)
            self.assertEqual(sorted(store), [1, 2])

    def test_read_missing_and_corrupt(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "hn-stories.jsonl"
            self.assertEqual(ts.read_log(str(log)), {})
            log.write_text('{"id": 9, "title": "ok"}\nnot json\n{"id": 10}\n')
            store = ts.read_log(str(log))
            self.assertEqual(sorted(store), [9, 10])


class TestAPI(ServerMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = str(Path(self.tmp.name) / "hn-stories.jsonl")
        stories = [
            {"id": 1, "title": "Rust wins again", "url": "https://x/1",
             "score": 142, "by": "alice", "time": 1700000000,
             "type": "story", "source": "hackernews", "feed": "top"},
            {"id": 2, "title": "Python tips", "url": "https://x/2",
             "score": 20, "by": "bob", "time": 1700000100,
             "type": "story", "source": "hackernews", "feed": "top"},
            {"id": 4, "title": "Rust for beginners", "url": "https://x/4",
             "score": 5, "by": "dave", "time": 1700000300,
             "type": "story", "source": "hackernews", "feed": "new"},
        ]
        ts.append_to_log(self.log, stories)
        cfg = {"min_score": 10, "keywords": [], "sources": [],
               "max_age_hours": None}
        frontend = str(Path(__file__).resolve().parent.parent / "frontend" / "index.html")
        self.base = self._start(ts.make_handler(self.log, cfg, frontend))

    def tearDown(self):
        self._stop()
        self.tmp.cleanup()

    def _get(self, path):
        with urllib.request.urlopen(self.base + path) as resp:
            return resp.status, resp.read().decode()

    def test_stories_newest_first_and_config_filter(self):
        _, body = self._get("/stories")
        ids = [s["id"] for s in json.loads(body)]
        self.assertEqual(ids, [2, 1])  # id 4 dropped by min_score=10; newest first

    def test_stories_top_score_order(self):
        _, body = self._get("/stories/top")
        ids = [s["id"] for s in json.loads(body)]
        self.assertEqual(ids, [1, 2])

    def test_query_filters(self):
        _, body = self._get("/stories?min_score=100")
        self.assertEqual([s["id"] for s in json.loads(body)], [1])
        _, body = self._get("/stories?keyword=rust")
        self.assertEqual([s["id"] for s in json.loads(body)], [1])
        _, body = self._get("/stories?source=reddit")
        self.assertEqual(json.loads(body), [])
        _, body = self._get("/stories?since=1700000050")
        self.assertEqual([s["id"] for s in json.loads(body)], [2])
        _, body = self._get("/stories/top?limit=1")
        self.assertEqual([s["id"] for s in json.loads(body)], [1])

    def test_frontend_and_404(self):
        _, body = self._get("/")
        self.assertIn("Top Programming Stories", body)
        try:
            self._get("/nope")
            self.fail("expected HTTPError")
        except Exception as exc:  # urllib.error.HTTPError
            self.assertEqual(getattr(exc, "code", None), 404)
            self.assertIn("not found", exc.read().decode())


if __name__ == "__main__":
    unittest.main()

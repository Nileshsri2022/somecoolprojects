#!/usr/bin/env python3
"""Top Programming Stories Dashboard.

Coding Challenges: "Build Your Own Top Programming Stories Dashboard"
(Step Zero + Steps 1-5). Python 3 standard library only.

Deliberate divergence, stated in docs/SPEC.md and README.md: there is
no real Kafka/Aiven cluster in this build (no account was created, no
credentials invented). The ``hn-stories`` topic is a local JSON-lines
append-log (default ``hn-stories.jsonl``); each line is one JSON story
message, the format a Kafka producer would carry. The scraper polls
Hacker News every 60 seconds by default, the backend re-reads the log
into an in-memory store per request, applies the instance config
(``config.yaml``) filter, and serves ``/stories``, ``/stories/top``
and the static frontend.

Subcommands:
    scrape   fetch top/new stories once and print them as JSON lines
    produce  poll HN and append new stories to the topic log
    serve    serve the API + frontend from the topic log

Run ``python3 top_stories.py <subcommand> --help`` for options.
Reddit multi-source aggregation (Going Further) is NOT built; see
docs/SPEC.md for why. Every story carries a ``source`` field and the
API supports ``?source=`` filtering, so a future source plugs in here.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HN_DEFAULT_BASE = "https://hacker-news.firebaseio.com/v0"
DEFAULT_LOG = "hn-stories.jsonl"
DEFAULT_CONFIG = "config.yaml"
DEFAULT_FRONTEND = "frontend/index.html"
FRONTEND_REFRESH_MS = 30000

CONFIG_KEYS = ("min_score", "keywords", "sources", "max_age_hours")


# ---------------------------------------------------------------- HN client

def fetch_json(url, timeout=15):
    """GET a URL and parse its JSON body. Raises on non-200/bad JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": "top-stories-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise ValueError("HTTP %s from %s" % (resp.status, url))
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP %s from %s" % (exc.code, url)) from exc


def fetch_story_ids(base, feed):
    """Return the list of story IDs for feed 'top' or 'new'."""
    if feed not in ("top", "new"):
        raise ValueError("feed must be 'top' or 'new', got %r" % feed)
    ids = fetch_json("%s/%sstories.json" % (base.rstrip("/"), feed))
    if not isinstance(ids, list):
        raise ValueError("expected a list of IDs from %sstories" % feed)
    return ids


def normalise_story(raw, feed):
    """Normalise one raw HN item into a story dict, or None to skip.

    Only type == 'story' items are kept. Missing url/score/time get
    neutral defaults; nothing else is invented.
    """
    if not isinstance(raw, dict):
        return None
    if raw.get("type") != "story":
        return None
    if raw.get("dead") or raw.get("deleted"):
        return None
    story_id = raw.get("id")
    if story_id is None:
        return None
    return {
        "id": story_id,
        "title": raw.get("title") or "",
        "url": raw.get("url") or "",
        "score": raw.get("score") or 0,
        "by": raw.get("by") or "",
        "time": raw.get("time") or 0,
        "type": "story",
        "source": "hackernews",
        "feed": feed,
    }


def fetch_story(base, story_id):
    """Fetch and normalise one story, or None if it should be skipped."""
    raw = fetch_json("%s/item/%s.json" % (base.rstrip("/"), story_id))
    return normalise_story(raw, feed="")  # feed filled in by fetch_feed


def fetch_feed(base, feed, limit=30):
    """Fetch the top/new feed: IDs, then each story, skipping non-stories."""
    stories = []
    for story_id in fetch_story_ids(base, feed)[:limit]:
        try:
            story = fetch_story(base, story_id)
        except ValueError as exc:
            print("warning: skipping story %s: %s" % (story_id, exc), file=sys.stderr)
            continue
        if story is not None:
            story["feed"] = feed
            stories.append(story)
    return stories


# ---------------------------------------------------------------- topic log

def read_log(path):
    """Read the topic log into a dict keyed by story id (latest wins).

    Missing file -> {}. A corrupt line is skipped with a warning, never
    fatal, so one bad line cannot kill the API.
    """
    stories = {}
    p = Path(path)
    if not p.exists():
        return stories
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                story = json.loads(line)
            except json.JSONDecodeError:
                print("warning: skipping corrupt log line: %r" % line[:80], file=sys.stderr)
                continue
            if isinstance(story, dict) and story.get("id") is not None:
                stories[story["id"]] = story
    return stories


def append_to_log(path, stories):
    """Append stories not already in the log. Returns the count appended."""
    existing = read_log(path)
    new = [s for s in stories if s["id"] not in existing]
    if not new:
        return 0
    p = Path(path)
    if p.parent != Path("."):
        p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for story in new:
            fh.write(json.dumps(story, sort_keys=True) + "\n")
    return len(new)


# ---------------------------------------------------------------- config

def _parse_scalar(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    return value.strip("\"'")


def parse_config(text):
    """Parse the small config.yaml subset documented in docs/SPEC.md.

    Raises ValueError on unknown keys or non-integer integer fields.
    """
    config = {"min_score": 0, "keywords": [], "sources": [], "max_age_hours": None}
    current_list = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith(" ") or line.startswith("\t"):
            stripped = line.strip()
            if stripped.startswith("- ") and current_list is not None:
                config[current_list].append(stripped[2:].strip().strip("\"'"))
                continue
            raise ValueError("unexpected indented line: %r" % raw_line)
        if ":" not in line:
            raise ValueError("bad config line (no ':'): %r" % raw_line)
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in CONFIG_KEYS:
            raise ValueError("unknown config key: %r" % key)
        if key in ("keywords", "sources"):
            current_list = key
            if value:
                parsed = _parse_scalar(value)
                if not isinstance(parsed, list):
                    raise ValueError("%s must be a list" % key)
                config[key] = parsed
            continue
        current_list = None
        if key in ("min_score", "max_age_hours"):
            if value == "" or value.lower() in ("null", "~"):
                config[key] = None if key == "max_age_hours" else 0
                continue
            try:
                config[key] = int(value)
            except ValueError:
                raise ValueError("%s must be an integer, got %r" % (key, value)) from None
        else:  # pragma: no cover - all keys handled above
            config[key] = value
    return config


def load_config(path):
    """Load config.yaml, or defaults when the file does not exist."""
    p = Path(path)
    if not p.exists():
        return {"min_score": 0, "keywords": [], "sources": [], "max_age_hours": None}
    return parse_config(p.read_text(encoding="utf-8"))


def story_matches(story, config, now=None):
    """Instance-level (Step 4) filter: True if the story is kept."""
    if story.get("score", 0) < config.get("min_score", 0):
        return False
    keywords = config.get("keywords") or []
    if keywords:
        title = (story.get("title") or "").lower()
        if not any(kw.lower() in title for kw in keywords):
            return False
    sources = config.get("sources") or []
    if sources and story.get("source") not in sources:
        return False
    max_age = config.get("max_age_hours")
    if max_age is not None:
        if now is None:
            now = int(time.time())
        if story.get("time", 0) < now - max_age * 3600:
            return False
    return True


def _int_param(params, name):
    try:
        return int(params[name][0])
    except (KeyError, IndexError, ValueError):
        return None


def apply_query_filters(stories, params):
    """Per-request (Step 3) filters: min_score, keyword, source, since, limit."""
    min_score = _int_param(params, "min_score")
    if min_score is not None:
        stories = [s for s in stories if s.get("score", 0) >= min_score]
    keyword = params.get("keyword", [None])[0] or params.get("q", [None])[0]
    if keyword:
        keyword = keyword.lower()
        stories = [s for s in stories if keyword in (s.get("title") or "").lower()]
    source = params.get("source", [None])[0]
    if source:
        stories = [s for s in stories if s.get("source") == source]
    since = _int_param(params, "since")
    if since is not None:
        stories = [s for s in stories if s.get("time", 0) >= since]
    limit = _int_param(params, "limit")
    if limit is not None and limit >= 0:
        stories = stories[:limit]
    return stories


def load_store(log_path, config):
    """In-memory store for one request: log -> config filter -> list."""
    return [s for s in read_log(log_path).values() if story_matches(s, config)]


# ---------------------------------------------------------------- API server

def make_handler(log_path, config, frontend_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test/server output clean
            pass

        def _send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path in ("/", "/index.html"):
                p = Path(frontend_path)
                if not p.exists():
                    self._send_json(404, {"error": "frontend not found"})
                    return
                body = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path in ("/stories", "/stories/top"):
                stories = load_store(log_path, config)
                if parsed.path == "/stories/top":
                    stories.sort(key=lambda s: (s.get("score", 0), s.get("time", 0)), reverse=True)
                else:
                    stories.sort(key=lambda s: s.get("time", 0), reverse=True)
                stories = apply_query_filters(stories, params)
                self._send_json(200, stories)
                return
            self._send_json(404, {"error": "not found: %s" % parsed.path})

    return Handler


def serve(log_path, config, frontend_path, host, port):
    server = ThreadingHTTPServer((host, port), make_handler(log_path, config, frontend_path))
    print("serving stories API + frontend on http://%s:%s/ (log: %s)"
          % (host, server.server_address[1], log_path))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ---------------------------------------------------------------- CLI

def cmd_scrape(args):
    stories = []
    for feed in ("top", "new"):
        stories.extend(fetch_feed(args.base_url, feed, limit=args.limit))
    for story in stories:
        print(json.dumps(story, sort_keys=True))
    return 0


def cmd_produce(args):
    while True:
        try:
            stories = []
            for feed in ("top", "new"):
                stories.extend(fetch_feed(args.base_url, feed, limit=args.limit))
            added = append_to_log(args.log, stories)
            print("poll: fetched %d stories, appended %d new to %s"
                  % (len(stories), added, args.log))
        except ValueError as exc:
            print("poll error: %s (retrying in %ss)" % (exc, args.poll_interval), file=sys.stderr)
        if args.once:
            break
        time.sleep(args.poll_interval)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="top_stories.py",
        description="Top Programming Stories Dashboard: HN scraper, "
        "hn-stories topic log, API and frontend. No real Kafka in this "
        "build -- the topic is a local JSON-lines log (see README.md). "
        "Reddit aggregation is not built.")
    parser.add_argument("--base-url", default=HN_DEFAULT_BASE,
                        help="Hacker News API base URL (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scrape", help="fetch top/new stories once, print as JSON lines")
    p.add_argument("--limit", type=int, default=30, help="stories per feed (default: 30)")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("produce", help="poll HN and append new stories to the topic log")
    p.add_argument("--log", default=DEFAULT_LOG, help="topic log file (default: %(default)s)")
    p.add_argument("--limit", type=int, default=30, help="stories per feed (default: 30)")
    p.add_argument("--poll-interval", type=int, default=60,
                   help="seconds between polls (default: 60)")
    p.add_argument("--once", action="store_true", help="a single poll pass, then exit")
    p.set_defaults(func=cmd_produce)

    p = sub.add_parser("serve", help="serve the API + frontend from the topic log")
    p.add_argument("--log", default=DEFAULT_LOG, help="topic log file (default: %(default)s)")
    p.add_argument("--config", default=DEFAULT_CONFIG,
                   help="config.yaml path (default: %(default)s; missing file = accept all)")
    p.add_argument("--frontend", default=DEFAULT_FRONTEND,
                   help="frontend HTML file (default: %(default)s)")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default: %(default)s)")
    p.add_argument("--port", type=int, default=8000, help="port (default: %(default)s)")
    p.set_defaults(func=None)  # handled specially in main (needs config load)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        try:
            config = load_config(args.config)
        except ValueError as exc:
            print("error: bad config %s: %s" % (args.config, exc), file=sys.stderr)
            return 2
        serve(args.log, config, args.frontend, args.host, args.port)
        return 0
    try:
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

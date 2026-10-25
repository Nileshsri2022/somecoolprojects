#!/usr/bin/env python3
"""Social media posting/management tool (local-only core).

Draft, edit, schedule and post text posts to LinkedIn and X via LOCAL
FAKE platform adapters. No real platform is ever contacted, no real
credential is used, and nothing is posted to a real account.

Placeholder credential names only (never read for a network call):
  LINKEDIN_ACCESS_TOKEN, X_BEARER_TOKEN

Storage: a single SQLite file (posts + jobs tables).
Queue: the jobs table. Scheduler: poll for due scheduled posts.
Interface: CLI (see --help). Python 3 standard library only.

Usage examples:
  python3 smtool.py create --platform x --author ada --body "Hello" --now
  python3 smtool.py create --platform linkedin --author ada --body "Hi" \\
      --schedule-at 2026-10-26T10:00:00Z
  python3 smtool.py list
  python3 smtool.py edit 1 --body "Edited" --schedule-at 2026-10-27T09:00:00Z
  python3 smtool.py run-due
  python3 smtool.py worker --once
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------- limits

PLATFORMS = {
    "linkedin": {"max_chars": 3000, "visibilities": ("public", "connections")},
    "x": {"max_chars": 280, "visibilities": ("public",)},
}

STATUSES = ("draft", "scheduled", "queued", "posted", "failed", "cancelled")
EDITABLE = ("draft", "scheduled")
DEFAULT_DB = "social-media-tool.db"


class SmError(Exception):
    """User-facing error: CLI prints the message and exits non-zero."""


# ------------------------------------------------------------------ time

def parse_time(value):
    """Parse ISO-8601 to an aware UTC datetime; naive input means UTC."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise SmError(f"unparseable time: {value!r} (expected ISO-8601, e.g. 2026-10-26T10:00:00Z)")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fmt_time(moment):
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


# ------------------------------------------------------------- validation

def validate_post(platform, body, visibility):
    platform = platform.lower()
    if platform not in PLATFORMS:
        raise SmError(f"unknown platform: {platform!r} (expected linkedin or x)")
    if not body or not body.strip():
        raise SmError("post body must not be blank")
    spec = PLATFORMS[platform]
    if len(body) > spec["max_chars"]:
        raise SmError(
            f"body is {len(body)} characters, over the {platform} limit "
            f"of {spec['max_chars']}")
    if visibility not in spec["visibilities"]:
        raise SmError(
            f"visibility {visibility!r} is not allowed for {platform} "
            f"(allowed: {', '.join(spec['visibilities'])})")
    return platform


# --------------------------------------------------------------- adapters

class FakeAdapter:
    """Local fake platform adapter: validates, fabricates an id.

    Makes NO network request. A real adapter would implement post()
    against the platform REST API; the signature is kept identical.
    """

    def __init__(self, platform):
        self.platform = platform

    def post(self, post):
        validate_post(post["platform"], post["body"], post["visibility"])
        # Local simulation only -- no HTTP, no credential, no real account.
        return f"{self.platform}:{post['id']}"


ADAPTERS = {name: FakeAdapter(name) for name in PLATFORMS}


def get_adapter(platform):
    try:
        return ADAPTERS[platform]
    except KeyError:
        raise SmError(f"unknown platform: {platform!r}")


# ------------------------------------------------------------------ store

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    platform TEXT NOT NULL,
    body TEXT NOT NULL,
    visibility TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    posted_at TEXT,
    platform_post_id TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    error TEXT,
    FOREIGN KEY (post_id) REFERENCES posts(id)
);
"""


class Store:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def _row(self, row):
        return dict(row) if row is not None else None

    # -- posts ------------------------------------------------------

    def create_post(self, author, platform, body, visibility="public",
                    now=False, scheduled_at=None):
        if not author or not author.strip():
            raise SmError("author must not be blank")
        platform = validate_post(platform, body, visibility)
        if now and scheduled_at is not None:
            raise SmError("--now and --schedule-at are mutually exclusive")
        sched = None
        if scheduled_at is not None:
            status = "scheduled"
            sched = fmt_time(scheduled_at)
        elif now:
            status = "queued"  # caller enqueues + drains immediately
        else:
            status = "draft"
        stamp = fmt_time(now_utc())
        cur = self.conn.execute(
            "INSERT INTO posts (author, platform, body, visibility, status,"
            " scheduled_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (author.strip(), platform, body, visibility, status, sched,
             stamp, stamp))
        self.conn.commit()
        post = self.get_post(cur.lastrowid)
        if now:
            self.enqueue_job(post["id"])
            self.drain_queue()
            post = self.get_post(post["id"])
        return post

    def get_post(self, post_id):
        row = self.conn.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise SmError(f"no post with id {post_id}")
        return self._row(row)

    def list_posts(self, status=None, platform=None, author=None):
        query = "SELECT * FROM posts WHERE 1=1"
        args = []
        if status is not None:
            if status not in STATUSES:
                raise SmError(f"unknown status: {status!r}")
            query += " AND status = ?"
            args.append(status)
        if platform is not None:
            query += " AND platform = ?"
            args.append(platform.lower())
        if author is not None:
            query += " AND author = ?"
            args.append(author)
        query += " ORDER BY id DESC"
        return [self._row(r) for r in self.conn.execute(query, args)]

    def edit_post(self, post_id, body=None, visibility=None,
                  scheduled_at=None, clear_schedule=False):
        post = self.get_post(post_id)
        if post["status"] not in EDITABLE:
            raise SmError(
                f"cannot edit a {post['status']} post (only draft/scheduled "
                "posts can be edited)")
        if (body is None and visibility is None and scheduled_at is None
                and not clear_schedule):
            raise SmError("edit needs at least one change: --body, "
                          "--visibility, --schedule-at or --clear-schedule")
        if clear_schedule and scheduled_at is not None:
            raise SmError("--clear-schedule and --schedule-at conflict")
        new_body = post["body"] if body is None else body
        new_vis = post["visibility"] if visibility is None else visibility
        validate_post(post["platform"], new_body, new_vis)
        if clear_schedule:
            new_sched, new_status = None, "draft"
        elif scheduled_at is not None:
            new_sched, new_status = fmt_time(scheduled_at), "scheduled"
        else:
            new_sched, new_status = post["scheduled_at"], post["status"]
        self.conn.execute(
            "UPDATE posts SET body=?, visibility=?, scheduled_at=?,"
            " status=?, updated_at=? WHERE id=?",
            (new_body, new_vis, new_sched, new_status,
             fmt_time(now_utc()), post_id))
        self.conn.commit()
        return self.get_post(post_id)

    def cancel_post(self, post_id):
        post = self.get_post(post_id)
        if post["status"] not in EDITABLE:
            raise SmError(
                f"cannot cancel a {post['status']} post (only "
                "draft/scheduled posts can be cancelled)")
        self.conn.execute(
            "UPDATE posts SET status='cancelled', updated_at=? WHERE id=?",
            (fmt_time(now_utc()), post_id))
        self.conn.commit()
        return self.get_post(post_id)

    # -- queue / scheduler ------------------------------------------

    def enqueue_job(self, post_id):
        cur = self.conn.execute(
            "INSERT INTO jobs (post_id, status, created_at) VALUES (?,?,?)",
            (post_id, "pending", fmt_time(now_utc())))
        self.conn.commit()
        return cur.lastrowid

    def drain_queue(self):
        """Post every pending job via its platform adapter. Returns jobs."""
        done = []
        pending = self.conn.execute(
            "SELECT * FROM jobs WHERE status='pending' ORDER BY id").fetchall()
        for job in pending:
            job = dict(job)
            self.conn.execute("UPDATE jobs SET status='processing' WHERE id=?",
                              (job["id"],))
            self.conn.commit()
            post = self.get_post(job["post_id"])
            try:
                platform_id = get_adapter(post["platform"]).post(post)
            except Exception as exc:  # adapter failure: record, don't lose
                self.conn.execute(
                    "UPDATE jobs SET status='failed', error=? WHERE id=?",
                    (str(exc), job["id"]))
                self.conn.execute(
                    "UPDATE posts SET status='failed', error=?, updated_at=?"
                    " WHERE id=?",
                    (str(exc), fmt_time(now_utc()), post["id"]))
                self.conn.commit()
                job["status"], job["error"] = "failed", str(exc)
            else:
                stamp = fmt_time(now_utc())
                self.conn.execute(
                    "UPDATE jobs SET status='done' WHERE id=?", (job["id"],))
                self.conn.execute(
                    "UPDATE posts SET status='posted', posted_at=?,"
                    " platform_post_id=?, error=NULL, updated_at=?"
                    " WHERE id=?",
                    (stamp, platform_id, stamp, post["id"]))
                self.conn.commit()
                job["status"] = "done"
            done.append(job)
        return done

    def find_due_posts(self, moment=None):
        moment = fmt_time(moment or now_utc())
        rows = self.conn.execute(
            "SELECT * FROM posts WHERE status='scheduled'"
            " AND scheduled_at IS NOT NULL AND scheduled_at <= ?"
            " ORDER BY id", (moment,)).fetchall()
        return [self._row(r) for r in rows]

    def run_due(self, moment=None):
        """Enqueue + post all due scheduled posts. Returns posted posts."""
        due = self.find_due_posts(moment)
        for post in due:
            self.enqueue_job(post["id"])
        self.drain_queue()
        return [self.get_post(p["id"]) for p in due]

    def post_now(self, post_id):
        post = self.get_post(post_id)
        if post["status"] not in EDITABLE:
            raise SmError(
                f"cannot post a {post['status']} post now (only "
                "draft/scheduled posts can be posted)")
        self.enqueue_job(post_id)
        self.drain_queue()
        return self.get_post(post_id)


# -------------------------------------------------------------------- CLI

def _print_post(post):
    sched = post["scheduled_at"] or "-"
    posted = post["posted_at"] or "-"
    pid = post["platform_post_id"] or "-"
    print(f"[{post['id']}] {post['platform']} | {post['author']} | "
          f"{post['status']} | vis={post['visibility']} | "
          f"scheduled={sched} | posted={posted} | platform_id={pid}")
    print(f"    {post['body']}")
    if post["error"]:
        print(f"    error: {post['error']}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="smtool", description="Local-only social media posting tool "
        "(fake LinkedIn/X adapters; nothing is posted to a real account).")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="SQLite file (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="create a post (draft, now, or scheduled)")
    c.add_argument("--platform", required=True, help="linkedin or x")
    c.add_argument("--author", required=True)
    c.add_argument("--body", required=True)
    c.add_argument("--visibility", default="public")
    c.add_argument("--now", action="store_true", help="post immediately")
    c.add_argument("--schedule-at", default=None,
                   help="ISO-8601 time to schedule the post")

    l = sub.add_parser("list", help="list posts")
    l.add_argument("--status", default=None)
    l.add_argument("--platform", default=None)
    l.add_argument("--author", default=None)

    s = sub.add_parser("show", help="show one post")
    s.add_argument("id", type=int)

    e = sub.add_parser("edit", help="edit a draft/scheduled post")
    e.add_argument("id", type=int)
    e.add_argument("--body", default=None)
    e.add_argument("--visibility", default=None)
    e.add_argument("--schedule-at", default=None)
    e.add_argument("--clear-schedule", action="store_true")

    x = sub.add_parser("cancel", help="cancel a draft/scheduled post")
    x.add_argument("id", type=int)

    p = sub.add_parser("post-now", help="post a draft/scheduled post now")
    p.add_argument("id", type=int)

    sub.add_parser("run-due", help="post all due scheduled posts, once")

    w = sub.add_parser("worker", help="poll and post due posts")
    w.add_argument("--interval", type=float, default=60.0,
                   help="poll interval in seconds (default 60)")
    w.add_argument("--once", action="store_true", help="single pass, then exit")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    store = Store(args.db)
    try:
        if args.command == "create":
            scheduled = parse_time(args.schedule_at) if args.schedule_at else None
            post = store.create_post(args.author, args.platform, args.body,
                                     args.visibility, now=args.now,
                                     scheduled_at=scheduled)
            _print_post(post)
        elif args.command == "list":
            posts = store.list_posts(args.status, args.platform, args.author)
            if not posts:
                print("no posts")
            for post in posts:
                _print_post(post)
        elif args.command == "show":
            _print_post(store.get_post(args.id))
        elif args.command == "edit":
            scheduled = parse_time(args.schedule_at) if args.schedule_at else None
            _print_post(store.edit_post(args.id, body=args.body,
                                        visibility=args.visibility,
                                        scheduled_at=scheduled,
                                        clear_schedule=args.clear_schedule))
        elif args.command == "cancel":
            _print_post(store.cancel_post(args.id))
        elif args.command == "post-now":
            _print_post(store.post_now(args.id))
        elif args.command == "run-due":
            posted = store.run_due()
            if not posted:
                print("no due posts")
            for post in posted:
                _print_post(post)
        elif args.command == "worker":
            if args.once:
                posted = store.run_due()
                print(f"posted {len(posted)} due post(s)" if posted
                      else "no due posts")
            else:
                print("worker running (local fake adapters only); "
                      "Ctrl-C to stop.")
                try:
                    while True:
                        posted = store.run_due()
                        if posted:
                            print(f"posted {len(posted)} due post(s)")
                        time.sleep(args.interval)
                except KeyboardInterrupt:
                    print("worker stopped.")
        return 0
    except SmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())

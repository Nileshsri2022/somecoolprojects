#!/usr/bin/env python3
"""Blogging software: local blog core (posts, comments, HTTP preview).

Python 3 standard library only. Storage is SQLite (stdlib ``sqlite3``).
See docs/SPEC.md for the challenge mapping, divergences and scope limits.

Usage:
    python3 blog.py [--db PATH] create --title T --summary S --body B
    python3 blog.py [--db PATH] edit ID [--title T] [--summary S] [--body B]
    python3 blog.py [--db PATH] list
    python3 blog.py [--db PATH] show ID
    python3 blog.py [--db PATH] comment ID --name N [--email E] --text T
    python3 blog.py [--db PATH] delete ID
    python3 blog.py [--db PATH] serve [--host H] [--port P] [--password PW]

The HTTP server is a LOCAL preview only (default 127.0.0.1:8080).
Do not expose it to the public internet: the editor password gate is
local-only (unsalted hash cookie, no CSRF protection, no HTTPS).
"""

import argparse
import hashlib
import html
import re
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_PASSWORD = "admin"
COOKIE_NAME = "blog_admin"


# ---------------------------------------------------------------- store
def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BlogStore:
    """SQLite-backed posts + comments."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS posts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',"
            "body TEXT NOT NULL DEFAULT '',"
            "published_at TEXT NOT NULL,"
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS comments ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "post_id INTEGER NOT NULL REFERENCES posts(id),"
            "name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',"
            "body TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def create_post(self, title, summary="", body="", published_at=None):
        title = (title or "").strip()
        body = body or ""
        if not title:
            raise ValueError("title must not be empty")
        if not body.strip():
            raise ValueError("body must not be empty")
        now = _now_iso()
        published_at = published_at or now
        cur = self.conn.execute(
            "INSERT INTO posts (title, summary, body, published_at,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (title, summary or "", body, published_at, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_post(self, post_id):
        row = self.conn.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_posts(self):
        rows = self.conn.execute(
            "SELECT * FROM posts ORDER BY published_at DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_post(self, post_id, title=None, summary=None, body=None,
                    published_at=None):
        post = self.get_post(post_id)
        if post is None:
            raise LookupError(f"no post with id {post_id}")
        new_title = post["title"] if title is None else title.strip()
        new_body = post["body"] if body is None else body
        if not new_title:
            raise ValueError("title must not be empty")
        if not new_body.strip():
            raise ValueError("body must not be empty")
        self.conn.execute(
            "UPDATE posts SET title=?, summary=?, body=?, published_at=?,"
            " updated_at=? WHERE id=?",
            (new_title,
             post["summary"] if summary is None else summary,
             new_body,
             post["published_at"] if published_at is None else published_at,
             _now_iso(), post_id),
        )
        self.conn.commit()
        return self.get_post(post_id)

    def delete_post(self, post_id):
        if self.get_post(post_id) is None:
            raise LookupError(f"no post with id {post_id}")
        self.conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        self.conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        self.conn.commit()

    def add_comment(self, post_id, name, email="", body=""):
        if self.get_post(post_id) is None:
            raise LookupError(f"no post with id {post_id}")
        name = (name or "").strip()
        body = body or ""
        if not name:
            raise ValueError("name must not be empty")
        if not body.strip():
            raise ValueError("comment must not be empty")
        cur = self.conn.execute(
            "INSERT INTO comments (post_id, name, email, body, created_at)"
            " VALUES (?,?,?,?,?)",
            (post_id, name, email or "", body, _now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_comments(self, post_id):
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE post_id = ?"
            " ORDER BY created_at DESC, id DESC",
            (post_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------- markdown
def _inline(text):
    """Inline Markdown on already-escaped text."""
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    def _link(m):
        label, url = m.group(1), m.group(2)
        if url.startswith(("http://", "https://", "/")):
            return f'<a href="{url}">{label}</a>'
        return label

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)


def markdown_to_html(text):
    """Small Markdown subset: headings, lists, paragraphs, inline styles.

    Raw HTML in the input is escaped first, so it is never rendered.
    """
    out = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(html.escape(m.group(2)))}</h{level}>")
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(_inline(html.escape(
                    re.sub(r"^[-*]\s+", "", lines[i].strip()))))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        para = []
        while i < len(lines) and lines[i].strip():
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(html.escape(' '.join(para)))}</p>")
    return "\n".join(out)


# ------------------------------------------------------------ rendering
def layout(title, body):
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        f"<meta charset=\"utf-8\">\n<title>{html.escape(title)}</title>\n"
        "</head>\n<body>\n"
        "<header><h1><a href=\"/\">My Blog</a></h1>"
        "<p><a href=\"/editor\">Editor</a> | "
        "<a href=\"/feed.xml\">RSS</a></p></header>\n"
        f"<main>\n{body}\n</main>\n</body>\n</html>"
    )


def render_index(posts):
    if not posts:
        body = "<h2>Posts</h2>\n<p>No posts yet.</p>"
    else:
        items = "".join(
            f"<li><a href=\"/posts/{p['id']}\">{html.escape(p['title'])}</a>"
            f" — {html.escape(p['published_at'])}"
            + (f"<br>{html.escape(p['summary'])}" if p["summary"] else "")
            + "</li>\n"
            for p in posts
        )
        body = f"<h2>Posts</h2>\n<ul>\n{items}</ul>"
    return layout("My Blog", body)


def render_post(post, comments, error=None):
    body = f"<h1>{html.escape(post['title'])}</h1>\n"
    body += f"<p><em>Published {html.escape(post['published_at'])}</em></p>\n"
    if post["summary"]:
        body += f"<p><strong>{html.escape(post['summary'])}</strong></p>\n"
    body += markdown_to_html(post["body"]) + "\n"
    body += "<h2>Comments</h2>\n"
    if error:
        body += f"<p><strong>Error: {html.escape(error)}</strong></p>\n"
    if not comments:
        body += "<p>No comments yet.</p>\n"
    else:
        for c in comments:
            # Email is stored but deliberately never displayed.
            body += (
                f"<article><p><strong>{html.escape(c['name'])}</strong>"
                f" — {html.escape(c['created_at'])}</p>\n"
                f"<p>{html.escape(c['body'])}</p></article>\n"
            )
    body += (
        f"<h3>Leave a comment</h3>\n"
        f"<form method=\"post\" action=\"/posts/{post['id']}/comments\">\n"
        "<p>Name: <input name=\"name\"></p>\n"
        "<p>Email: <input name=\"email\"></p>\n"
        "<p>Comment:<br><textarea name=\"comment\" rows=\"4\" cols=\"60\">"
        "</textarea></p>\n"
        "<p><button type=\"submit\">Post comment</button></p>\n</form>"
    )
    return layout(post["title"], body)


def render_editor_index(posts):
    items = "".join(
        f"<li><a href=\"/posts/{p['id']}\">{html.escape(p['title'])}</a>"
        f" — <a href=\"/editor/post/{p['id']}\">Edit</a></li>\n"
        for p in posts
    )
    body = ("<h2>Editor</h2>\n<p><a href=\"/editor/post\">New post</a></p>\n"
            f"<ul>\n{items}</ul>" if posts else
            "<h2>Editor</h2>\n<p><a href=\"/editor/post\">New post</a></p>\n"
            "<p>No posts yet.</p>")
    return layout("Editor", body)


def render_post_form(post=None, error=None):
    post = post or {}
    is_edit = bool(post.get("id"))
    action = f"/editor/post/{post['id']}" if is_edit else "/editor/post"
    heading = "Edit post" if is_edit else "New post"
    body = f"<h2>{heading}</h2>\n"
    if error:
        body += f"<p><strong>Error: {html.escape(error)}</strong></p>\n"
    body += (
        f"<form method=\"post\" action=\"{action}\">\n"
        f"<p>Title: <input name=\"title\" size=\"60\" value=\""
        f"{html.escape(post.get('title', ''), quote=True)}\"></p>\n"
        f"<p>Summary: <input name=\"summary\" size=\"60\" value=\""
        f"{html.escape(post.get('summary', ''), quote=True)}\"></p>\n"
        f"<p>Published at: <input name=\"published_at\" size=\"30\" value=\""
        f"{html.escape(post.get('published_at', ''), quote=True)}\"></p>\n"
        "<p>Post (Markdown):<br><textarea name=\"body\" rows=\"15\" cols=\"70\">"
        f"{html.escape(post.get('body', ''))}</textarea></p>\n"
        "<p><button type=\"submit\">Save post</button></p>\n</form>"
    )
    return layout(heading, body)


def render_login(error=None):
    body = "<h2>Login</h2>\n"
    if error:
        body += f"<p><strong>Error: {html.escape(error)}</strong></p>\n"
    body += (
        "<form method=\"post\" action=\"/login\">\n"
        "<p>Password: <input type=\"password\" name=\"password\"></p>\n"
        "<p><button type=\"submit\">Log in</button></p>\n</form>"
    )
    return layout("Login", body)


def render_feed(posts):
    items = ""
    for p in posts:
        items += (
            "<item>"
            f"<title>{html.escape(p['title'])}</title>"
            f"<link>/posts/{p['id']}</link>"
            f"<description>{html.escape(p['summary'])}</description>"
            f"<pubDate>{html.escape(p['published_at'])}</pubDate>"
            "</item>\n"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\"><channel>"
        "<title>My Blog</title><link>/</link>"
        "<description>My Blog feed</description>\n"
        f"{items}</channel></rss>"
    )


# ----------------------------------------------------------------- HTTP
def _auth_token(password):
    return hashlib.sha256(password.encode()).hexdigest()


def make_handler(store, password):
    token = _auth_token(password)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        # -- helpers
        def _send(self, code, body, content_type="text/html; charset=utf-8",
                  extra=None):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location, extra=None):
            self.send_response(302)
            self.send_header("Location", location)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _authenticated(self):
            cookie = self.headers.get("Cookie", "")
            for part in cookie.split(";"):
                part = part.strip()
                if part.startswith(COOKIE_NAME + "="):
                    return part.split("=", 1)[1] == token
            return False

        def _form(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode() if length else ""
            parsed = parse_qs(raw)
            return {k: v[0] for k, v in parsed.items()}

        # -- routing
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, render_index(store.list_posts()))
            elif path == "/feed.xml":
                self._send(200, render_feed(store.list_posts()),
                           "application/rss+xml; charset=utf-8")
            elif path == "/login":
                self._send(200, render_login())
            elif path == "/editor":
                if not self._authenticated():
                    self._redirect("/login")
                else:
                    self._send(200, render_editor_index(store.list_posts()))
            elif path == "/editor/post":
                if not self._authenticated():
                    self._redirect("/login")
                else:
                    self._send(200, render_post_form())
            elif re.fullmatch(r"/posts/\d+", path):
                post = store.get_post(int(path.rsplit("/", 1)[1]))
                if post is None:
                    self._send(404, layout("Not found", "<h2>Not found</h2>"))
                else:
                    self._send(200, render_post(post, store.list_comments(post["id"])))
            elif re.fullmatch(r"/editor/post/\d+", path):
                if not self._authenticated():
                    self._redirect("/login")
                    return
                post = store.get_post(int(path.rsplit("/", 1)[1]))
                if post is None:
                    self._send(404, layout("Not found", "<h2>Not found</h2>"))
                else:
                    self._send(200, render_post_form(post))
            else:
                self._send(404, layout("Not found", "<h2>Not found</h2>"))

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/login":
                form = self._form()
                if form.get("password") == password:
                    self._redirect("/editor",
                                   {"Set-Cookie": f"{COOKIE_NAME}={token}; Path=/"})
                else:
                    self._send(200, render_login("wrong password"))
                return
            m = re.fullmatch(r"/posts/(\d+)/comments", path)
            if m:
                post = store.get_post(int(m.group(1)))
                if post is None:
                    self._send(404, layout("Not found", "<h2>Not found</h2>"))
                    return
                form = self._form()
                try:
                    store.add_comment(post["id"], form.get("name", ""),
                                      form.get("email", ""), form.get("comment", ""))
                except (ValueError, LookupError) as e:
                    self._send(400, render_post(
                        post, store.list_comments(post["id"]), error=str(e)))
                    return
                self._redirect(f"/posts/{post['id']}")
                return
            if path == "/editor/post":
                if not self._authenticated():
                    self._redirect("/login")
                    return
                form = self._form()
                try:
                    pid = store.create_post(
                        form.get("title", ""), form.get("summary", ""),
                        form.get("body", ""),
                        form.get("published_at") or None)
                except ValueError as e:
                    self._send(400, render_post_form(
                        {"title": form.get("title", ""),
                         "summary": form.get("summary", ""),
                         "body": form.get("body", ""),
                         "published_at": form.get("published_at", "")},
                        error=str(e)))
                    return
                self._redirect(f"/posts/{pid}")
                return
            m = re.fullmatch(r"/editor/post/(\d+)", path)
            if m:
                if not self._authenticated():
                    self._redirect("/login")
                    return
                post = store.get_post(int(m.group(1)))
                if post is None:
                    self._send(404, layout("Not found", "<h2>Not found</h2>"))
                    return
                form = self._form()
                try:
                    store.update_post(
                        post["id"], title=form.get("title", ""),
                        summary=form.get("summary", ""),
                        body=form.get("body", ""),
                        published_at=form.get("published_at") or None)
                except ValueError as e:
                    merged = dict(post)
                    merged.update(form)
                    self._send(400, render_post_form(merged, error=str(e)))
                    return
                self._redirect(f"/posts/{post['id']}")
                return
            self._send(404, layout("Not found", "<h2>Not found</h2>"))

    return Handler


def serve(store, host, port, password):
    server = ThreadingHTTPServer((host, port), make_handler(store, password))
    print(f"Serving blog at http://{host}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ------------------------------------------------------------------ CLI
def build_parser():
    p = argparse.ArgumentParser(description="Local blogging software")
    p.add_argument("--db", default="blog.db", help="SQLite file (default blog.db)")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--summary", default="")
    c.add_argument("--body", default="")
    c.add_argument("--body-file")
    c.add_argument("--published-at")

    e = sub.add_parser("edit")
    e.add_argument("id", type=int)
    e.add_argument("--title")
    e.add_argument("--summary")
    e.add_argument("--body")
    e.add_argument("--body-file")
    e.add_argument("--published-at")

    sub.add_parser("list")
    s = sub.add_parser("show")
    s.add_argument("id", type=int)
    cm = sub.add_parser("comment")
    cm.add_argument("id", type=int)
    cm.add_argument("--name", required=True)
    cm.add_argument("--email", default="")
    cm.add_argument("--text", required=True)
    d = sub.add_parser("delete")
    d.add_argument("id", type=int)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default=DEFAULT_HOST)
    sv.add_argument("--port", type=int, default=DEFAULT_PORT)
    sv.add_argument("--password", default=None)
    return p


def _body(args):
    if getattr(args, "body_file", None):
        with open(args.body_file, encoding="utf-8") as f:
            return f.read()
    return getattr(args, "body", "") or ""


def main(argv=None):
    import os
    args = build_parser().parse_args(argv)
    store = BlogStore(args.db)
    try:
        if args.command == "create":
            pid = store.create_post(args.title, args.summary, _body(args),
                                    args.published_at)
            print(pid)
        elif args.command == "edit":
            post = store.update_post(
                args.id, title=args.title, summary=args.summary,
                body=_body(args) if (args.body or args.body_file) else None,
                published_at=args.published_at)
            print(f"updated {post['id']}")
        elif args.command == "list":
            for p in store.list_posts():
                print(f"{p['id']} | {p['published_at']} | {p['title']}")
        elif args.command == "show":
            post = store.get_post(args.id)
            if post is None:
                raise LookupError(f"no post with id {args.id}")
            print(post["title"])
            print(post["summary"])
            print(f"published: {post['published_at']}")
            print(post["body"])
            for c in store.list_comments(args.id):
                print(f"- {c['name']}: {c['body']}")
        elif args.command == "comment":
            cid = store.add_comment(args.id, args.name, args.email, args.text)
            print(cid)
        elif args.command == "delete":
            store.delete_post(args.id)
            print(f"deleted {args.id}")
        elif args.command == "serve":
            password = args.password or os.environ.get("BLOG_PASSWORD") \
                or DEFAULT_PASSWORD
            serve(store, args.host, args.port, password)
    except (ValueError, LookupError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if args.command != "serve":
            store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Notion-like local workspace/docs app (Python standard library only).

Local-only clone of the core concepts from
https://codingchallenges.fyi/challenges/challenge-notion :
register/login, pages, blocks (headings, bullets, bold/italic), a
navigation listing, page duplication, and page reorganisation
(nesting + reordering), stored in one local JSON file.

No real Notion account, API key, or network service is used.
See docs/SPEC.md for divergences and what is NOT built.

Usage: python3 notion.py [--data PATH] <command> [options]
Run `python3 notion.py --help` for the command list.
"""

import argparse
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

BLOCK_TYPES = ("heading_1", "heading_2", "heading_3", "paragraph",
               "bulleted_list_item")
DEFAULT_DATA = "notion_workspace.json"
_PBKDF2_ITERATIONS = 200_000


class NotionError(ValueError):
    """Domain error: bad input, unknown id, or permission problem."""


# ---------------------------------------------------------------- passwords

def hash_password(password):
    """Return 'salt_hex$hash_hex' for a password (PBKDF2-HMAC-SHA256)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 _PBKDF2_ITERATIONS)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    """Constant-time check of a password against a stored salt$hash."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex),
                                     _PBKDF2_ITERATIONS)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# ---------------------------------------------------------------- workspace

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Workspace:
    """A JSON-backed store: users + pages. All mutations save at once."""

    def __init__(self, path):
        self.path = path
        self.users = {}
        self.pages = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.users = data.get("users", {})
            self.pages = data.get("pages", {})

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"users": self.users, "pages": self.pages}, fh,
                      indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, self.path)

    # ---- users ------------------------------------------------------
    def register_user(self, username, password):
        if not username or not password:
            raise NotionError("username and password must not be empty")
        if username in self.users:
            raise NotionError("user %r already exists" % username)
        self.users[username] = {"username": username,
                                "password_hash": hash_password(password),
                                "created_at": _now_iso()}
        self.save()
        return self.users[username]

    def authenticate(self, username, password):
        user = self.users.get(username)
        if user is None or not verify_password(password,
                                               user["password_hash"]):
            raise NotionError("invalid username or password")
        return user

    # ---- page helpers ----------------------------------------------
    def _page_for_user(self, username, page_id):
        page = self.pages.get(page_id)
        if page is None:
            raise NotionError("no such page: %s" % page_id)
        if page["owner"] != username:
            raise NotionError("page %s does not belong to %s"
                              % (page_id, username))
        return page

    def siblings(self, username, parent_id):
        """Pages of `username` under `parent_id`, in order."""
        sibs = [p for p in self.pages.values()
                if p["owner"] == username and p["parent_id"] == parent_id]
        sibs.sort(key=lambda p: (p["order"], p["created_at"], p["id"]))
        return sibs

    def children_of(self, username, parent_id):
        return self.siblings(username, parent_id)

    def _renumber(self, username, parent_id):
        for i, page in enumerate(self.siblings(username, parent_id)):
            page["order"] = i

    def _is_descendant(self, page_id, ancestor_id):
        """True if page_id is ancestor_id or below it (walk up parents)."""
        cur = self.pages.get(page_id)
        seen = set()
        while cur is not None and cur["id"] not in seen:
            if cur["id"] == ancestor_id:
                return True
            seen.add(cur["id"])
            cur = self.pages.get(cur["parent_id"]) if cur["parent_id"] else None
        return False

    # ---- pages ------------------------------------------------------
    def create_page(self, username, title=None, parent_id=None):
        if parent_id is not None:
            self._page_for_user(username, parent_id)  # ownership check
        order = len(self.siblings(username, parent_id))
        page = {"id": str(uuid.uuid4()), "owner": username,
                "title": title or "Untitled", "parent_id": parent_id,
                "order": order, "blocks": [],
                "created_at": _now_iso(), "updated_at": _now_iso()}
        self.pages[page["id"]] = page
        self.save()
        return page

    def update_title(self, username, page_id, title):
        page = self._page_for_user(username, page_id)
        if not title:
            raise NotionError("title must not be empty")
        page["title"] = title
        page["updated_at"] = _now_iso()
        self.save()
        return page

    def delete_page(self, username, page_id):
        """Recursively delete a page and its children (library-only)."""
        page = self._page_for_user(username, page_id)
        parent_id = page["parent_id"]
        for child in list(self.children_of(username, page_id)):
            self.delete_page(username, child["id"])
        del self.pages[page_id]
        self._renumber(username, parent_id)
        self.save()

    def duplicate_page(self, username, page_id):
        """Deep-copy a page + children. Returns the new top-level copy."""
        src = self._page_for_user(username, page_id)
        taken = {p["title"] for p in self.pages.values()
                 if p["owner"] == username}
        base = "Copy of " + src["title"]
        title, n = base, 1
        while title in taken:
            title = "%s (%d)" % (base, n)
            n += 1

        def copy_page(node, parent_id, order):
            new = {"id": str(uuid.uuid4()), "owner": username,
                   "title": node["title"], "parent_id": parent_id,
                   "order": order,
                   "blocks": [{"id": str(uuid.uuid4()), "type": b["type"],
                               "text": b["text"]} for b in node["blocks"]],
                   "created_at": _now_iso(), "updated_at": _now_iso()}
            self.pages[new["id"]] = new
            for i, child in enumerate(self.children_of(username, node["id"])):
                copy_page(child, new["id"], i)
            return new

        new_top = copy_page(src, src["parent_id"],
                            len(self.siblings(username, src["parent_id"])))
        new_top["title"] = title
        self.save()
        return new_top

    def move_page(self, username, page_id, parent_id=None, position=None):
        """Reparent (+ optionally reposition) a page. parent None = top."""
        page = self._page_for_user(username, page_id)
        if parent_id is not None:
            parent = self._page_for_user(username, parent_id)
            if parent_id == page_id or self._is_descendant(parent_id, page_id):
                raise NotionError("cannot move a page under itself or "
                                  "one of its descendants")
        old_parent = page["parent_id"]
        page["parent_id"] = parent_id
        sibs = [p for p in self.siblings(username, parent_id)
                if p["id"] != page_id]
        if position is None:
            position = len(sibs)
        if position < 0 or position > len(sibs):
            raise NotionError("position %r out of range" % (position,))
        sibs.insert(position, page)
        for i, sib in enumerate(sibs):
            sib["order"] = i
        if old_parent != parent_id:
            self._renumber(username, old_parent)
        page["updated_at"] = _now_iso()
        self.save()
        return page

    def reorder_siblings(self, username, parent_id, ordered_ids):
        """Set the exact order of one sibling group (Step 6 navigation)."""
        current = self.siblings(username, parent_id)
        if sorted(p["id"] for p in current) != sorted(ordered_ids):
            raise NotionError("order must list exactly the current siblings")
        by_id = {p["id"]: p for p in current}
        for i, pid in enumerate(ordered_ids):
            by_id[pid]["order"] = i
        self.save()
        return [by_id[pid] for pid in ordered_ids]

    def search(self, username, query):
        """Case-insensitive substring search over own titles + block text."""
        q = query.lower()
        hits = []
        for page in self.pages.values():
            if page["owner"] != username:
                continue
            if q in page["title"].lower() or any(
                    q in b["text"].lower() for b in page["blocks"]):
                hits.append(page)
        hits.sort(key=lambda p: (p["order"], p["created_at"]))
        return hits

    # ---- blocks ------------------------------------------------------
    def add_block(self, username, page_id, block_type, text):
        if block_type not in BLOCK_TYPES:
            raise NotionError("unknown block type %r (expected one of %s)"
                              % (block_type, ", ".join(BLOCK_TYPES)))
        page = self._page_for_user(username, page_id)
        block = {"id": str(uuid.uuid4()), "type": block_type, "text": text}
        page["blocks"].append(block)
        page["updated_at"] = _now_iso()
        self.save()
        return block

    def _block_for_user(self, username, page_id, block_id):
        page = self._page_for_user(username, page_id)
        for block in page["blocks"]:
            if block["id"] == block_id:
                return page, block
        raise NotionError("no such block: %s" % block_id)

    def edit_block(self, username, page_id, block_id, text=None,
                   block_type=None):
        page, block = self._block_for_user(username, page_id, block_id)
        if block_type is not None:
            if block_type not in BLOCK_TYPES:
                raise NotionError("unknown block type %r" % block_type)
            block["type"] = block_type
        if text is not None:
            block["text"] = text
        page["updated_at"] = _now_iso()
        self.save()
        return block

    def delete_block(self, username, page_id, block_id):
        page, block = self._block_for_user(username, page_id, block_id)
        page["blocks"].remove(block)
        page["updated_at"] = _now_iso()
        self.save()

    def move_block(self, username, page_id, block_id, to_index):
        page, block = self._block_for_user(username, page_id, block_id)
        if to_index < 0 or to_index >= len(page["blocks"]):
            raise NotionError("block position %r out of range" % (to_index,))
        page["blocks"].remove(block)
        page["blocks"].insert(to_index, block)
        page["updated_at"] = _now_iso()
        self.save()
        return block


# ---------------------------------------------------------------- rendering

def render_inline(text):
    """Escape HTML, then **bold** -> <strong>, *italic* -> <em>."""
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
    safe = re.sub(r"\*(.+?)\*", r"<em>\1</em>", safe)
    return safe


_BLOCK_TAGS = {"heading_1": "h1", "heading_2": "h2", "heading_3": "h3",
               "paragraph": "p", "bulleted_list_item": "li"}


def render_page_html(ws, username, page):
    """Full HTML for one page (navigation + blocks)."""
    parts = ["<h1>%s</h1>" % html.escape(page["title"])]
    in_list = False
    for block in page["blocks"]:
        if block["type"] == "bulleted_list_item" and not in_list:
            parts.append("<ul>")
            in_list = True
        if block["type"] != "bulleted_list_item" and in_list:
            parts.append("</ul>")
            in_list = False
        tag = _BLOCK_TAGS[block["type"]]
        parts.append("<%s>%s</%s>" % (tag, render_inline(block["text"]), tag))
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


def _nav_html(ws, username, parent_id=None):
    out = []
    for page in ws.children_of(username, parent_id):
        out.append('<li><a href="/page/%s">%s</a>' % (
            page["id"], html.escape(page["title"])))
        kids = _nav_html(ws, username, page["id"])
        if kids:
            out.append("<ul>" + "".join(kids) + "</ul>")
        out.append("</li>")
    return out


def render_workspace_html(ws):
    """Index page: one sidebar section per user, listing their pages."""
    sections = []
    for username in sorted(ws.users):
        nav = _nav_html(ws, username)
        body = ("<ul>" + "".join(nav) + "</ul>") if nav else "<p>(no pages yet)</p>"
        sections.append("<h2>%s's workspace</h2>\n%s\n"
                        "<p>Use the CLI to create a page: "
                        "<code>python3 notion.py create-page --user %s "
                        "--password &lt;password&gt; --title \"New page\"</code></p>"
                        % (html.escape(username), body, html.escape(username)))
    if not sections:
        sections.append("<p>No users yet. Register with the CLI first.</p>")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Notion (local)</title></head><body>"
            "<h1>Notion — local workspace</h1>" + "\n".join(sections) +
            "</body></html>")


# ---------------------------------------------------------------- HTTP view

def make_server(data_path, port):
    """Return a ThreadingHTTPServer bound to 127.0.0.1:port (0 = ephemeral)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, code, body):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            ws = Workspace(data_path)  # reload per request: CLI edits show up
            path = urlparse(self.path).path
            if path in ("/", ""):
                self._send(200, render_workspace_html(ws))
                return
            m = re.match(r"^/page/([0-9a-f-]+)$", unquote(path))
            if m and m.group(1) in ws.pages:
                page = ws.pages[m.group(1)]
                body = ("<!doctype html><html><head><meta charset='utf-8'>"
                        "<title>%s</title></head><body>"
                        "<p><a href='/'>&larr; workspace</a></p>" % html.escape(page["title"]))
                body += render_page_html(ws, page["owner"], page)
                body += "</body></html>"
                self._send(200, body)
                return
            self._send(404, "<h1>404: page not found</h1>")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


# ---------------------------------------------------------------- CLI

def _ws_and_auth(args):
    ws = Workspace(args.data)
    ws.authenticate(args.user, args.password)
    return ws


def build_parser():
    parser = argparse.ArgumentParser(
        prog="notion",
        description="Local-only Notion-like workspace (see docs/SPEC.md).")
    parser.add_argument("--data", default=DEFAULT_DATA,
                        help="JSON store file (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_auth(p):
        p.add_argument("--user", required=True)
        p.add_argument("--password", required=True)

    def add_page(p):
        p.add_argument("--page", required=True)

    p = sub.add_parser("register", help="create a local account")
    add_auth(p)
    p = sub.add_parser("login", help="verify local credentials")
    add_auth(p)
    p = sub.add_parser("create-page", help="create a page")
    add_auth(p)
    p.add_argument("--title", default=None)
    p.add_argument("--parent", default=None)
    p = sub.add_parser("list-pages", help="list own pages, nested + ordered")
    add_auth(p)
    p = sub.add_parser("show-page", help="show a page's title and blocks")
    add_auth(p)
    add_page(p)
    p = sub.add_parser("add-block", help="append a block to a page")
    add_auth(p)
    add_page(p)
    p.add_argument("--type", required=True, choices=BLOCK_TYPES)
    p.add_argument("--text", required=True)
    p = sub.add_parser("edit-block", help="edit a block's text and/or type")
    add_auth(p)
    add_page(p)
    p.add_argument("--block", required=True)
    p.add_argument("--text", default=None)
    p.add_argument("--type", default=None, choices=BLOCK_TYPES)
    p = sub.add_parser("delete-block", help="delete a block from a page")
    add_auth(p)
    add_page(p)
    p.add_argument("--block", required=True)
    p = sub.add_parser("move-block", help="reorder a block within a page")
    add_auth(p)
    add_page(p)
    p.add_argument("--block", required=True)
    p.add_argument("--to", type=int, required=True)
    p = sub.add_parser("duplicate-page", help="duplicate a page + children")
    add_auth(p)
    add_page(p)
    p = sub.add_parser("move-page", help="reparent / reposition a page")
    add_auth(p)
    add_page(p)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--parent", default=None)
    grp.add_argument("--top", action="store_true")
    p.add_argument("--position", type=int, default=None)
    p = sub.add_parser("reorder", help="set exact order of one sibling group")
    add_auth(p)
    p.add_argument("--parent", required=True,
                   help="parent page id, or 'top' for top-level pages")
    p.add_argument("--order", required=True,
                   help="comma-separated page ids, in the new order")
    p = sub.add_parser("search", help="search own titles and block text")
    add_auth(p)
    p.add_argument("query")
    p = sub.add_parser("serve", help="local read-only HTML view")
    p.add_argument("--port", type=int, default=8000)
    return parser


def _print_pages(ws, username, parent_id=None, depth=0):
    for page in ws.children_of(username, parent_id):
        print("%s- %s (%s)" % ("  " * depth, page["title"], page["id"]))
        _print_pages(ws, username, page["id"], depth + 1)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "register":
            ws = Workspace(args.data)
            ws.register_user(args.user, args.password)
            print("registered %s" % args.user)
        elif args.command == "login":
            ws = Workspace(args.data)
            ws.authenticate(args.user, args.password)
            print("login ok: %s" % args.user)
        elif args.command == "create-page":
            ws = _ws_and_auth(args)
            page = ws.create_page(args.user, args.title, args.parent)
            print(page["id"])
        elif args.command == "list-pages":
            ws = _ws_and_auth(args)
            _print_pages(ws, args.user)
        elif args.command == "show-page":
            ws = _ws_and_auth(args)
            page = ws._page_for_user(args.user, args.page)
            print(page["title"])
            for block in page["blocks"]:
                print("[%s] %s" % (block["type"], block["text"]))
        elif args.command == "add-block":
            ws = _ws_and_auth(args)
            block = ws.add_block(args.user, args.page, args.type, args.text)
            print(block["id"])
        elif args.command == "edit-block":
            ws = _ws_and_auth(args)
            ws.edit_block(args.user, args.page, args.block,
                          args.text, args.type)
            print("edited %s" % args.block)
        elif args.command == "delete-block":
            ws = _ws_and_auth(args)
            ws.delete_block(args.user, args.page, args.block)
            print("deleted %s" % args.block)
        elif args.command == "move-block":
            ws = _ws_and_auth(args)
            ws.move_block(args.user, args.page, args.block, args.to)
            print("moved %s" % args.block)
        elif args.command == "duplicate-page":
            ws = _ws_and_auth(args)
            print(ws.duplicate_page(args.user, args.page)["id"])
        elif args.command == "move-page":
            ws = _ws_and_auth(args)
            parent = None if args.top or args.parent is None else args.parent
            # NOTE: --parent omitted means "keep at top" only via --top;
            # without either flag, move-page keeps the current parent:
            if not args.top and args.parent is None:
                parent = ws._page_for_user(args.user, args.page)["parent_id"]
            ws.move_page(args.user, args.page, parent, args.position)
            print("moved %s" % args.page)
        elif args.command == "reorder":
            ws = _ws_and_auth(args)
            parent = None if args.parent == "top" else args.parent
            if parent is not None:
                ws._page_for_user(args.user, parent)
            ids = [s for s in args.order.split(",") if s]
            ws.reorder_siblings(args.user, parent, ids)
            print("reordered %d pages" % len(ids))
        elif args.command == "search":
            ws = _ws_and_auth(args)
            for page in ws.search(args.user, args.query):
                print("%s (%s)" % (page["title"], page["id"]))
        elif args.command == "serve":
            server = make_server(args.data, args.port)
            print("serving local view at http://127.0.0.1:%d/ (Ctrl-C to stop)"
                  % server.server_address[1])
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        else:  # pragma: no cover - argparse enforces the choice
            raise NotionError("unknown command")
    except NotionError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

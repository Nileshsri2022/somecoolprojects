#!/usr/bin/env python3
"""Google Keep (local) — a local note-taking app in the shape of Keep.

Standard library only. One process serves both a REST API and a small
responsive web UI, and the same note store backs a CLI.

    python3 keep.py serve [--host 127.0.0.1] [--port 8000] [--data notes.json]
    python3 keep.py add --title "Groceries" --content "milk, eggs"
    python3 keep.py list [--search QUERY] [--json]
    python3 keep.py get <id> | edit <id> ... | delete <id>
    python3 keep.py pin|unpin|archive|unarchive <id>
    python3 keep.py search QUERY

Data lives in a JSON file (default ``notes.json`` in the current working
directory, or ``KEEP_DATA`` / ``--data``). This is LOCAL ONLY: no Google
account, no cloud sync, no real credentials of any kind. If the
``KEEP_TOKEN`` environment variable is set, API requests must carry
``Authorization: Bearer <token>``; the CLI bypasses it because it owns
the local file directly. See docs/SPEC.md for divergences and limits.
"""

import argparse
import html
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = 1
COLORS = {
    "default", "red", "orange", "yellow", "green",
    "teal", "blue", "purple", "pink", "brown", "gray",
}
MAX_TITLE = 1000
MAX_CONTENT = 50000
ALLOWED_FIELDS = {"title", "content", "color", "labels", "pinned", "archived"}


def _now():
    # Microsecond precision: second-precision stamps made "recently
    # edited first" ordering nondeterministic within the same second.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _clean_labels(labels):
    if not isinstance(labels, list):
        raise ValueError("labels must be a list of strings")
    cleaned = []
    for label in labels:
        if not isinstance(label, str):
            raise ValueError("labels must be a list of strings")
        label = label.strip()
        if label and label not in cleaned:
            cleaned.append(label)
    return cleaned


def validate_fields(fields, partial=False):
    """Validate and clean a create (partial=False) or update dict.

    Raises ValueError on any problem. Unknown fields are rejected.
    """
    if not isinstance(fields, dict):
        raise ValueError("note body must be a JSON object")
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError("unknown field(s): " + ", ".join(sorted(unknown)))
    cleaned = {}
    if "title" in fields:
        title = fields["title"]
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        if len(title) > MAX_TITLE:
            raise ValueError("title must be at most %d characters" % MAX_TITLE)
        cleaned["title"] = title
    if "content" in fields:
        content = fields["content"]
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        if len(content) > MAX_CONTENT:
            raise ValueError("content must be at most %d characters" % MAX_CONTENT)
        cleaned["content"] = content
    if "color" in fields:
        if fields["color"] not in COLORS:
            raise ValueError(
                "color must be one of: " + ", ".join(sorted(COLORS)))
        cleaned["color"] = fields["color"]
    if "labels" in fields:
        cleaned["labels"] = _clean_labels(fields["labels"])
    for flag in ("pinned", "archived"):
        if flag in fields:
            if not isinstance(fields[flag], bool):
                raise ValueError("%s must be a boolean" % flag)
            cleaned[flag] = fields[flag]
    if not partial:
        title = cleaned.get("title", "")
        content = cleaned.get("content", "")
        if not title.strip() and not content.strip():
            raise ValueError("a note needs a non-blank title or content")
    return cleaned


class NoteStore:
    """JSON-file note store. Notes are plain dicts, exactly as served."""

    def __init__(self, path):
        self.path = path
        self.notes = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.notes = {}
            return
        with open(self.path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError("corrupt notes file %s: %s" % (self.path, exc))
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
            raise ValueError("corrupt notes file %s: bad shape" % self.path)
        self.notes = {n["id"]: n for n in data["notes"] if isinstance(n, dict)}

    def save(self):
        tmp = self.path + ".tmp"
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": VERSION, "notes": list(self.notes.values())},
                      f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def create(self, fields):
        cleaned = validate_fields(fields, partial=False)
        note = {
            "id": uuid.uuid4().hex,
            "title": cleaned.get("title", ""),
            "content": cleaned.get("content", ""),
            "color": cleaned.get("color", "default"),
            "labels": cleaned.get("labels", []),
            "pinned": cleaned.get("pinned", False),
            "archived": cleaned.get("archived", False),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.notes[note["id"]] = note
        self.save()
        return note

    def get(self, note_id):
        try:
            return self.notes[note_id]
        except KeyError:
            raise KeyError("no note with id %s" % note_id)

    def update(self, note_id, fields):
        note = self.get(note_id)
        cleaned = validate_fields(fields, partial=True)
        merged = dict(note)
        merged.update(cleaned)
        if not merged["title"].strip() and not merged["content"].strip():
            raise ValueError("a note needs a non-blank title or content")
        merged["updated_at"] = _now()
        self.notes[note_id] = merged
        self.save()
        return merged

    def delete(self, note_id):
        self.get(note_id)  # raises KeyError if unknown
        del self.notes[note_id]
        self.save()

    def list_notes(self, q=None, label=None, pinned=None,
                   archived=None, include_archived=False):
        notes = list(self.notes.values())
        if archived is not None:
            notes = [n for n in notes if n["archived"] == archived]
        elif not include_archived:
            notes = [n for n in notes if not n["archived"]]
        if pinned is not None:
            notes = [n for n in notes if n["pinned"] == pinned]
        if label:
            notes = [n for n in notes if label in n["labels"]]
        if q:
            needle = q.lower()
            notes = [n for n in notes
                     if needle in n["title"].lower()
                     or needle in n["content"].lower()
                     or any(needle in lab.lower() for lab in n["labels"])]
        # Stable sorts, last applied wins: pinned first, then most
        # recently updated, then id ascending as a deterministic tiebreak.
        notes.sort(key=lambda n: n["id"])
        notes.sort(key=lambda n: n["updated_at"], reverse=True)
        notes.sort(key=lambda n: not n["pinned"])
        return notes


# ---------------------------------------------------------------- HTTP API

def _parse_bool(value, name):
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValueError("query flag %s must be true or false" % name)


def make_handler(store, token, lock):
    class KeepHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        # -- helpers -------------------------------------------------
        def _send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status, body):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, message):
            self._send_json(status, {"error": message})

        def _authorized(self):
            if not token:
                return True
            return self.headers.get("Authorization") == "Bearer " + token

        def _read_json(self):
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("application/json"):
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("malformed JSON body")
            if not isinstance(body, dict):
                raise ValueError("note body must be a JSON object")
            return body

        def _route(self):
            """Return (kind, note_id) or None for non-API paths."""
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if parts == ["api", "notes"]:
                return ("collection", None, parsed)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "notes":
                return ("item", parts[2], parsed)
            if parts and parts[0] == "api":
                return ("unknown_api", None, parsed)
            return (None, None, parsed)

        # -- verbs ---------------------------------------------------
        def do_GET(self):
            kind, note_id, parsed = self._route()
            if kind is None:
                if parsed.path == "/":
                    self._send_html(200, UI_HTML)
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "9")
                    self.end_headers()
                    self.wfile.write(b"not found")
                return
            if kind == "unknown_api":
                self._error(404, "unknown API path")
                return
            if not self._authorized():
                self._error(401, "missing or invalid bearer token")
                return
            try:
                with lock:
                    if kind == "collection":
                        query = parse_qs(parsed.query)
                        kwargs = {}
                        if "q" in query:
                            kwargs["q"] = query["q"][0]
                        if "label" in query:
                            kwargs["label"] = query["label"][0]
                        for flag in ("pinned", "archived", "include_archived"):
                            if flag in query:
                                kwargs[flag] = _parse_bool(query[flag][0], flag)
                        self._send_json(200, store.list_notes(**kwargs))
                    else:
                        self._send_json(200, store.get(note_id))
            except KeyError as exc:
                self._error(404, str(exc))
            except ValueError as exc:
                self._error(400, str(exc))

        def _write_note(self):
            kind, note_id, _parsed = self._route()
            if kind not in ("collection", "item"):
                self._error(404, "unknown API path")
                return
            if not self._authorized():
                self._error(401, "missing or invalid bearer token")
                return
            try:
                body = self._read_json()
            except ValueError as exc:
                status = 415 if "Content-Type" in str(exc) else 400
                self._error(status, str(exc))
                return
            try:
                with lock:
                    if self.command == "POST" and kind == "collection":
                        self._send_json(201, store.create(body))
                    elif self.command in ("PUT", "PATCH") and kind == "item":
                        self._send_json(200, store.update(note_id, body))
                    else:
                        self._error(405, "method not allowed for this path")
            except KeyError as exc:
                self._error(404, str(exc))
            except ValueError as exc:
                self._error(400, str(exc))

        do_POST = _write_note
        do_PUT = _write_note
        do_PATCH = _write_note

        def do_DELETE(self):
            kind, note_id, _parsed = self._route()
            if kind != "item":
                self._error(404, "unknown API path")
                return
            if not self._authorized():
                self._error(401, "missing or invalid bearer token")
                return
            try:
                with lock:
                    store.delete(note_id)
            except KeyError as exc:
                self._error(404, str(exc))
                return
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return KeepHandler


UI_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Keep (local)</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#f5f5f5}
h1{font-size:20px} #error{display:none;background:#fdecea;color:#611;padding:8px;margin:8px 0}
form, .card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px;margin:8px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.card{cursor:pointer;white-space:pre-wrap;word-break:break-word}
.card[data-color=red]{background:#f8d7da}.card[data-color=orange]{background:#ffe5c2}
.card[data-color=yellow]{background:#fff3b0}.card[data-color=green]{background:#d4edda}
.card[data-color=teal]{background:#d1ecf1}.card[data-color=blue]{background:#d6e4ff}
.card[data-color=purple]{background:#e2d6ff}.card[data-color=pink]{background:#f8d7e8}
.card[data-color=brown]{background:#e8d5c4}.card[data-color=gray]{background:#e2e3e5}
input,textarea,select{width:100%;box-sizing:border-box;margin:4px 0;padding:6px}
button{margin:2px;padding:6px 10px;cursor:pointer}
#modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.4)}
#modal>div{background:#fff;margin:10% auto;padding:16px;max-width:500px;border-radius:8px}
</style></head><body>
<h1>Keep (local) — notes live only on this machine</h1>
<p><input id="q" placeholder="Search notes…">
<button onclick="load()">Search</button>
<label><input type="checkbox" id="arch"> Show archived</label></p>
<div id="error"></div>
<form onsubmit="addNote(event)">
<input id="title" placeholder="Title">
<textarea id="content" placeholder="Take a note…" rows="3"></textarea>
<select id="color"><option>default</option><option>red</option><option>orange</option>
<option>yellow</option><option>green</option><option>teal</option><option>blue</option>
<option>purple</option><option>pink</option><option>brown</option><option>gray</option></select>
<input id="labels" placeholder="Labels, comma separated">
<button type="submit">Add note</button></form>
<div class="grid" id="grid"></div>
<div id="modal"><div>
<input id="etitle"><textarea id="econtent" rows="6"></textarea>
<select id="ecolor"><option>default</option><option>red</option><option>orange</option>
<option>yellow</option><option>green</option><option>teal</option><option>blue</option>
<option>purple</option><option>pink</option><option>brown</option><option>gray</option></select>
<label><input type="checkbox" id="epinned"> Pinned</label>
<label><input type="checkbox" id="earchived"> Archived</label><br>
<button onclick="saveEdit()">Save</button>
<button onclick="closeEdit()">Close without saving</button></div></div>
<script>
let token = null, editing = null;
async function api(path, opts={}) {
  opts.headers = Object.assign({}, opts.headers || {});
  if (token) opts.headers.Authorization = 'Bearer ' + token;
  const r = await fetch(path, opts);
  if (r.status === 401) {
    token = prompt('This server needs a token (KEEP_TOKEN):');
    if (!token) throw new Error('token required (401)');
    return api(path, opts);
  }
  if (!r.ok) { const d = await r.json().catch(()=>({})); throw new Error(d.error || ('HTTP ' + r.status)); }
  if (r.status === 204) return null;
  return r.json();
}
function showErr(e){ const el=document.getElementById('error'); el.style.display='block'; el.textContent='Backend error: '+e.message+' — your draft was kept.'; }
function hideErr(){ document.getElementById('error').style.display='none'; }
async function load(){
  try { hideErr();
    const q = document.getElementById('q').value;
    const arch = document.getElementById('arch').checked;
    const url = '/api/notes?' + (q ? 'q='+encodeURIComponent(q)+'&' : '') + (arch ? 'archived=true' : '');
    const notes = await api(url);
    const grid = document.getElementById('grid'); grid.innerHTML='';
    notes.forEach(n => {
      const d = document.createElement('div'); d.className='card'; d.dataset.color=n.color;
      d.innerHTML = '<b></b><div></div><small></small><br>';
      d.querySelector('b').textContent = (n.pinned?'📌 ':'') + n.title;
      d.querySelector('div').textContent = n.content;
      d.querySelector('small').textContent = (n.labels||[]).join(', ');
      d.onclick = () => openEdit(n);
      const del = document.createElement('button'); del.textContent='Delete';
      del.onclick = async (e) => { e.stopPropagation(); try { await api('/api/notes/'+n.id,{method:'DELETE'}); load(); } catch(err){ showErr(err); } };
      d.appendChild(del); grid.appendChild(d);
    });
  } catch(e){ showErr(e); }
}
async function addNote(ev){
  ev.preventDefault();
  try { hideErr();
    await api('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title: document.getElementById('title').value,
        content: document.getElementById('content').value,
        color: document.getElementById('color').value,
        labels: document.getElementById('labels').value.split(',').map(s=>s.trim()).filter(Boolean)})});
    document.getElementById('title').value=''; document.getElementById('content').value='';
    document.getElementById('labels').value=''; load();
  } catch(e){ showErr(e); }
}
function openEdit(n){ editing=n;
  document.getElementById('etitle').value=n.title; document.getElementById('econtent').value=n.content;
  document.getElementById('ecolor').value=n.color; document.getElementById('epinned').checked=n.pinned;
  document.getElementById('earchived').checked=n.archived; document.getElementById('modal').style.display='block'; }
function closeEdit(){ editing=null; document.getElementById('modal').style.display='none'; }
async function saveEdit(){
  try { hideErr();
    await api('/api/notes/'+editing.id,{method:'PUT',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title: document.getElementById('etitle').value,
        content: document.getElementById('econtent').value,
        color: document.getElementById('ecolor').value,
        pinned: document.getElementById('epinned').checked,
        archived: document.getElementById('earchived').checked})});
    closeEdit(); load();
  } catch(e){ showErr(e); }
}
load();
</script></body></html>
"""


def serve(store, host, port):
    token = os.environ.get("KEEP_TOKEN") or None
    handler = make_handler(store, token, threading.Lock())
    server = ThreadingHTTPServer((host, port), handler)
    actual_port = server.server_address[1]
    print("Keep (local) at http://%s:%d/  (data: %s)"
          % (host, actual_port, store.path))
    if token:
        print("API requires a bearer token (KEEP_TOKEN is set).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# ---------------------------------------------------------------- CLI

def _print_note(note, as_json):
    if as_json:
        print(json.dumps(note, indent=2))
    else:
        pin = "📌 " if note["pinned"] else ""
        arch = " [archived]" if note["archived"] else ""
        print("%s%s%s%s" % (pin, note["id"], arch, ""))
        if note["title"]:
            print("  " + note["title"])
        if note["content"]:
            print("  " + note["content"])
        tags = ", ".join(note["labels"])
        print("  color=%s%s  updated=%s"
              % (note["color"], (" labels=" + tags) if tags else "",
                 note["updated_at"]))


def _fail(message):
    print("error: " + message, file=sys.stderr)
    return 1


def build_parser():
    parser = argparse.ArgumentParser(prog="keep.py",
                                    description="Local note-taking app (Keep-shaped, no cloud).")
    parser.add_argument("--data", default=os.environ.get("KEEP_DATA"),
                        help="notes JSON file (default: notes.json in cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="serve the REST API + web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    p = sub.add_parser("add", help="create a note")
    p.add_argument("--title", default="")
    p.add_argument("--content", default="")
    p.add_argument("--color", default="default")
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--pinned", action="store_true")

    for name in ("list", "search"):
        p = sub.add_parser(name, help=name + " notes")
        if name == "search":
            p.add_argument("query")
        else:
            p.add_argument("--search", "-q", default=None)
        p.add_argument("--label", default=None)
        p.add_argument("--pinned", action="store_true")
        p.add_argument("--archived", action="store_true")
        p.add_argument("--all", action="store_true",
                       help="include archived notes")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("get", help="show one note")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("edit", help="edit a note (only given fields change)")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--content")
    p.add_argument("--color")
    p.add_argument("--labels", help="comma-separated, replaces labels")
    p.add_argument("--pinned", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--archived", action=argparse.BooleanOptionalAction, default=None)

    p = sub.add_parser("delete", help="delete a note permanently")
    p.add_argument("id")

    for name in ("pin", "unpin", "archive", "unarchive"):
        p = sub.add_parser(name, help=name + " a note")
        p.add_argument("id")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    data_path = args.data or "notes.json"
    try:
        store = NoteStore(data_path)
    except ValueError as exc:
        return _fail(str(exc))

    if args.command == "serve":
        return serve(store, args.host, args.port)

    try:
        if args.command == "add":
            note = store.create({
                "title": args.title, "content": args.content,
                "color": args.color, "labels": args.label,
                "pinned": args.pinned,
            })
            _print_note(note, False)
        elif args.command in ("list", "search"):
            query = args.query if args.command == "search" else args.search
            notes = store.list_notes(
                q=query, label=args.label,
                pinned=True if args.pinned else None,
                archived=True if args.archived else None,
                include_archived=args.all)
            if args.json:
                print(json.dumps(notes, indent=2))
            elif not notes:
                print("(no notes)")
            else:
                for note in notes:
                    _print_note(note, False)
        elif args.command == "get":
            _print_note(store.get(args.id), args.json)
        elif args.command == "edit":
            fields = {}
            if args.title is not None:
                fields["title"] = args.title
            if args.content is not None:
                fields["content"] = args.content
            if args.color is not None:
                fields["color"] = args.color
            if args.labels is not None:
                fields["labels"] = [s.strip() for s in args.labels.split(",")]
            if args.pinned is not None:
                fields["pinned"] = args.pinned
            if args.archived is not None:
                fields["archived"] = args.archived
            if not fields:
                return _fail("edit needs at least one field to change")
            _print_note(store.update(args.id, fields), False)
        elif args.command == "delete":
            store.delete(args.id)
            print("deleted " + args.id)
        elif args.command in ("pin", "unpin", "archive", "unarchive"):
            field = "pinned" if args.command in ("pin", "unpin") else "archived"
            value = args.command in ("pin", "archive")
            _print_note(store.update(args.id, {field: value}), False)
    except (ValueError, KeyError) as exc:
        return _fail(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())

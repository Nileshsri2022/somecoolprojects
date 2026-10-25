#!/usr/bin/env python3
"""ccbox — a local-only Dropbox-like file storage and sync tool.

Single-file implementation (Python 3 standard library only):

  * HTTP server holding one virtual drive per user on local disk
    (signup/login, folders, upload/download, share links).
  * CLI client for the same API.
  * Sync engine: one pass comparing a local folder with the remote
    drive by SHA-256 + mtime, uploading newer local files and
    downloading newer remote files.

Run ``python3 ccbox.py --help`` for commands. Plain HTTP only:
run on localhost or a trusted network. See docs/SPEC.md for the
challenge steps, deliberate divergences, and scope limits.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

PBKDF2_ITERATIONS = 100_000


class CcboxError(Exception):
    """User-facing error, optionally carrying an HTTP status."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- paths

def normalize_path(path, allow_empty=False):
    """Validate a remote drive path; return its normalised form.

    Rejects absolute paths, empty paths (unless allow_empty, used
    for listing the drive root) and any ``..`` component.
    """
    if path is None:
        raise CcboxError("path is required", 400)
    path = str(path).strip()
    if path.startswith("/"):
        raise CcboxError(f"invalid path: {path!r}", 400)
    path = path.rstrip("/")
    if not path:
        if allow_empty:
            return ""
        raise CcboxError("path must not be empty", 400)
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise CcboxError(f"invalid path: {path!r}", 400)
    return "/".join(parts)


def drive_root(data_dir, username):
    return Path(data_dir) / "drive" / username


def meta_root(data_dir, username):
    return Path(data_dir) / "meta" / username


def drive_path(data_dir, username, rel):
    """Resolve a normalised remote path inside the user's drive.

    The resolve + containment check is defence in depth on top of
    normalize_path: a resolved path outside the drive is refused.
    """
    root = drive_root(data_dir, username).resolve()
    target = (root / rel).resolve() if rel else root
    if target != root and root not in target.parents:
        raise CcboxError(f"invalid path: {rel!r}", 400)
    return target


def meta_path(data_dir, username, rel):
    return meta_root(data_dir, username) / (rel + ".json")


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- server state

class Store:
    """JSON-backed user/token/share state, guarded by one lock."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _p(self, name):
        return self.data_dir / name

    def users(self):
        return load_json(self._p("users.json"), {})

    def tokens(self):
        return load_json(self._p("tokens.json"), {})

    def shares(self):
        return load_json(self._p("shares.json"), {})

    def set_users(self, v):
        save_json(self._p("users.json"), v)

    def set_tokens(self, v):
        save_json(self._p("tokens.json"), v)

    def set_shares(self, v):
        save_json(self._p("shares.json"), v)


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    ).hex()


def file_meta(data_dir, username, rel, size):
    meta = load_json(meta_path(data_dir, username, rel), {})
    return {
        "path": rel,
        "type": "file",
        "size": size,
        "sha256": meta.get("sha256"),
        "mtime": meta.get("mtime"),
    }


def list_entries(data_dir, username, rel):
    """One-level listing of a folder (rel == "" is the drive root)."""
    target = drive_path(data_dir, username, rel)
    if not target.is_dir():
        raise CcboxError(f"folder not found: {rel or '/'}", 404)
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: p.name):
        child_rel = f"{rel}/{child.name}" if rel else child.name
        if child.is_dir():
            entries.append({"path": child_rel, "type": "folder"})
        else:
            entries.append(
                file_meta(data_dir, username, child_rel, child.stat().st_size)
            )
    return entries


def tree_entries(data_dir, username):
    """Recursive listing of every file in the user's drive."""
    root = drive_root(data_dir, username)
    entries = []
    if not root.exists():
        return entries
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        entries.append(
            file_meta(data_dir, username, rel, path.stat().st_size)
        )
    return entries


# ---------------------------------------------------------------- HTTP server

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    store = None  # set by make_server

    # -- plumbing ----------------------------------------------------
    def log_message(self, *args):  # keep test/server output quiet
        pass

    def _send(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise CcboxError("request body is not valid JSON", 400)

    def _auth(self):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Bearer "):
            raise CcboxError("missing or invalid Authorization header", 401)
        token = header[len("Bearer "):].strip()
        with self.store.lock:
            username = self.store.tokens().get(token)
        if not username:
            raise CcboxError("invalid or expired token", 401)
        return username

    def _route(self, method, parsed):
        path = parsed.path
        query = urlparse.parse_qs(parsed.query)
        if method == "POST" and path == "/api/signup":
            return self._signup(self._body())
        if method == "POST" and path == "/api/login":
            return self._login(self._body())
        if method == "POST" and path == "/api/mkdir":
            user = self._auth()
            return 200, self._mkdir(user, self._body())
        if method == "GET" and path == "/api/list":
            user = self._auth()
            rel = normalize_path(
                query.get("path", [""])[0], allow_empty=True
            )
            return 200, {"path": rel, "entries": list_entries(
                self.store.data_dir, user, rel)}
        if method == "GET" and path == "/api/tree":
            user = self._auth()
            return 200, {"entries": tree_entries(
                self.store.data_dir, user)}
        if method == "POST" and path == "/api/upload":
            user = self._auth()
            return 200, self._upload(user, self._body())
        if method == "GET" and path == "/api/download":
            user = self._auth()
            rel = normalize_path(query.get("path", [""])[0])
            return 200, self._download(user, rel)
        if method == "POST" and path == "/api/delete":
            user = self._auth()
            return 200, self._delete(user, self._body())
        if method == "POST" and path == "/api/share":
            user = self._auth()
            return 200, self._share(user, self._body())
        if method == "GET" and path.startswith("/share/"):
            token = path[len("/share/"):]
            return 200, self._fetch_share(token)
        raise CcboxError("unknown route", 404)

    def _dispatch(self, method):
        try:
            status, obj = self._route(method, urlparse.urlparse(self.path))
            self._send(status, obj)
        except CcboxError as exc:
            self._send(exc.status or 400, {"error": str(exc)})
        except BrokenPipeError:
            pass
        except Exception as exc:  # never leak a stack trace as a hang
            self._send(500, {"error": f"internal error: {exc}"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    # -- handlers ----------------------------------------------------
    def _signup(self, body):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or not password:
            raise CcboxError("username and password are required", 400)
        if "/" in username or username in (".", ".."):
            raise CcboxError("invalid username", 400)
        with self.store.lock:
            users = self.store.users()
            if username in users:
                raise CcboxError("username already exists", 409)
            salt = secrets.token_bytes(16)
            users[username] = {
                "salt": salt.hex(),
                "hash": hash_password(password, salt),
            }
            self.store.set_users(users)
        drive_root(self.store.data_dir, username).mkdir(
            parents=True, exist_ok=True)
        return 201, {"username": username}

    def _login(self, body):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        with self.store.lock:
            users = self.store.users()
            record = users.get(username)
            if not record:
                raise CcboxError("invalid username or password", 401)
            salt = bytes.fromhex(record["salt"])
            if hash_password(password, salt) != record["hash"]:
                raise CcboxError("invalid username or password", 401)
            token = secrets.token_urlsafe(32)
            tokens = self.store.tokens()
            tokens[token] = username
            self.store.set_tokens(tokens)
        return 200, {"username": username, "token": token}

    def _mkdir(self, user, body):
        rel = normalize_path(body.get("path"))
        drive_path(self.store.data_dir, user, rel).mkdir(
            parents=True, exist_ok=True)
        return {"path": rel}

    def _upload(self, user, body):
        rel = normalize_path(body.get("path"))
        if "content_b64" not in body:
            raise CcboxError("content_b64 is required", 400)
        try:
            data = base64.b64decode(body["content_b64"], validate=True)
        except Exception:
            raise CcboxError("content_b64 is not valid base64", 400)
        target = drive_path(self.store.data_dir, user, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        mtime = body.get("mtime")
        if mtime is None:
            mtime = time.time()
        save_json(meta_path(self.store.data_dir, user, rel), {
            "sha256": sha256_of(data), "mtime": float(mtime),
        })
        return {"path": rel, "size": len(data),
                "sha256": sha256_of(data), "mtime": float(mtime)}

    def _download(self, user, rel):
        target = drive_path(self.store.data_dir, user, rel)
        if not target.is_file():
            raise CcboxError(f"file not found: {rel}", 404)
        data = target.read_bytes()
        meta = load_json(meta_path(self.store.data_dir, user, rel), {})
        return {
            "path": rel,
            "content_b64": base64.b64encode(data).decode("ascii"),
            "size": len(data),
            "sha256": meta.get("sha256", sha256_of(data)),
            "mtime": meta.get("mtime"),
        }

    def _delete(self, user, body):
        rel = normalize_path(body.get("path"))
        target = drive_path(self.store.data_dir, user, rel)
        if target.is_file():
            target.unlink()
            mp = meta_path(self.store.data_dir, user, rel)
            if mp.exists():
                mp.unlink()
        elif target.is_dir():
            import shutil
            shutil.rmtree(target)
            mdir = meta_root(self.store.data_dir, user) / rel
            if mdir.exists():
                shutil.rmtree(mdir)
        else:
            raise CcboxError(f"path not found: {rel}", 404)
        return {"path": rel, "deleted": True}

    def _share(self, user, body):
        rel = normalize_path(body.get("path"), allow_empty=True)
        target = drive_path(self.store.data_dir, user, rel)
        if not target.exists():
            raise CcboxError(f"path not found: {rel or '/'}", 404)
        public = bool(body.get("public", False))
        token = secrets.token_urlsafe(24)
        with self.store.lock:
            shares = self.store.shares()
            shares[token] = {"owner": user, "path": rel, "public": public}
            self.store.set_shares(shares)
        return {"token": token, "url": f"/share/{token}",
                "path": rel, "public": public}

    def _fetch_share(self, token):
        with self.store.lock:
            share = self.store.shares().get(token)
        if not share:
            raise CcboxError("share link not found", 404)
        if not share["public"]:
            # Private link: only the owner's token may fetch it.
            try:
                user = self._auth()
            except CcboxError:
                raise CcboxError("this link is private", 401)
            if user != share["owner"]:
                raise CcboxError("this link is private", 403)
        owner, rel = share["owner"], share["path"]
        target = drive_path(self.store.data_dir, owner, rel)
        if target.is_file():
            return self._download(owner, rel)
        if target.is_dir():
            return {"path": rel, "type": "folder",
                    "entries": list_entries(
                        self.store.data_dir, owner, rel)}
        raise CcboxError("shared path no longer exists", 404)


def make_server(data_dir, port=0):
    """Build (do not yet run) a ccbox server on the given port."""
    handler = type("BoundHandler", (Handler,), {"store": Store(data_dir)})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    return server


# ---------------------------------------------------------------- client

def _request(server, method, route, token=None, body=None):
    url = server.rstrip("/") + route
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urlrequest.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            detail = ""
        raise CcboxError(detail or f"HTTP {exc.code}", exc.code)
    except urlerror.URLError as exc:
        raise CcboxError(f"cannot reach server: {exc.reason}")


def signup(server, username, password):
    return _request(server, "POST", "/api/signup",
                    body={"username": username, "password": password})


def login(server, username, password):
    return _request(server, "POST", "/api/login",
                    body={"username": username, "password": password})


def mkdir(server, token, path):
    return _request(server, "POST", "/api/mkdir", token, {"path": path})


def list_dir(server, token, path=""):
    route = "/api/list?path=" + urlparse.quote(path)
    return _request(server, "GET", route, token)


def tree(server, token):
    return _request(server, "GET", "/api/tree", token)


def upload_file(server, token, local_path, remote_path, mtime=None):
    data = Path(local_path).read_bytes()
    if mtime is None:
        mtime = Path(local_path).stat().st_mtime
    return _request(server, "POST", "/api/upload", token, {
        "path": remote_path,
        "content_b64": base64.b64encode(data).decode("ascii"),
        "mtime": float(mtime),
    })


def upload_dir(server, token, local_dir, remote_dir=""):
    """Upload a local directory recursively, preserving relative paths."""
    uploaded = []
    base = Path(local_dir)
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = path.relative_to(base).as_posix()
            remote = f"{remote_dir}/{rel}" if remote_dir else rel
            upload_file(server, token, path, remote)
            uploaded.append(remote)
    return uploaded


def download_file(server, token, remote_path, local_path):
    result = _request(
        server, "GET",
        "/api/download?path=" + urlparse.quote(remote_path), token)
    data = base64.b64decode(result["content_b64"])
    target = Path(local_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if result.get("mtime"):
        os.utime(target, (result["mtime"], result["mtime"]))
    return result


def delete(server, token, path):
    return _request(server, "POST", "/api/delete", token, {"path": path})


def create_share(server, token, path, public=False):
    return _request(server, "POST", "/api/share", token,
                    {"path": path, "public": public})


def fetch_share(server, token, share_token):
    return _request(server, "GET", f"/share/{share_token}", token)


# ---------------------------------------------------------------- sync

def sync_once(server, token, local_dir):
    """One sync pass. Returns {uploaded, downloaded, unchanged}.

    Local file wins ties (equal mtimes, differing hashes); a newer
    remote file wins otherwise. Deletions are never propagated.
    """
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    local = {}
    for path in sorted(local_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(local_dir).as_posix()
            data = path.read_bytes()
            local[rel] = (sha256_of(data), path.stat().st_mtime)
    remote = {}
    for entry in tree(server, token)["entries"]:
        if entry["type"] == "file":
            remote[entry["path"]] = (entry.get("sha256"),
                                     entry.get("mtime") or 0)
    uploaded, downloaded, unchanged = [], [], []
    for rel, (digest, mtime) in local.items():
        if rel not in remote:
            upload_file(server, token, local_dir / rel, rel, mtime)
            uploaded.append(rel)
        elif remote[rel][0] == digest:
            unchanged.append(rel)
        elif mtime >= (remote[rel][1] or 0):
            upload_file(server, token, local_dir / rel, rel, mtime)
            uploaded.append(rel)
        else:
            download_file(server, token, rel, local_dir / rel)
            downloaded.append(rel)
    for rel in remote:
        if rel not in local:
            download_file(server, token, rel, local_dir / rel)
            downloaded.append(rel)
    return {"uploaded": sorted(uploaded),
            "downloaded": sorted(downloaded),
            "unchanged": sorted(unchanged)}


# ---------------------------------------------------------------- CLI

def _server_arg(args):
    return getattr(args, "server", None) or os.environ.get(
        "CCBOX_SERVER_URL", "http://127.0.0.1:8765")


def _token_arg(args):
    return getattr(args, "token", None) or os.environ.get("CCBOX_TOKEN")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ccbox", description="Local Dropbox-like file sync tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("server", help="run the ccbox server")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--data-dir", default="./ccbox-data")

    for name, help_text in (
        ("signup", "create a local account"),
        ("login", "log in and print a bearer token"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--server", default=None)
        p.add_argument("--username", required=True)
        p.add_argument("--password", required=True)

    def _authed(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--server", default=None)
        p.add_argument("--token", default=None)
        return p

    p = _authed("mkdir", "create a folder (parents as needed)")
    p.add_argument("--path", required=True)
    p = _authed("list", "list one folder")
    p.add_argument("--path", default="")
    _authed("tree", "list the whole drive recursively")
    p = _authed("upload", "upload a file or a whole directory")
    p.add_argument("--local", required=True)
    p.add_argument("--remote", default="")
    p = _authed("download", "download a file")
    p.add_argument("--remote", required=True)
    p.add_argument("--local", required=True)
    p = _authed("delete", "delete a file or folder")
    p.add_argument("--path", required=True)
    p = _authed("share", "create a share link")
    p.add_argument("--path", required=True)
    p.add_argument("--public", action="store_true")
    p = _authed("sync", "sync a local folder with the remote drive")
    p.add_argument("--local-dir", required=True)
    p.add_argument("--interval", type=float, default=0,
                   help="seconds between passes; 0 = run once")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    server_url = _server_arg(args)
    try:
        if args.command == "server":
            server = make_server(args.data_dir, args.port)
            print(f"ccbox server on 127.0.0.1:{server.server_address[1]} "
                  f"(data: {args.data_dir})")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("stopped")
            return 0
        if args.command == "signup":
            print(json.dumps(signup(server_url, args.username,
                                    args.password), indent=2))
        elif args.command == "login":
            print(json.dumps(login(server_url, args.username,
                                   args.password), indent=2))
        else:
            token = _token_arg(args)
            if not token:
                raise CcboxError(
                    "a token is required: pass --token or set CCBOX_TOKEN")
            if args.command == "mkdir":
                print(json.dumps(mkdir(server_url, token, args.path)))
            elif args.command == "list":
                print(json.dumps(list_dir(server_url, token, args.path),
                                 indent=2))
            elif args.command == "tree":
                print(json.dumps(tree(server_url, token), indent=2))
            elif args.command == "upload":
                local = Path(args.local)
                if local.is_dir():
                    print(json.dumps({"uploaded": upload_dir(
                        server_url, token, local, args.remote)}))
                else:
                    remote = args.remote or local.name
                    print(json.dumps(upload_file(
                        server_url, token, local, remote)))
            elif args.command == "download":
                print(json.dumps(download_file(
                    server_url, token, args.remote, args.local)))
            elif args.command == "delete":
                print(json.dumps(delete(server_url, token, args.path)))
            elif args.command == "share":
                result = create_share(server_url, token, args.path,
                                      args.public)
                result["full_url"] = server_url + result["url"]
                print(json.dumps(result, indent=2))
            elif args.command == "sync":
                while True:
                    result = sync_once(server_url, token, args.local_dir)
                    print(json.dumps(result, indent=2))
                    if not args.interval:
                        break
                    time.sleep(args.interval)
        return 0
    except CcboxError as exc:
        print(f"ccbox: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

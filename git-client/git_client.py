"""ccgit: a minimal git client (Coding Challenges, challenge-git).

Implements the challenge steps 1-5 with Python's standard library
only: init, add (hash-object + index v2), status, commit (blob /
tree / commit objects, SHA-1, zlib), diff, plus cat-file,
hash-object, log and checkout. Step 6 (push to GitHub) is NOT
implemented -- see docs/DESIGN.md -- and `push` says so plainly.

Core logic never shells out to system git; git is used only as a
test oracle in tests/.

Usage: python3 git_client.py <command> [args...]
  init [dir]  add <path>...  status  commit [-m] <message>
  log  hash-object [-w] <file>  cat-file -p|-t|-s <sha>
  diff [--cached]  checkout [--] <path> | checkout <commit-ish>
  push (not implemented)
"""

import difflib
import hashlib
import os
import struct
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone

DEFAULT_BRANCH = "master"
DESCRIPTION = "Unnamed repository; edit this file 'description' to name the repository.\n"
EXCLUDE = "# git ls-files --others --exclude-from=.git/info/exclude\n"


class GitError(Exception):
    """Any user-facing failure: message goes to stderr, exit 1."""


# ---------------------------------------------------------------- repo

def find_repo(start=None):
    """Return (worktree, gitdir) walking up from start (default cwd)."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        gitdir = os.path.join(cur, ".git")
        if os.path.isdir(gitdir):
            return cur, gitdir
        parent = os.path.dirname(cur)
        if parent == cur:
            raise GitError("not a git repository (or any parent up to mount point)")
        cur = parent


def read_head(gitdir):
    """Return ('ref', 'refs/heads/master') or ('detached', sha)."""
    with open(os.path.join(gitdir, "HEAD"), "rb") as f:
        text = f.read().decode("utf-8", "replace").strip()
    if text.startswith("ref:"):
        return "ref", text[4:].strip()
    return "detached", text


def branch_name(gitdir):
    kind, value = read_head(gitdir)
    if kind == "ref" and value.startswith("refs/heads/"):
        return value[len("refs/heads/"):]
    return "HEAD"  # detached


def resolve_ref(gitdir, ref):
    """SHA a ref file holds, or None."""
    path = os.path.join(gitdir, ref)
    if os.path.isfile(path):
        with open(path) as f:
            return f.read().strip() or None
    return None


def head_commit(gitdir):
    kind, value = read_head(gitdir)
    if kind == "ref":
        return resolve_ref(gitdir, value)
    return value or None


def write_ref(gitdir, ref, sha):
    path = os.path.join(gitdir, ref)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(sha + "\n")


def update_head(gitdir, sha):
    kind, value = read_head(gitdir)
    if kind == "ref":
        write_ref(gitdir, value, sha)
    else:
        with open(os.path.join(gitdir, "HEAD"), "w") as f:
            f.write(sha + "\n")


def read_config_user(gitdir):
    """Best-effort [user] name/email from .git/config, else {}."""
    user = {}
    try:
        with open(os.path.join(gitdir, "config")) as f:
            lines = f.read().splitlines()
    except OSError:
        return user
    in_user = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_user = stripped == "[user]"
            continue
        if in_user and "=" in stripped:
            key, val = stripped.split("=", 1)
            user[key.strip()] = val.strip()
    return user


def identity(gitdir, role):
    """(name, email, timestamp, tz) for author/committer."""
    env_name = os.environ.get("GIT_%s_NAME" % role)
    env_email = os.environ.get("GIT_%s_EMAIL" % role)
    cfg = read_config_user(gitdir)
    name = env_name or cfg.get("name") or "ccgit"
    email = env_email or cfg.get("email") or "ccgit@example.com"
    date = os.environ.get("GIT_%s_DATE" % role)
    try:
        ts = int(date) if date is not None else int(time.time())
    except ValueError:
        ts = int(time.time())
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    sign = "+" if offset >= timedelta(0) else "-"
    total = abs(int(offset.total_seconds()))
    tz = "%s%02d%02d" % (sign, total // 3600, (total % 3600) // 60)
    return name, email, ts, tz


def format_ident(name, email, ts, tz):
    return "%s <%s> %d %s" % (name, email, ts, tz)


def format_date(ts, tz):
    sign = 1 if tz[0] == "+" else -1
    delta = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
    dt = datetime.fromtimestamp(ts, tz=timezone(delta))
    return dt.strftime("%a %b %e %H:%M:%S %Y %z")


# ---------------------------------------------------------------- objects

def object_path(gitdir, sha):
    return os.path.join(gitdir, "objects", sha[:2], sha[2:])


def hash_object_data(obj_type, data):
    header = ("%s %d" % (obj_type, len(data))).encode() + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def write_object(gitdir, obj_type, data):
    sha = hash_object_data(obj_type, data)
    path = object_path(gitdir, sha)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        header = ("%s %d" % (obj_type, len(data))).encode() + b"\0"
        with open(path, "wb") as f:
            f.write(zlib.compress(header + data))
    return sha


def read_object(gitdir, sha):
    """Return (type, data); sha may be a unique prefix (len >= 4)."""
    if len(sha) < 40:
        sha = resolve_short_sha(gitdir, sha)
    path = object_path(gitdir, sha)
    if not os.path.isfile(path):
        raise GitError("object not found: %s" % sha)
    try:
        with open(path, "rb") as f:
            raw = zlib.decompress(f.read())
    except zlib.error:
        raise GitError("corrupt object: %s" % sha)
    header, _, data = raw.partition(b"\0")
    try:
        obj_type, size = header.decode().split(" ")
        size = int(size)
    except ValueError:
        raise GitError("corrupt object header: %s" % sha)
    if size != len(data):
        raise GitError("corrupt object size: %s" % sha)
    return obj_type, data


def resolve_short_sha(gitdir, prefix):
    if len(prefix) < 4 or not all(c in "0123456789abcdef" for c in prefix):
        raise GitError("not a valid object name: %s" % prefix)
    d = os.path.join(gitdir, "objects", prefix[:2])
    matches = []
    if os.path.isdir(d):
        for name in os.listdir(d):
            if name.startswith(prefix[2:]):
                matches.append(prefix[:2] + name)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise GitError("object not found: %s" % prefix)
    raise GitError("short object ID %s is ambiguous" % prefix)


def resolve_commitish(gitdir, arg):
    """Branch name, HEAD, full/short SHA -> commit SHA (or raise)."""
    if arg == "HEAD":
        sha = head_commit(gitdir)
        if not sha:
            raise GitError("HEAD has no commit yet")
        return sha
    for ref in ("refs/heads/" + arg, "refs/tags/" + arg):
        sha = resolve_ref(gitdir, ref)
        if sha:
            return sha
    if all(c in "0123456789abcdef" for c in arg) and len(arg) >= 4:
        sha = arg if len(arg) == 40 else resolve_short_sha(gitdir, arg)
        obj_type, _ = read_object(gitdir, sha)
        if obj_type != "commit":
            raise GitError("%s is a %s, not a commit" % (arg, obj_type))
        return sha
    raise GitError("unknown revision: %s" % arg)


# ---------------------------------------------------------------- trees

def parse_tree(data):
    """[(mode_str, name, sha_hex)] from raw tree bytes."""
    entries, i = [], 0
    while i < len(data):
        sp = data.index(b" ", i)
        mode = data[i:sp].decode()
        nul = data.index(b"\0", sp)
        name = data[sp + 1:nul].decode()
        sha = data[nul + 1:nul + 21].hex()
        entries.append((mode, name, sha))
        i = nul + 21
    return entries


def build_tree(gitdir, entries):
    """entries: [(path, mode, sha)] -> tree SHA, writing trees."""
    # Group by first path component.
    children = {}  # name -> ('blob', mode, sha) or ('tree', [entries])
    for path, mode, sha in entries:
        head, _, rest = path.partition("/")
        if not rest:
            children[head] = ("blob", mode, sha)
        else:
            node = children.setdefault(head, ("tree", []))
            node[1].append((rest, mode, sha))
    tree_entries = []
    for name, node in children.items():
        if node[0] == "blob":
            tree_entries.append((node[1], name, node[2]))
        else:
            sub = build_tree(gitdir, node[1])
            tree_entries.append(("40000", name, sub))
    # Git sort: directories sort as if named with a trailing '/'.
    tree_entries.sort(key=lambda e: (e[1] + "/").encode()
                      if e[0] == "40000" else e[1].encode())
    data = b""
    for mode, name, sha in tree_entries:
        data += mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(sha)
    return write_object(gitdir, "tree", data)


def flatten_tree(gitdir, tree_sha, prefix=""):
    """tree SHA -> {path: (mode, blob_sha)}, recursively."""
    if tree_sha is None:
        return {}
    obj_type, data = read_object(gitdir, tree_sha)
    if obj_type != "tree":
        raise GitError("not a tree: %s" % tree_sha)
    out = {}
    for mode, name, sha in parse_tree(data):
        path = prefix + name
        if mode == "40000":
            out.update(flatten_tree(gitdir, sha, path + "/"))
        else:
            out[path] = (mode, sha)
    return out


def parse_commit(data):
    """(headers dict with list values, message str) from raw commit."""
    header_text, _, message = data.decode("utf-8", "replace").partition("\n\n")
    headers = {}
    for line in header_text.splitlines():
        key, _, val = line.partition(" ")
        headers.setdefault(key, []).append(val)
    return headers, message


def head_tree_map(gitdir):
    sha = head_commit(gitdir)
    if not sha:
        return {}
    obj_type, data = read_object(gitdir, sha)
    if obj_type != "commit":
        raise GitError("HEAD is not a commit: %s" % sha)
    headers, _ = parse_commit(data)
    return flatten_tree(gitdir, headers["tree"][0])


# ---------------------------------------------------------------- index v2

class IndexEntry:
    __slots__ = ("name", "mode", "sha", "ctime_s", "ctime_n", "mtime_s",
                 "mtime_n", "dev", "ino", "uid", "gid", "size")

    def __init__(self, name, mode, sha, st=None):
        self.name = name
        self.mode = mode
        self.sha = sha
        if st is not None:
            self.ctime_s, self.ctime_n = divmod(st.st_ctime_ns, 10 ** 9)
            self.mtime_s, self.mtime_n = divmod(st.st_mtime_ns, 10 ** 9)
            self.dev, self.ino = st.st_dev, st.st_ino
            self.uid, self.gid = st.st_uid, st.st_gid
            self.size = st.st_size
        else:
            self.ctime_s = self.ctime_n = self.mtime_s = self.mtime_n = 0
            self.dev = self.ino = self.uid = self.gid = self.size = 0


def read_index(gitdir):
    """{path: IndexEntry}; missing index -> {}."""
    path = os.path.join(gitdir, "index")
    if not os.path.isfile(path):
        return {}
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 12 + 20 or raw[:4] != b"DIRC":
        raise GitError("invalid index file")
    version, count = struct.unpack(">II", raw[4:12])
    if version not in (2, 3):
        raise GitError("unsupported index version: %d" % version)
    if hashlib.sha1(raw[:-20]).digest() != raw[-20:]:
        raise GitError("index checksum mismatch")
    entries, i = {}, 12
    for _ in range(count):
        vals = struct.unpack(">10I", raw[i:i + 40])
        (ctime_s, ctime_n, mtime_s, mtime_n, dev, ino, mode, uid, gid,
         size) = vals
        sha = raw[i + 40:i + 60].hex()
        flags = struct.unpack(">H", raw[i + 60:i + 62])[0]
        name_len = flags & 0xFFF
        j = i + 62
        if version == 3 and flags & 0x4000:
            j += 2  # extended flags word
        if name_len < 0xFFF:
            name = raw[j:j + name_len].decode()
            entry_len = ((62 + name_len + 8) // 8) * 8
            if version == 3 and flags & 0x4000:
                entry_len = ((64 + name_len + 8) // 8) * 8
        else:
            end = raw.index(b"\0", j)
            name = raw[j:end].decode()
            entry_len = ((j - i + (end - j) + 8) // 8) * 8
        e = IndexEntry(name, "%o" % mode, sha)
        (e.ctime_s, e.ctime_n, e.mtime_s, e.mtime_n, e.dev, e.ino,
         e.uid, e.gid, e.size) = (ctime_s, ctime_n, mtime_s, mtime_n,
                                  dev, ino, uid, gid, size)
        entries[name] = e
        i += entry_len
    # Anything left before the trailer is extension blocks; ignored.
    return entries


def write_index(gitdir, entries):
    names = sorted(entries)
    out = struct.pack(">4sII", b"DIRC", 2, len(names))
    for name in names:
        e = entries[name]
        name_b = name.encode()
        flags = min(len(name_b), 0xFFF)
        out += struct.pack(
            ">10I", e.ctime_s, e.ctime_n, e.mtime_s, e.mtime_n,
            e.dev, e.ino, int(e.mode, 8), e.uid, e.gid, e.size)
        out += bytes.fromhex(e.sha)
        out += struct.pack(">H", flags)
        out += name_b
        pad = ((62 + len(name_b) + 8) // 8) * 8 - (62 + len(name_b))
        out += b"\0" * pad
    out += hashlib.sha1(out).digest()
    with open(os.path.join(gitdir, "index"), "wb") as f:
        f.write(out)


# ---------------------------------------------------------------- worktree

def file_mode(path, st):
    import stat as statmod
    if statmod.S_ISLNK(st.st_mode):
        return "120000"
    if st.st_mode & 0o111:
        return "100755"
    return "100644"


def blob_for_path(worktree, rel):
    """(mode, sha_of_content, bytes) for a worktree file, no writing."""
    path = os.path.join(worktree, rel)
    st = os.lstat(path)
    mode = file_mode(path, st)
    if mode == "120000":
        data = os.readlink(path).encode()
    else:
        with open(path, "rb") as f:
            data = f.read()
    return mode, hash_object_data("blob", data), data


def walk_worktree(worktree):
    """Sorted relative posix paths of tracked-able files, excl. .git."""
    out = []
    for root, dirs, files in os.walk(worktree):
        dirs[:] = sorted(d for d in dirs
                         if d != ".git" and not os.path.islink(os.path.join(root, d)))
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, worktree).replace(os.sep, "/")
            out.append(rel)
        # Symlinked files appear in files; symlinked dirs are pruned above.
    return out


def collect_paths(worktree, args):
    """Expand CLI paths (files, directories, '.') to sorted rel paths."""
    found = []
    for arg in args:
        path = os.path.join(worktree, arg)
        if os.path.isdir(path) and not os.path.islink(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs
                                 if not os.path.islink(os.path.join(root, d)))
                for name in sorted(files):
                    rel = os.path.relpath(os.path.join(root, name),
                                          worktree).replace(os.sep, "/")
                    found.append(rel)
        elif os.path.lexists(path):
            found.append(os.path.relpath(path, worktree).replace(os.sep, "/"))
        else:
            raise GitError("pathspec '%s' did not match any files" % arg)
    return sorted(set(found))


# ---------------------------------------------------------------- commands

def cmd_init(args):
    target = os.path.abspath(args[0]) if args else os.getcwd()
    gitdir = os.path.join(target, ".git")
    if os.path.isdir(gitdir):
        raise GitError("repository already exists: %s" % target)
    if not args and os.path.isdir(gitdir):
        raise GitError("repository already exists: %s" % target)
    for sub in ("hooks", "info", "objects/info", "objects/pack",
                "refs/heads", "refs/tags"):
        os.makedirs(os.path.join(gitdir, sub), exist_ok=True)
    with open(os.path.join(gitdir, "HEAD"), "w") as f:
        f.write("ref: refs/heads/%s\n" % DEFAULT_BRANCH)
    with open(os.path.join(gitdir, "config"), "w") as f:
        f.write("[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n"
                "\tbare = false\n\tlogallrefupdates = true\n")
    with open(os.path.join(gitdir, "description"), "w") as f:
        f.write(DESCRIPTION)
    with open(os.path.join(gitdir, "info", "exclude"), "w") as f:
        f.write(EXCLUDE)
    print("initialized empty repository: %s" % (args[0] if args else "."))
    return 0


def cmd_add(args):
    if not args:
        raise GitError("usage: add <path>...")
    worktree, gitdir = find_repo()
    entries = read_index(gitdir)
    for rel in collect_paths(worktree, args):
        path = os.path.join(worktree, rel)
        st = os.lstat(path)
        mode = file_mode(path, st)
        if mode == "120000":
            data = os.readlink(path).encode()
        else:
            with open(path, "rb") as f:
                data = f.read()
        sha = write_object(gitdir, "blob", data)
        entries[rel] = IndexEntry(rel, mode, sha, st)
    write_index(gitdir, entries)
    return 0


def status_maps(worktree, gitdir):
    index = read_index(gitdir)
    head = head_tree_map(gitdir)
    work = {}
    for rel in walk_worktree(worktree):
        try:
            work[rel] = blob_for_path(worktree, rel)
        except OSError:
            continue
    return index, head, work


def cmd_status(args):
    worktree, gitdir = find_repo()
    index, head, work = status_maps(worktree, gitdir)
    staged, unstaged, untracked = [], [], []
    for name in sorted(set(index) | set(head)):
        if name in index and name not in head:
            staged.append(("new file", name))
        elif name in index and name in head and index[name].sha != head[name][1]:
            staged.append(("modified", name))
        elif name not in index and name in head:
            staged.append(("deleted", name))
    for name in sorted(index):
        if name not in work:
            unstaged.append(("deleted", name))
        elif work[name][1] != index[name].sha:
            unstaged.append(("modified", name))
    for name in sorted(work):
        if name not in index:
            untracked.append(name)
    print("On branch %s" % branch_name(gitdir))
    if not staged and not unstaged and not untracked:
        print("nothing to commit, working tree clean")
        return 0
    if staged:
        print("Changes to be committed:")
        for kind, name in staged:
            print("\t%s:   %s" % (kind, name))
    if unstaged:
        print("Changes not staged for commit:")
        for kind, name in unstaged:
            print("\t%s:   %s" % (kind, name))
    if untracked:
        print("Untracked files:")
        for name in untracked:
            print("\t%s" % name)
    return 0


def cmd_commit(args):
    message = None
    rest = list(args)
    if rest and rest[0] == "-m":
        rest = rest[1:]
        if not rest:
            raise GitError("usage: commit [-m] <message>")
    if rest:
        message = " ".join(rest)
    if not message:
        raise GitError("usage: commit [-m] <message>")
    worktree, gitdir = find_repo()
    index = read_index(gitdir)
    if not index:
        raise GitError("nothing to commit (no files staged)")
    tree_sha = build_tree(gitdir, [(e.name, e.mode, e.sha)
                                   for e in index.values()])
    parent = head_commit(gitdir)
    if parent:
        headers, _ = parse_commit(read_object(gitdir, parent)[1])
        if headers["tree"][0] == tree_sha:
            raise GitError("nothing to commit, working tree clean")
    a_name, a_email, a_ts, a_tz = identity(gitdir, "AUTHOR")
    c_name, c_email, c_ts, c_tz = identity(gitdir, "COMMITTER")
    lines = ["tree %s" % tree_sha]
    if parent:
        lines.append("parent %s" % parent)
    lines.append("author %s" % format_ident(a_name, a_email, a_ts, a_tz))
    lines.append("committer %s" % format_ident(c_name, c_email, c_ts, c_tz))
    body = message if message.endswith("\n") else message + "\n"
    commit_sha = write_object(gitdir, "commit",
                              ("\n".join(lines) + "\n\n" + body).encode())
    update_head(gitdir, commit_sha)
    print("committed to %s: %s" % (branch_name(gitdir), commit_sha))
    return 0


def cmd_log(args):
    worktree, gitdir = find_repo()
    sha = head_commit(gitdir)
    if not sha:
        raise GitError("no commits yet")
    while sha:
        obj_type, data = read_object(gitdir, sha)
        if obj_type != "commit":
            raise GitError("%s is not a commit" % sha)
        headers, message = parse_commit(data)
        author = headers.get("author", ["?"])[0]
        # author: "Name <email> ts tz"
        try:
            ident, ts, tz = author.rsplit(" ", 2)
            date = format_date(int(ts), tz)
        except ValueError:
            ident, date = author, "?"
        print("commit %s" % sha)
        print("Author: %s" % ident)
        print("Date:   %s" % date)
        print()
        for line in message.rstrip("\n").splitlines():
            print("    %s" % line)
        print()
        parents = headers.get("parent", [])
        sha = parents[0] if parents else None
    return 0


def cmd_hash_object(args):
    write = False
    rest = []
    for a in args:
        if a == "-w":
            write = True
        else:
            rest.append(a)
    if len(rest) != 1:
        raise GitError("usage: hash-object [-w] <file>")
    worktree, gitdir = find_repo()
    path = rest[0]
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        full = path if os.path.isabs(path) else os.path.join(worktree, path)
        with open(full, "rb") as f:
            data = f.read()
    sha = hash_object_data("blob", data)
    if write:
        write_object(gitdir, "blob", data)
    print(sha)
    return 0


def write_bytes(data):
    """Write bytes to stdout, tolerating a text-only stdout (tests)."""
    stream = sys.stdout
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        buf.write(data)
        buf.flush()
    else:
        stream.write(data.decode("utf-8", "replace"))


def cmd_cat_file(args):
    flag, sha_arg = "-p", None
    for a in args:
        if a in ("-p", "-t", "-s"):
            flag = a
        else:
            sha_arg = a
    if not sha_arg:
        raise GitError("usage: cat-file -p|-t|-s <sha>")
    worktree, gitdir = find_repo()
    obj_type, data = read_object(gitdir, sha_arg)
    if flag == "-t":
        print(obj_type)
    elif flag == "-s":
        print(len(data))
    elif obj_type == "blob":
        write_bytes(data)
    elif obj_type == "tree":
        for mode, name, sha in parse_tree(data):
            disp = "040000" if mode == "40000" else mode
            kind = "tree" if mode == "40000" else "blob"
            print("%s %s %s\t%s" % (disp, kind, sha, name))
    else:  # commit
        write_bytes(data)
    return 0


def diff_text(old, new, path, old_sha, new_sha):
    out = ["diff --git a/%s b/%s" % (path, path),
           "index %s..%s 100644" % (old_sha[:7], new_sha[:7]),
           "--- a/%s" % path, "+++ b/%s" % path]
    old_lines = old.decode("utf-8", "replace").splitlines(keepends=True)
    new_lines = new.decode("utf-8", "replace").splitlines(keepends=True)
    hunks = list(difflib.unified_diff(old_lines, new_lines,
                                      fromfile="a/" + path, tofile="b/" + path))
    # difflib already emits ---/+++ headers; drop its copies. A
    # hunk line with no trailing newline marks a file whose last
    # line lacks one, as in real git.
    for ln in hunks[2:]:
        if ln.endswith("\n"):
            out.append(ln[:-1])
        else:
            out.append(ln)
            out.append("\\ No newline at end of file")
    return "\n".join(out)


def _blob_bytes(gitdir, sha):
    if sha is None:
        return b""
    return read_object(gitdir, sha)[1]


def cmd_diff(args):
    cached = "--cached" in args
    worktree, gitdir = find_repo()
    index, head, work = status_maps(worktree, gitdir)
    printed = False
    if cached:
        pairs = []
        for name in sorted(set(index) | set(head)):
            old = head[name][1] if name in head else None
            new = index[name].sha if name in index else None
            if old != new:
                pairs.append((name, old, new))
        for name, old, new in pairs:
            print(diff_text(_blob_bytes(gitdir, old), _blob_bytes(gitdir, new),
                            name, old or "0" * 40, new or "0" * 40))
            printed = True
    else:
        for name in sorted(index):
            if name not in work:
                old = index[name].sha
                print(diff_text(_blob_bytes(gitdir, old), b"", name,
                                old, "0" * 40))
                printed = True
            elif work[name][1] != index[name].sha:
                old = index[name].sha
                new_data = blob_for_path(worktree, name)[2]
                print(diff_text(_blob_bytes(gitdir, old), new_data, name,
                                old, work[name][1]))
                printed = True
    return 0


def cmd_checkout(args):
    if not args:
        raise GitError("usage: checkout [--] <path> | checkout <commit-ish>")
    worktree, gitdir = find_repo()
    if args[0] == "--":
        if len(args) != 2:
            raise GitError("usage: checkout -- <path>")
        index = read_index(gitdir)
        rel = args[1]
        if rel not in index:
            raise GitError("path '%s' is not in the index" % rel)
        data = read_object(gitdir, index[rel].sha)[1]
        full = os.path.join(worktree, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if index[rel].mode == "120000":
            if os.path.lexists(full):
                os.remove(full)
            os.symlink(data.decode(), full)
        else:
            if os.path.islink(full):
                os.remove(full)
            with open(full, "wb") as f:
                f.write(data)
        return 0
    # Commit checkout.
    arg = args[0]
    is_branch = resolve_ref(gitdir, "refs/heads/" + arg) is not None
    sha = resolve_commitish(gitdir, arg)
    headers, _ = parse_commit(read_object(gitdir, sha)[1])
    new_tree = flatten_tree(gitdir, headers["tree"][0])
    old_index = read_index(gitdir)
    for name in old_index:
        if name not in new_tree:
            full = os.path.join(worktree, name)
            if os.path.lexists(full):
                os.remove(full)
    new_index = {}
    for name, (mode, blob_sha) in new_tree.items():
        full = os.path.join(worktree, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        data = read_object(gitdir, blob_sha)[1]
        if mode == "120000":
            if os.path.lexists(full):
                os.remove(full)
            os.symlink(data.decode(), full)
            st = os.lstat(full)
        else:
            if os.path.islink(full):
                os.remove(full)
            with open(full, "wb") as f:
                f.write(data)
            if mode == "100755":
                os.chmod(full, 0o755)
            st = os.lstat(full)
        new_index[name] = IndexEntry(name, mode, blob_sha, st)
    write_index(gitdir, new_index)
    if is_branch:
        with open(os.path.join(gitdir, "HEAD"), "w") as f:
            f.write("ref: refs/heads/%s\n" % arg)
    else:
        with open(os.path.join(gitdir, "HEAD"), "w") as f:
            f.write(sha + "\n")
    return 0


def cmd_push(args):
    raise GitError(
        "push is not implemented: step 6 of the challenge needs the "
        "git smart-HTTP protocol and a real GitHub account/token, "
        "which this offline build does not attempt (see docs/DESIGN.md)")


COMMANDS = {
    "init": cmd_init, "add": cmd_add, "status": cmd_status,
    "commit": cmd_commit, "log": cmd_log, "hash-object": cmd_hash_object,
    "cat-file": cmd_cat_file, "diff": cmd_diff, "checkout": cmd_checkout,
    "push": cmd_push,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        sys.stderr.write(
            "usage: git_client.py {%s} ...\n" % "|".join(sorted(COMMANDS)))
        return 2
    try:
        return COMMANDS[argv[0]](argv[1:])
    except GitError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

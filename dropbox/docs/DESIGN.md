# Dropbox (ccbox) — DESIGN

## Layout

```
dropbox/
  ccbox.py          # server + client + sync, stdlib only (the whole app)
  README.md
  docs/SPEC.md      # this spec's companion: steps, divergences, limits
  docs/DESIGN.md    # this file
  docs/TEST_PLAN.md
  tests/test_ccbox.py
```

One main file on purpose (wave convention): the server, the HTTP
client helpers, the sync engine, and the CLI all live in
`ccbox.py` so there is a single file to run and to test. No
helper modules were needed.

## Server

- `http.server.ThreadingHTTPServer` + a `BaseHTTPRequestHandler`
  subclass. JSON in, JSON out, for every route.
- State lives under `--data-dir` (default `./ccbox-data`):
  - `users.json`: `{username: {salt_hex, hash_hex}}`
  - `tokens.json`: `{token: username}` (regenerated login tokens;
    persisted so a server restart keeps sessions)
  - `shares.json`: `{token: {owner, path, public}}`
  - `drive/<username>/...`: the user's virtual drive, real files
    and directories on disk, mirroring remote paths exactly.
  - `meta/<username>/...json`: per-file metadata (sha256, mtime)
    kept beside the drive, not inside it, so a `tree` listing
    never mistakes metadata for user files. The metadata file
    for remote path `a/b.txt` is `meta/<user>/a/b.txt.json`
    (the remote path with `.json` appended).
- Passwords: `hashlib.pbkdf2_hmac("sha256", password, salt,
  100_000)`, 16-byte random salt per user.
- Tokens: `secrets.token_urlsafe(32)` for logins and share links.
- Path safety: every remote path is normalised (`posixpath`
  semantics) and rejected if it is absolute, empty after
  stripping, or contains a `..` component. The resolved drive
  path is checked to stay inside the user's drive directory
  (`Path.resolve()` + `is_relative_to`-style check) before any
  read/write, so `../other-user` style traversal cannot escape.
- Upload stores bytes and records `mtime` (client-supplied, or
  server time when absent) and SHA-256 in the metadata file.
  Download reads both. `tree` walks the drive directory and
  attaches metadata per file.

## Client

- Thin wrappers over `urllib.request`: `signup`, `login`,
  `mkdir`, `list_dir`, `tree`, `upload_file`, `upload_dir`,
  `download_file`, `delete`, `create_share`, `fetch_share`.
- Each takes `server` (base URL) and `token` explicitly, so
  tests can pass them directly without environment variables.
- Errors surface as `CcboxError` (message + HTTP status where
  one exists) instead of raw `HTTPError`, so CLI and tests get
  readable failures.

## Sync engine (`sync_once`)

Pure function over (local_dir, remote tree, client helpers):

1. Walk the local tree: `{relpath: (sha256, mtime)}` for files.
2. Fetch the remote tree: `{relpath: (sha256, mtime)}`.
3. For each local file: missing remotely, or hash differs and
   local mtime >= remote mtime → upload. Recorded as `uploaded`.
4. For each remote file: missing locally, or hash differs and
   remote mtime > local mtime → download (creating parent dirs).
   Recorded as `downloaded`.
5. Anything else → `unchanged`.
6. Returns a dict `{uploaded, downloaded, unchanged}` (sorted
   lists) which the CLI prints and tests assert on.

Notes: directories alone (empty folders) are not synced — only
files carry content, and a directory is created implicitly on
either side when a file inside it transfers. This matches the
spec's "folders and their contents" behaviour for non-empty
folders and is recorded as a limit, not a silent gap: an empty
local folder does not appear remotely until it gains a file.

## CLI

`python3 ccbox.py <command> [options]`:

```
server   --port 8765 --data-dir ./ccbox-data
signup   --server URL --username U --password P
login    --server URL --username U --password P   (prints token)
mkdir    --server URL --token T --path docs
list     --server URL --token T [--path DIR]
tree     --server URL --token T
upload   --server URL --token T --local FILE|DIR --remote PATH
download --server URL --token T --remote PATH --local FILE
delete   --server URL --token T --path PATH
share    --server URL --token T --path PATH [--public]
sync     --server URL --token T --local-dir DIR [--interval 0]
```

`--server` defaults to `CCBOX_SERVER_URL` or
`http://127.0.0.1:8765`; `--token` defaults to `CCBOX_TOKEN`.
`sync --interval N` (N > 0) repeats `sync_once` every N seconds
until Ctrl-C; `--interval 0` (default) runs exactly once.

## Security notes (for a local tool)

- Plain HTTP only: run on localhost or a trusted network.
- No rate limiting / lockout on login: do not expose this
  server to the internet.
- Tokens are bearer tokens with no expiry; treat them like
  passwords and do not paste them into shared logs.

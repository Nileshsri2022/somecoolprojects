# Dropbox (ccbox) — SPEC

Source challenge: https://codingchallenges.fyi/challenges/challenge-dropbox
(read 2026-10-25; page live, not a 404)

## What it is

`ccbox` is a Dropbox-like file storage and sync tool, built as a
local-only client + server in Python 3 (standard library only).
The server holds per-user virtual drives on local disk; the client
is a CLI that talks to the server over HTTP and can sync a local
folder with the remote drive.

This is NOT a real Dropbox account, NOT cloud-hosted, and NOT a GUI.
See "Scope limits" below.

## Challenge steps (as written on the page) and how each is met

### Step 0 — Project setup
Pick a language/IDE, start a `ccbox` project.
Met: Python 3 stdlib only, single main file `ccbox.py`, no third-party
dependencies, no build step.

### Step 1 — Sign up and login
The page asks for user sign up and login, notes that rolling your
own auth is hard, and says deferring to social login is perfectly
reasonable.
Met with local auth (deliberate divergence, see below): `POST
/api/signup` and `POST /api/login`. Passwords are never stored in
cleartext: each user gets a random salt and a PBKDF2-HMAC-SHA256
hash (100,000 iterations). Login returns a random bearer token
kept server-side; every drive API call requires
`Authorization: Bearer <token>`. No social login, no OAuth, no
email verification, no password reset.

### Step 2 — Folder structure for a virtual drive
Logged-in users can see their drive's folder structure, create
top-level folders, and nest folders inside folders.
Met: `POST /api/mkdir` (creates parents as needed, like `mkdir -p`),
`GET /api/list?path=<dir>` (one level), `GET /api/tree` (recursive
listing with type, size, SHA-256 and mtime per file).

### Step 3 — Upload files (or folders and their contents)
Upload one or more files, or a folder and its contents, to a folder.
Met: `POST /api/upload` (JSON body: remote path + base64 content +
optional client mtime) and the client `upload` command, which
uploads a single file or walks a local directory recursively,
preserving relative paths. `GET /api/download?path=<file>` returns
the file content (base64) plus metadata. Uploads are whole-file;
there is no chunked/resumable upload (the page does not require
chunking — see divergences).

### Step 4 — Shareable links
Create a link to a file or folder that is either private (only the
owner can access it) or public (accessible without authentication).
Met: `POST /api/share` returns a random token and a
`/share/<token>` URL. `GET /share/<token>` serves a file's content
without authentication when the link is public; a private link
requires the owner's bearer token and rejects anyone else
(including other logged-in users). Folder links return a JSON
listing of that folder's contents rather than a file body.

### Step 5 — Sync a local folder with the online account
A CLI tool (the page explicitly allows a CLI first, background
service later) with configuration for which local folder is the
root. It polls the remote drive at a set frequency and uploads new
local files / new changes to existing files, or downloads remote
files that are newer / have changed more recently than local ones.
Met: the client `sync` command takes `--local-dir` (the root) and
`--interval` (seconds; `0` = run once). One sync pass:
- Local file missing remotely, or local SHA-256 differs from
  remote and local mtime >= remote mtime → upload.
- Remote file missing locally, or hashes differ and remote mtime
  is newer than local mtime → download.
- Identical hashes → no transfer either way.
- `--watch` / repeated runs re-poll at the interval until
  interrupted; a single run is the default and the tested mode.
- Remote files are also created as needed in nested local
  directories on download, and local nested directories are
  created remotely on upload.

## Deliberate divergences

1. Local auth instead of social login. The page permits deferring
   auth complexity to social login; this build instead rolls a
   small local PBKDF2 + bearer-token scheme so the tool works
   fully offline with no third-party account. It is NOT a
   production-grade identity system (no rate limiting, no
   lockout, no 2FA, no reset flow).
2. No web UI. The page offers "API only" for backend-focused
   builders; this build takes that option. All interaction is
   CLI + HTTP API. There is no signup/login web page, no file
   browser page, no drag-and-drop upload.
3. Whole-file upload, no chunking. The page does not specify
   chunking or versioning, so files are transferred whole and
   only the latest version is kept (no version history, no
   trash/restore). Large files are therefore limited by memory
   for the base64 JSON round-trip; this is acceptable for a
   local tool and documented, not hidden.
4. Sync does NOT propagate deletions. Deleting a file locally
   does not delete it remotely, and vice versa. This is a safety
   choice: a sync bug or an empty-folder mistake must not wipe
   the other side. Deletion is available explicitly via
   `POST /api/delete` / the `delete` CLI command.
5. Conflict rule is mtime + hash, not a merge. If both sides
   changed with different hashes, the newer mtime wins and the
   older side is overwritten on that pass. There is no
   three-way merge, no conflict-copy file, and no warning beyond
   the sync report listing what was transferred. Equal mtimes
   with different hashes: local wins (documented tie-break).
6. Single-server, single-process storage. The server stores
   metadata in JSON files and file bytes on local disk under
   its `--data-dir`. There is no database, no replication, no
   clustering, and concurrent writers are serialised only by
   the HTTP server's request handling, not by a lock file.

## Scope limits / NOT built (honestly)

- No real Dropbox account, API, or cloud hosting is touched.
- No GUI, no web frontend, no mobile client.
- No background service / startup daemon: `sync --interval N`
  is a foreground polling loop; installing it as a service is
  left to the operator.
- No CI/CD pipeline and no deployment to AWS/Azure/GCP (the
  page's "ultimate" stretch goal). The server runs on
  localhost by default.
- No sharing with named users, no permissions beyond
  owner/private-link/public-link, no link expiry, no link
  revocation UI (a link token can only be removed by deleting
  its entry from the server's `shares.json` while stopped —
  documented here, not offered as a feature).
- No encryption at rest beyond OS file permissions, and no TLS:
  the server is plain HTTP, so it must only be run on
  localhost or a trusted network. Bearer tokens sent over
  plain HTTP on an untrusted network would be exposed.
- No file previews, search, comments, or collaboration.

## API summary

All `/api/*` routes except signup/login/share-public require
`Authorization: Bearer <token>`.

| Method & route | Purpose |
|---|---|
| POST /api/signup | `{username, password}` → created |
| POST /api/login | `{username, password}` → `{token}` |
| POST /api/mkdir | `{path}` → creates folder(s) |
| GET /api/list?path= | one-level listing |
| GET /api/tree | recursive listing |
| POST /api/upload | `{path, content_b64, mtime?}` |
| GET /api/download?path= | `{content_b64, size, sha256, mtime}` |
| POST /api/delete | `{path}` → file or folder |
| POST /api/share | `{path, public}` → `{token, url}` |
| GET /share/<token> | public: no auth; private: owner token |

## Credentials

No real credentials are used, hardcoded, or requested. Usernames
and passwords in this tool are purely local test accounts created
via the signup API against the local server (e.g. in tests).
The client accepts a token via `--token` or the `CCBOX_TOKEN`
environment variable, and a server URL via `--server` or
`CCBOX_SERVER_URL`; both are placeholders for local use only
and are never sent anywhere except the configured server.

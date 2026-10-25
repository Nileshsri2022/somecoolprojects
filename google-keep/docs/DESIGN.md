# DESIGN — Google Keep (local)

## Layout

One file, standard library only:

- `keep.py` — note model/validation, `NoteStore` (JSON persistence),
  REST handler + embedded web UI, CLI. No third-party dependencies.
- `tests/test_keep.py` — unittest suite (store, validation, API over a
  real HTTP server on an ephemeral port, CLI via subprocess-free
  in-process calls).

## Components

### Note validation (`validate_note_fields`, `validate_create`, `validate_update`)

Pure functions, shared by the API and the CLI so both enforce identical
rules. Create requires at least one of title/content non-blank after
stripping; update validates only the fields supplied, then re-checks the
merged note still has at least one non-blank field (so a note cannot be
edited down to completely empty). Unknown fields are rejected. Colours
are checked against `COLORS`. Labels are stripped, empties dropped, and
duplicates removed preserving order.

### NoteStore

- In-memory dict `id -> note` (dicts, JSON-shaped throughout — no ORM,
  no separate model class, so what is stored is exactly what the API
  returns).
- `load()`: missing file → empty store; present but invalid JSON or
  wrong shape → `ValueError` (loud, never silent reset).
- `save()`: write to `<path>.tmp` in the same directory, `flush` +
  `fsync`, then `os.replace` — atomic on POSIX, so readers never see a
  half-written file.
- `create/get/list/update/delete/search` are small methods; `list_notes`
  applies the archived filter, label filter, and search query, then sorts
  pinned-first / `updated_at` descending / `id` ascending (stable
  tiebreak, so ordering is deterministic even for equal timestamps).
- Timestamps: `datetime.now(timezone.utc)` formatted with a `Z` suffix,
  microsecond precision (second precision made "recently edited first"
  ordering nondeterministic within one second). `updated_at` is refreshed
  on every update/pin/archive change, which is what drives the
  "recently edited first" ordering.

### REST API (`KeepHandler`, `ThreadingHTTPServer`)

Routes (all under `/api/notes`, JSON in/out):

| Method | Path | Result |
|---|---|---|
| GET | `/api/notes` | list; query `q`, `label`, `pinned`, `archived`, `include_archived` |
| POST | `/api/notes` | create → 201 + note |
| GET | `/api/notes/<id>` | one note or 404 |
| PUT/PATCH | `/api/notes/<id>` | merge update or 404/400 |
| DELETE | `/api/notes/<id>` | 204 or 404 |
| GET | `/` | the web UI (HTML) |

Error bodies are always `{"error": "..."}` with the matching status.
Query-flag parsing: `pinned`/`archived`/`include_archived` accept
`true/1/yes` and `false/0/no` (anything else → 400). A trailing slash on
`/api/notes/` is tolerated. Unknown `/api/*` paths → 404 JSON; unknown
non-API paths → 404 plain text.

Authentication hook: if `KEEP_TOKEN` is set at server start, every
`/api/*` request (but not the UI page itself, so the token prompt can
load) must present the exact bearer token, else 401. The UI stores the
entered token in a JS variable only (no localStorage), and sends it as
a header.

Concurrency: `ThreadingHTTPServer` plus one `threading.Lock` around
every store read-modify-write in the handler, so concurrent requests
cannot interleave a load/save cycle. The CLI is single-process and
loads/saves per command.

### Web UI (embedded HTML/JS in `keep.py`)

No build step, no external assets (works fully offline): a sticky-note
grid rendered from `GET /api/notes`, an add form at the top, a modal
editor opened by clicking a note, and per-note Pin / Archive / Delete
buttons plus a colour `<select>`. Backend failures show in a banner
(`#error`) and the add/edit draft is left in place; a 401 shows a
"token required" prompt state. Search is a text box that re-fetches with
`?q=`. Archived notes are shown via an "Archived" toggle that fetches
with `?archived=true`.

### CLI

`argparse` subcommands, each loading the store, performing one operation,
and printing either human-readable text or `--json` (for `list`/`get`/
`search`). Exit codes: 0 success, 1 usage/validation/not-found errors
(message on stderr), 2 argparse errors. `serve` defaults to
`127.0.0.1:8000` and prints the URL; `--port 0` is accepted (ephemeral)
and the chosen port is printed, which is how tests discover it.

## Trade-offs recorded

- JSON file over SQLite: matches the challenge's "disk is fine for a
  personal app" note, keeps the project one file with zero dependencies,
  and makes the data inspectable. Cost: no concurrent multi-process
  safety beyond the in-process lock, and list/search are O(n) scans —
  fine for hundreds of notes, not for Keep-scale millions.
- Single file over a package: the whole app is reviewable at once;
  the embedded UI string is the one wart, accepted to keep the
  "one main .py file" wave convention.
- No password hashing / session handling: the optional bearer token is
  a local-network guard, not a security boundary, and is documented as
  such in SPEC.

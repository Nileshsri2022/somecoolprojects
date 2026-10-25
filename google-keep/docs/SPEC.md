# SPEC — Build Your Own Google Keep

Source challenge (read 2026-10-25, before any code was written):
https://codingchallenges.fyi/challenges/challenge-keep

## What the challenge asks for

- Step 0: Backend service + persistent store + a frontend that uses the
  backend. Separate frontend/backend components are suggested (an API to
  learn REST, gRPC, or GraphQL); a single CLI-only app is explicitly allowed
  as an alternative.
- Step 1: API endpoint to add a new note. A note consists of **Title** and
  **Note Content**. The note must be saved to persistent storage (disk is
  fine for a personal, single-user app). Test automation covering happy path
  and error conditions is requested at this stage.
- Step 2: API endpoint to view a single note. Notes need a unique identifier.
- Step 3: API endpoint to fetch a list of notes. Authentication is raised
  here: notes are per-user and private; social login is suggested as reading
  material, not mandated.
- Step 4: UI(s) to list and view notes, as a collection of sticky notes
  (mobile and web look similar in the real app).
- Step 5: UI(s) to add notes: a button, an entry UI, and a call to the
  backend API. The UI must handle backend failures, distinguishing permanent
  failures (need user action) from transient ones.
- Step 6: UI(s) to edit a note (click a note → editor, saved on exit) plus
  an API endpoint to update a note, with tests and input validation.
- Going Further: (1) a second UI, (2) voice notes, (3) searching notes,
  (4) ordering and pinning notes.

## What this build implements

All of Steps 0–6, plus Going Further (3) search and (4) pin/ordering:

- A REST API (`keep.py serve`) over Python's standard-library HTTP server:
  `GET /api/notes`, `POST /api/notes`, `GET /api/notes/<id>`,
  `PUT`/`PATCH /api/notes/<id>`, `DELETE /api/notes/<id>`.
- Persistent storage: one JSON file, written atomically (temp file +
  `os.replace`), so a crash mid-write does not corrupt the note file.
- A note has: `id` (UUID4 hex), `title`, `content`, `color`, `labels`
  (list of strings), `pinned` (bool), `archived` (bool), `created_at`,
  `updated_at` (UTC ISO-8601, `Z` suffix).
- A single responsive web UI served by the same process (`GET /`): a sticky-
  note grid, an add form, click-to-edit in a modal (saved on Save/close),
  search box, pin / archive / delete buttons, and a colour picker. The UI
  shows backend failures in an error banner and keeps the user's draft in
  the form instead of discarding it.
- A CLI over the same store (`add`, `list`, `get`, `edit`, `delete`,
  `pin`, `unpin`, `archive`, `unarchive`, `search`, `serve`) for
  headless/scripted use.
- List ordering: pinned notes first, then most-recently-updated first.
  Archived notes are excluded from the default list and returned only with
  `?archived=true` or `?include_archived=true`.
- Search (`?q=` / CLI `search`): case-insensitive substring match over
  title, content, and labels.
- Validation (API and CLI alike): a note needs at least one non-blank field
  among title/content; title ≤ 1000 chars, content ≤ 50000 chars; `color`
  must be one of the palette names below (unknown → 400); `labels` must be
  a list of non-empty strings; `pinned`/`archived` must be booleans.
  Unknown JSON fields on create/update are rejected with 400 (fail loudly
  rather than silently dropping data). Malformed JSON → 400, unknown id →
  404, wrong method on a known path → 405, non-JSON body on
  POST/PUT/PATCH → 415.
- Colour palette: `default red orange yellow green teal blue purple pink
  brown gray`.

## Deliberate divergences (honest, not silent)

1. **Local-only, single user — no Google account, no cloud sync.** No real
   Google credentials are used, requested, or stored, and no real Google
   account is touched. Notes live only in the local JSON file. This is a
   local note app in the shape of Keep, NOT a Google Keep clone UI and NOT
   a sync client.
2. **Authentication is local-only and optional, not social login.** The
   challenge suggests reading about social login; implementing real social
   login would require third-party credentials and a hosted identity
   provider, out of scope for a local stdlib app. Instead: the server binds
   to `127.0.0.1` by default, and if the `KEEP_TOKEN` environment variable
   is set, API requests must carry `Authorization: Bearer <token>`
   (the web UI prompts for it and stores it only in session memory).
   The CLI bypasses the token because it owns the local file directly.
   This is documented as a limitation, not as real multi-user auth:
   anyone who can read the local file can read the notes.
3. **One web UI, not web + native mobile.** The web UI is responsive and
   usable from a phone browser, but there is no native mobile app and no
   second (mobile) UI, so Going Further (1) is only partially met.
4. **Hard delete, no trash.** The real Keep keeps deleted notes in Trash
   for a while; here `DELETE` removes the note immediately. Not built.
5. **Update is a partial merge, not a full replacement.** `PUT` and `PATCH`
   both merge the supplied fields into the existing note. This is simpler
   and matches the "edit on exit" UI; it is a deviation from strict REST
   PUT semantics and is stated here deliberately.

## NOT built (scope limits)

- Voice notes (Going Further 2) — no audio capture, transcription, or
  playback.
- Reminders / scheduled notifications, checklists as structured items
  (checklist-style text inside `content` works as plain text), image or
  drawing notes, OCR, collaboration/sharing, multi-user accounts,
  cloud sync, offline-conflict resolution, and import/export from real
  Google Keep.
- gRPC / GraphQL — the API is REST over HTTP, the challenge's first
  suggested option.
- Any Google branding, logos, or API endpoints.

## Storage format

`notes.json`: `{"version": 1, "notes": [<note>, ...]}`. A missing file
starts empty; a corrupt file raises an error instead of silently starting
empty (data loss must be loud). The default path is `notes.json` in the
current working directory, overridable with `--data` or `KEEP_DATA`.

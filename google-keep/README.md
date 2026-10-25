# google-keep — Build Your Own Google Keep (local)

Coding Challenges: https://codingchallenges.fyi/challenges/challenge-keep,
worked in `somecoolprojects/`. Docs first, then code — see `docs/`.

A local note-taking app in the shape of Google Keep: a REST API, a
responsive sticky-note web UI served by the same process, and a CLI over
the same JSON store. Notes have title, content, colour, labels, pinned,
and archived flags; listing is pinned-first then most-recently-updated,
with search over title, content, and labels.

**Local only — not a Google product, not a sync client.** No Google
account, no cloud sync, no real credentials of any kind. Notes live only
in the local JSON file. See `docs/SPEC.md` for the full list of
divergences and scope limits.

## Usage

```sh
# Serve API + web UI on http://127.0.0.1:8000/
python3 keep.py serve
python3 keep.py serve --port 8080 --data ./notes.json

# CLI (same store; default data file is notes.json in the cwd)
python3 keep.py add --title "Groceries" --content "milk, eggs" --label home
python3 keep.py list
python3 keep.py list --search milk --json
python3 keep.py search groceries
python3 keep.py get <id>
python3 keep.py edit <id> --title "New title"
python3 keep.py pin <id> | python3 keep.py archive <id>
python3 keep.py delete <id>
```

API: `GET /api/notes[?q=&label=&pinned=&archived=&include_archived=]`,
`POST /api/notes` → 201, `GET /api/notes/<id>`, `PUT`/`PATCH
/api/notes/<id>` (partial merge), `DELETE /api/notes/<id>` → 204.
Errors are `{"error": "..."}` with 400/401/404/405/415. If `KEEP_TOKEN`
is set, API requests need `Authorization: Bearer <token>`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

16 tests: store CRUD/validation/persistence/ordering/search, the full
HTTP lifecycle and error paths over a real server on an ephemeral port,
token auth, the UI route, and a CLI round-trip.

## Files

- `keep.py` — store, REST API + embedded web UI, CLI (stdlib only).
- `docs/SPEC.md` — challenge steps, divergences, and what is NOT built.
- `docs/DESIGN.md` — components and trade-offs.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_keep.py` — the test suite.

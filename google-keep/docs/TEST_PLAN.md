# TEST_PLAN — Google Keep (local)

Run: `python3 -m unittest discover -s tests -v` from `google-keep/`.
All tests use temporary directories / ephemeral ports; no test touches a
real data file, a real Google account, or the network beyond localhost.
HTTP API tests start a real `ThreadingHTTPServer` on port 0 in a thread
and shut it down in `tearDown` (no stray servers).

## Store / validation tests

1. Create: fields stored, id is a 32-char hex UUID, timestamps set,
   defaults (`color=default`, `labels=[]`, `pinned=false`,
   `archived=false`).
2. Create validation: empty title+content rejected; blank-only rejected;
   title > 1000 chars rejected; content > 50000 rejected; bad colour
   rejected; non-list labels rejected; empty-string labels dropped,
   duplicates de-duplicated; unknown field rejected.
3. Get: existing note returned; unknown id → `KeyError`.
4. Update: partial merge keeps untouched fields; `updated_at` advances
   (or stays equal if within the same second — test asserts >=);
   editing a note to fully empty rejected; unknown id → `KeyError`;
   bad colour / unknown field rejected.
5. Delete: note gone afterwards; deleting unknown id → `KeyError`.
6. Pin/archive: flags flip and persist across a store reload.
7. Persistence: notes survive `NoteStore` reload from the same file;
   save is atomic (no `.tmp` file left behind); corrupt JSON file raises
   `ValueError` instead of silently resetting.
8. Ordering: pinned notes first, then `updated_at` descending.
9. Search: case-insensitive substring over title, content, labels;
   no-match → empty list; archived notes excluded from default search
   unless requested.
10. List filters: `archived=true` returns only archived; `label=` filters;
    `pinned=true` filters.

## API tests (real HTTP, ephemeral port)

11. Full lifecycle over HTTP: POST 201 → GET one 200 → PUT edit 200 →
    GET list contains it → DELETE 204 → GET one 404.
12. Error paths: malformed JSON → 400; non-JSON content-type → 415;
    unknown field → 400; empty note → 400; unknown id → 404;
    wrong method (e.g. POST to `/api/notes/<id>`) → 405;
    unknown `/api/*` path → 404 with JSON error body.
13. Query handling: `?q=`, `?label=`, `?pinned=true`, bad flag value → 400.
14. UI route: `GET /` returns 200 with `text/html` containing the grid
    container.
15. Token auth (when enabled): request without token → 401; with the
    correct bearer token → 200. (Tested by starting a second server with
    `KEEP_TOKEN` set in-process via the handler factory, not by env
    mutation of the running process.)

## CLI tests

16. CLI `add`/`list`/`get`/`edit`/`delete`/`pin`/`search` round-trip
    against a temp data file via in-process `main(argv)` calls with
    captured stdout; not-found and validation failures exit non-zero
    with a message on stderr.

## Manual checks (done once, not in the suite)

- Start `python3 keep.py serve`, open http://127.0.0.1:8000/ in a
  browser, add/edit/pin/archive/search a note, reload the page, and
  confirm persistence; stop the server and confirm no process remains.
  (Browser-dependent, so verified by the parent if a live browser is
  available; the automated suite covers the same paths over HTTP.)

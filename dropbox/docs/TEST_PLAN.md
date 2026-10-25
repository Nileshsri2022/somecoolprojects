# Dropbox (ccbox) — TEST_PLAN

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

No network beyond localhost, no third-party packages, no real
accounts. Every test starts its own server on an ephemeral port
(`port 0`, OS-assigned) in a background thread with a fresh
temporary data directory, and shuts it down in tearDown. No
test server is left running after the suite.

## Coverage map

| Area | Tests |
|---|---|
| Signup / login | new user can log in; duplicate signup rejected; wrong password rejected; unknown user rejected |
| Auth enforcement | list/tree/upload/download/mkdir without a token rejected (401); with another user's token, a user's drive is not visible (separate drive roots) |
| Folders | mkdir creates nested folders; list shows them; tree lists nested files |
| Upload / download | text and binary round-trip byte-identical; download of missing file rejected; upload overwrites with new content + new hash |
| Path safety | `../escape`, absolute paths, and empty paths rejected on upload and mkdir |
| Share links | public link fetchable with no token; private link fetchable by owner, rejected anonymously and by another user; share of missing path rejected |
| Sync | local-only file uploads; remote-only file downloads; identical file is a no-op; locally newer changed file uploads; remotely newer changed file downloads; sync report lists exactly what moved |
| Delete | delete removes a file and then download fails; delete of missing path rejected |
| Client folder upload | upload_dir preserves nested relative paths |

## Manual checks (not automated, done by reading code paths)

- `python3 ccbox.py server --port 8765` starts and answers
  `GET /api/tree` with 401 when no token is supplied.
- `sync --interval 2` repeats passes until Ctrl-C (loop only;
  the automated suite covers the single-pass engine, which is
  the same code path).
- Empty local folders are not synced (documented limit in
  SPEC/DESIGN); verified by reasoning over `sync_once`, which
  walks files only, not by a dedicated test.

## Known non-goals for testing

- No GUI/browser tests (no frontend exists).
- No TLS, load, or concurrency soak tests (single-user local
  tool; threading server is exercised only lightly by the
  sequential test client).
- No performance benchmarks; base64 JSON upload is known to
  be memory-heavy for very large files (see SPEC).

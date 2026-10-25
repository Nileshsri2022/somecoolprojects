# Notion — TEST_PLAN

Run: `python3 -m unittest discover -s tests -v` from `notion/`
(or `python3 -m unittest discover -s tests` for quiet output).
Stdlib `unittest` only. Every test uses a temporary directory
(`tempfile.TemporaryDirectory`) as its store — no test touches a real
workspace file, and no test needs the network except the HTTP test, which
binds `127.0.0.1` on port 0 (ephemeral) and shuts the server down in
`tearDown`.

## Coverage map

- Users/auth: duplicate registration rejected; wrong password rejected;
  unknown user rejected; stored value is a `salt$hash`, not the password;
  two users with the same password get different hashes (random salt).
- Pages: default title "Untitled"; create under a parent; listing is
  nested and ordered; per-user isolation (user B cannot read/list/move
  user A's page; B's listing does not contain A's pages).
- Blocks: all five types accepted; invalid type rejected; add/edit/delete
  round-trip; move-block reorders within a page; out-of-range move and
  unknown block/page rejected; editing a block's type works.
- Duplication: copy has new ids, same blocks text, "Copy of" name;
  second duplicate gets "(1)"; child pages are copied recursively with
  the copy nested under the copied parent, not the original.
- Reorganisation: move-page reparents (child appears under new parent,
  disappears from old); move to top level; cycle (under self/descendant)
  rejected; cross-user parenting rejected; reorder sets an exact sibling
  order and rejects a set that adds/omits a sibling.
- Search: title match, block-text match, case-insensitive, no match
  returns empty, other users' pages never returned.
- Persistence: save → fresh `Workspace.load` round-trips users, pages,
  blocks, order, and parent links.
- Rendering: `**bold**` → `<strong>`, `*italic*` → `<em>`, HTML in text
  is escaped (no raw `<script>` passthrough), unmatched markers literal.
- HTTP view: server on an ephemeral port serves `/` (contains page
  titles) and `/page/<id>` (contains block text); unknown page → 404;
  server is stopped after the test.
- CLI: end-to-end via `main()` with argv lists — register, create-page,
  add-block, list-pages, duplicate-page, search — plus CLI error exit
  code 2 on bad credentials.
- Page deletion (library-only): recursive delete removes children too.

## Manual checks (done at build time, not in the suite)

- `python3 notion.py serve --port 0` prints an actual port; opening the
  printed URL in a browser shows the sidebar + page (not asserted here
  because this worker has no live browser; the HTTP test asserts the same
  HTML over a socket instead).
- CLI `--help` lists all subcommands.

## Known test gaps (honest)

- No concurrency test: concurrent writers are out of scope (see SPEC).
- No browser/UI test: there is no JS frontend to drive.
- No performance test: the JSON store is fine for personal-scale data.

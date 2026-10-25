# Notion — DESIGN

## Stack

Python 3 standard library only: `argparse`, `hashlib`, `hmac`, `json`,
`os`, `secrets`, `uuid`, `html`, `http.server`, `urllib.parse`. No
third-party packages, no database server. Python 3.12 verified locally.

## Layout (single main file, by design)

```
notion/
  README.md
  docs/SPEC.md  docs/DESIGN.md  docs/TEST_PLAN.md
  notion.py          # everything: store, users, pages, blocks, CLI, HTTP view
  tests/test_notion.py
```

One file keeps the "one main .py file" wave rule. It is organised in
sections so it can be split later without behaviour change:

1. Constants & errors (`NotionError`, `BLOCK_TYPES`).
2. Password hashing (`hash_password` / `verify_password`: PBKDF2-HMAC-SHA256,
   200,000 iterations, 16-byte salt, stored as `salt_hex$hash_hex`).
3. `Workspace` — the store. `load(path)` / `save()` (atomic-ish: write to
   a temp file in the same directory, then `os.replace`). In-memory dicts:
   `users: {username: user-dict}`, `pages: {id: page-dict}`.
4. User operations: `register_user`, `authenticate` (constant-time compare
   via `hmac.compare_digest`).
5. Page operations: `create_page`, `get_page_for_user` (ownership check),
   `list_top_level` / `children_of` (sorted by `order`, then `created_at`
   as a stable tiebreak), `update_title`, `duplicate_page` (recursive),
   `move_page`, `reorder_siblings`, `delete_page` (not exposed on the CLI
   except via duplication tests — see note below), `search`.
6. Block operations: `add_block`, `edit_block`, `delete_block`,
   `move_block` (reorder within a page).
7. Rendering: `render_inline(text)` — escape HTML first, then replace
   `**...**` with `<strong>` and `*...*` with `<em>` (non-greedy, no
   nesting support; unmatched markers stay literal). `render_page_html`,
   `render_workspace_html` (sidebar nav, nested `<ul>`).
8. HTTP view: `NotionHTTPRequestHandler` (a `BaseHTTPRequestHandler`
   subclass) + `make_server(data_path, port)` returning an
   `http.server.ThreadingHTTPServer`. Routes: `GET /` (workspace index),
   `GET /page/<id>` (page HTML, 404 for unknown ids). Everything else 404.
   The handler reloads the store file per request, so CLI edits show up
   without restarting the server.
9. CLI: `argparse` subparsers, one function per command, `main(argv)`.
   Authentication is re-checked on every mutating/read command from
   `--user`/`--password`; there is no session token file (simpler and
   avoids a stale-token footgun for a local tool).

## Ordering model

Siblings (pages sharing a `parent_id`, or all top-level pages of a user)
carry an integer `order`. Creating a page appends it (`max + 1`). Moving
a page removes it from the old sibling list, inserts it at the requested
position in the new list, and renumbers both lists densely from 0.
`reorder_siblings` validates that the supplied id list is exactly the
current sibling set (same ids, any order) and then renumbers. This keeps
ordering total and deterministic after any sequence of moves.

## Duplication model

`duplicate_page` copies a page's title/blocks (new block ids, same text)
and recursively copies its child pages, preserving their relative order.
The copy is placed as the last sibling of the original's parent. The new
title rule: `Copy of <title>`, then `Copy of <title> (1)`, `(2)`, …
— uniqueness is checked against the duplicating user's existing titles
among that parent's siblings only if needed; in practice the loop appends
a counter until the title is unused among the user's pages. (Implementation
checks all of the user's page titles, which is stricter and simpler.)

## Cycle protection

`move_page` rejects: moving a page under itself, moving it under any of
its own descendants, and parenting to a page owned by another user. The
descendant check walks `parent_id` links upward from the target parent.

## Deletion note

Page deletion exists in the library (`delete_page`, recursive) and is
unit-tested, but is intentionally NOT exposed as a CLI command in this
wave: the challenge steps never ask for delete-page, and exposing it
without a confirmation step risks data loss in a local tool. Block
deletion IS exposed (Step 3 editing). This is a deliberate omission,
recorded here and in SPEC's scope limits rather than silently added.

## Storage format (JSON, versioned lightly)

```json
{"users": {"alice": {"username": "alice", "password_hash": "salt$hash",
  "created_at": "..."}},
 "pages": {"<uuid>": {"id": "...", "owner": "alice", "title": "Untitled",
  "parent_id": null, "order": 0, "blocks": [{"id": "...",
  "type": "paragraph", "text": "..."}], "created_at": "...",
  "updated_at": "..."}}}
```

Timestamps are ISO-8601 UTC strings, informational only; ordering never
depends on wall-clock except as a tiebreak.

## Error handling

All domain failures raise `NotionError(ValueError)` with a plain message;
the CLI catches it, prints `error: <message>` to stderr, and exits 2.
Unknown pages/blocks, duplicate usernames, bad credentials, bad block
types, out-of-range positions, and invalid reorder sets are all errors,
never silent no-ops.

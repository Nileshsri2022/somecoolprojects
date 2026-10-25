# Notion — SPEC

Source challenge: https://codingchallenges.fyi/challenges/challenge-notion
("Build Your Own Notion", read 2026-10-25; page live, not a 404.)

## What this build is

A local-only, Notion-like workspace/docs app in Python 3 standard library
only. No real Notion account, API key, or network service is used, requested,
or touched. All data lives in one local JSON file. The primary interface is
a CLI (`notion.py`); a small local HTTP server renders a read-only HTML
view of the workspace (sidebar navigation + page content).

## Challenge steps — coverage

| Step | Challenge asks | This build |
|---|---|---|
| Step 0 | Backend + persistent store + frontend, separate components / API to learn from | Local JSON store + CLI + local HTTP view in one stdlib file. The HTTP view is a view, not a separate frontend app; there is no REST/gRPC/GraphQL API (see divergences). |
| Step 1 | Home page + register/login flow (one-time codes suggested as an alternative to passwords) | `register` / `login` commands. Local accounts only. Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a random salt — never plaintext. No email, no one-time codes (see divergences). |
| Step 2 | Workspace shown after login, initially blank, with a 'Create Page' action | `list-pages` shows an empty workspace for a new user; `create-page` creates a page. The HTTP view shows the same, with a "Create Page" note pointing at the CLI. |
| Step 3 | Add a page, edit its contents; title replaces 'Untitled'; formatting: three heading levels, bullet points, bold, italic; backend DB + API | Pages default to title "Untitled". Blocks: `heading_1`, `heading_2`, `heading_3`, `paragraph`, `bulleted_list_item`. Bold/italic are inline Markdown-style markers (`**bold**`, `*italic*`) stored in block text and rendered as `<strong>`/`<em>` in HTML. Blocks can be added, edited, deleted, and reordered within a page. |
| Step 4 | Navigation bar listing all pages the user created | `list-pages` prints the user's pages in order, nested by parent. The HTTP view renders a sidebar with the same nested list. Pages are per-user: a user sees only their own pages. |
| Step 5 | Duplicate a page; sensible name, i.e. "Copy of" prefix and/or "(1)" suffix | `duplicate-page` deep-copies a page (title, blocks, and — recursively — child pages). First duplicate is named `Copy of <title>`; further duplicates of the same source become `Copy of <title> (1)`, `(2)`, … (see divergence note on the page's ambiguous wording). |
| Step 6 | Re-organise: group pages under other pages, re-order them in navigation | `move-page` reparents a page (including to the top level) and places it at a position among its new siblings; `reorder` sets the full sibling order. Nesting is by `parent_id`; cycles are rejected. |
| Step 7 (Bonus) | AI text generation via an LLM (Ollama / llama3 suggested) | NOT BUILT. No LLM, no Ollama call, no network model. See "Not built". |
| Going Further | Mobile/desktop app (e.g. Electron) on the same backend | NOT BUILT. |

## Data model

- User: `username`, `password_hash` (PBKDF2-HMAC-SHA256, hex `salt$hash`),
  `created_at`.
- Page: `id` (uuid4), `owner` (username), `title`, `parent_id` (null = top
  level), `order` (int, position among siblings), `blocks` (list), `created_at`,
  `updated_at`.
- Block: `id` (uuid4), `type` (one of the five types above), `text`.
- A page's children are pages whose `parent_id` equals that page's id.
  Ownership is inherited at creation: a child page's owner is its parent's
  owner, and cross-user parenting is rejected.

## Commands (CLI, `python3 notion.py <command> ...`)

Global: `--data PATH` (default `notion_workspace.json` in the working
directory) selects the JSON store file.

- `register --user NAME --password PASS` — create a local account.
- `login --user NAME --password PASS` — verify credentials, print OK.
- `create-page --user NAME --password PASS [--title T] [--parent ID]`
  — prints the new page id.
- `list-pages --user NAME --password PASS` — nested, ordered listing.
- `show-page --user NAME --password PASS --page ID` — title + blocks.
- `add-block --user NAME --password PASS --page ID --type TYPE --text TEXT`
- `edit-block --user NAME --password PASS --page ID --block ID --text TEXT`
  (also `--type TYPE` to change a block's type).
- `delete-block --user NAME --password PASS --page ID --block ID`
- `move-block --user NAME --password PASS --page ID --block ID --to INDEX`
- `duplicate-page --user NAME --password PASS --page ID` — prints new id.
- `move-page --user NAME --password PASS --page ID [--parent ID | --top] [--position N]`
- `reorder --user NAME --password PASS --parent ID|top --order ID,ID,...`
  — `--parent top` means top-level siblings; the order must list exactly
  the current siblings, no more, no fewer.
- `search --user NAME --password PASS QUERY` — matches page titles and
  block text (case-insensitive substring), own pages only.
- `serve --port PORT` — start the local HTTP view (default port 8000;
  `--port 0` picks an ephemeral port and prints the actual port). No login
  is required on the HTTP view: it renders the local store file, so only
  ever serve a store you are happy to show locally. See security note.

## Deliberate divergences (honest)

1. **No separate frontend / no REST, gRPC, or GraphQL API.** The challenge
   suggests separate frontend/backend as a learning opportunity, not as a
   graded contract. This build keeps one stdlib file: a CLI plus a small
   read-only HTML view over the same JSON store. Building a full REST API
   + JS frontend was out of scope for a local-core build.
2. **Passwords, not one-time codes.** The challenge says "you might like
   to try" one-time codes. No email/SMS channel exists locally, so this
   build uses salted PBKDF2 password hashes instead. No password is ever
   stored or printed in plaintext.
3. **Duplicate naming.** Step 5's wording ("add '(1)' after the name of
   'Copy of' to the beginning") is ambiguous. Rule implemented: first
   duplicate `Copy of <title>`, then `Copy of <title> (1)`, `(2)`, …
   Duplicating a duplicate follows the same rule against its own title.
4. **HTTP view is read-only and unauthenticated.** It renders whatever is
   in the local store file. It is a viewing aid, not a multi-user service.
   Do not serve a store containing private notes on a shared network.
5. **Inline formatting is Markdown-style markers in text**, not a rich-text
   editor with toolbar/selection state. `**bold**` and `*italic*` are stored
   verbatim and rendered to HTML with escaping; unmatched markers are left
   as literal text.

## NOT built (scope limits — do not claim these)

- Real Notion UI, real Notion API/account/sync, cloud storage, or any
  network call to Notion. This is a local clone of the core concepts only.
- Real-time collaboration, sharing/permissions, comments, multi-user
  editing, or conflict resolution. Pages are strictly per-user.
- AI text generation (Step 7 bonus) / Ollama / any LLM integration.
- Databases/tables, kanban boards, calendars, templates gallery, file
  uploads, images, embeds, drag-and-drop UI, or a desktop/mobile app.
- One-time-code / email login, password reset, or account recovery.
- A REST/gRPC/GraphQL API and a separate JS frontend (see divergence 1).
- Concurrent-write locking: the JSON store is rewritten on every mutation.
  Two processes writing at once can lose each other's last write; this is
  a single-user local tool, not a server database.

## Security / privacy notes

- Never put real Notion credentials in this project; it never asks for
  them. Local CLI passwords are only used to derive the stored hash.
- The JSON store contains password hashes and page contents in plaintext
  (page text is not encrypted). Keep the store file private to the user.

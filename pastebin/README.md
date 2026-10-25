# Pastebin

Build Your Own Pastebin — Coding Challenges #60
(https://codingchallenges.fyi/challenges/challenge-pastebin/).

A tiny pastebin in one Python file, standard library only. Paste text,
get a unique URL (`/<id>`), view it, view it raw, or delete it
(with confirmation). Pastes can expire, and Python pastes get simple
keyword highlighting.

## Run

```
python3 pastebin.py [--port 8080] [--host 127.0.0.1] [--store pastes.json]
```

Then open http://127.0.0.1:8080/ (or your chosen port).

- Default storage is in-memory (lost on restart). Pass `--store` for a
  JSON file that survives restarts.
- No authentication: anyone with a paste's URL can view or delete it.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/` | Form + recent pastes |
| POST | `/` | Create: form fields `content`, `expiry`, `language` → 303 to `/<id>`; or JSON `{"content", "expiry_seconds", "language"}` → 201 `{"id", "url"}` |
| GET | `/<id>` | Snippet page |
| GET | `/<id>/raw` | Exact content, `text/plain` |
| GET | `/<id>/delete` | Delete confirmation |
| POST | `/<id>/delete` | Deletes, redirects home |

Expiry options: never, 10 minutes, 1 hour, 1 day, 1 week.
Languages: plain, Python, JavaScript, HTML, SQL (highlighting is
Python-only; others render as plain escaped text).

## Test

```
python3 -m unittest discover -s tests -v
```

Tests spin up the real server on an ephemeral localhost port.

## Docs

- `docs/SPEC.md` — page steps, interface, success criteria
- `docs/DESIGN.md` — assumptions, storage/expiry/id/highlighting
  tradeoffs, divergences
- `docs/TEST_PLAN.md` — test cases and how to run them

## Divergences from the challenge page

- Step 5 (cloud deploy with CI/CD + IaC) is not built: this build is
  local-only by task constraint; the server is a plain stdlib app, so
  deploying it later is just running it behind a reverse proxy.
- Step 6 highlighting covers Python only (stdlib has no Pygments);
  other languages are stored, labelled, and rendered as plain text.
- The home page's recent-pastes list is an addition (the page does
  not specify a list view); it shows live pastes only.

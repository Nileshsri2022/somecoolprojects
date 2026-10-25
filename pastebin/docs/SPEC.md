# Pastebin — Specification

Source: https://codingchallenges.fyi/challenges/challenge-pastebin/
("Build Your Own Pastebin", Coding Challenges #60). Slug used: `challenge-pastebin`.
No correction was needed: the first-guess URL returned the full page (no 404).

## Page steps implemented

- **Step 1 — Create:** a form page lets the user paste content and submit.
  Submitting generates a unique id and a unique URL of the form `/<id>`
  (e.g. `/fe45swq`), as in the page's example.
- **Step 2 — Store and retrieve:** the content is stored and shown when the
  unique URL is visited. After a form submission the user is redirected
  (303) to the snippet URL, as the page suggests.
- **Step 3 — Delete:** the snippet page has a delete button. Clicking it
  shows a confirmation page ("check they meant to delete it"); confirming
  deletes the snippet. Visiting a deleted URL returns 404, and deleting
  twice returns 404 on the second attempt.
- **Step 4 — Expiry:** the submission form offers an expiry (never,
  10 minutes, 1 hour, 1 day, 1 week). Access after the expiry time
  returns 404 and the paste is removed.
- **Step 5 — Deploy:** NOT built. The task forbids external hosting and
  pushing; the server is local-only (see DESIGN.md). The app is a plain
  stdlib server, so deploying it later is just running `pastebin.py`
  behind any reverse proxy.
- **Bonus Step 6 — Formatting:** the submission form offers a language
  (plain, Python, JavaScript, HTML, SQL). The snippet page renders the
  content with simple keyword highlighting for Python (and plain escaped
  text for the others). This is a stdlib approximation, not Pygments —
  see "Divergences".
- **Going Further (partial):** a raw view (`/<id>/raw`) returns the exact
  content as `text/plain`; the home page lists recent (live) pastes.

## HTTP interface

| Method | Path | Behaviour |
|---|---|---|
| GET | `/` | Home page: submission form + list of recent live pastes. |
| POST | `/` | Create a paste. Form-encoded body (`content`, `expiry`, `language`) → 303 redirect to `/<id>`. JSON body (`{"content": ..., "expiry_seconds": ..., "language": ...}`) → 201 with `{"id": ..., "url": "/<id>"}`. Empty content → 400. |
| GET | `/<id>` | Snippet page (highlighted if Python, otherwise escaped `<pre>`), with delete link and raw link. Unknown / deleted / expired id → 404. |
| GET | `/<id>/raw` | Exact content, `Content-Type: text/plain`. Unknown / deleted / expired → 404. |
| GET | `/<id>/delete` | Confirmation page. Unknown / deleted / expired → 404. |
| POST | `/<id>/delete` | Deletes the paste, 303 redirect to `/`. Unknown / already deleted → 404. |

Expiry values on the form: `never`, `600`, `3600`, `86400`, `604800`
(seconds). Via JSON: `expiry_seconds` is a number of seconds, or `null`
for never. `expiry_seconds <= 0` means "already expired" (useful for
testing); the paste is never retrievable.

Ids: 7 random base62 characters (`[A-Za-z0-9]`), matching the page's
`fe45swq` example length. Collisions are retried until unique.

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes (see TEST_PLAN.md).
- A paste created via the form is retrievable at its URL, deletable
  with confirmation, and gone (404) afterwards.
- An expired paste returns 404; a never-expiring paste stays retrievable.
- Pasted HTML (e.g. `<script>`) is escaped on the snippet page, never
  executed.

# SPEC — Build Your Own URL Shortener (Coding Challenges #12)

Source: https://codingchallenges.fyi/challenges/challenge-url-shortener/
(read 2026-10-25; the challenge page itself is the spec — this file
summarises it, it does not replace it.)

A service that accepts a long URL, stores a short code for it, and
redirects requests for the short code to the long URL — think bit.ly /
tinyurl.com.

## Step 1 — Create a shortened URL

- `POST /` with `Content-Type: application/json` and body
  `{"url": "https://www.example.com"}`.
- On success, return a suitable HTTP status code and JSON of the form:

  ```json
  {"key": "Y3S9wb", "long_url": "https://www.example.com",
   "short_url": "http://localhost/Y3S9wb"}
  ```

  (`short_url` is the host the request was made to, plus `/` plus the key;
  the page's example uses `http://localhost` because its server runs
  there.)
- Idempotent: if the URL already exists, return the same status code
  and the existing shortened version — a repeat POST must not change
  state.
- If the request is invalid, return a suitable HTTP status code (400)
  and a clear error message, e.g. for a body without the `url` field:

  ```
  HTTP/1.1 400 Bad Request

  Missing field: url
  ```

- Bonus: a duplicate key generated from a different long URL must be
  handled (e.g. add a unique value to the hash input and re-hash).

## Step 2 — Redirect

- `GET /<key>` returns `302 Found` with a `Location` header naming the
  long URL and an empty body.
- `GET /<unknown-key>` returns `404 Not Found` with body `URL not found`.

## Step 3 — Delete

- `DELETE /<key>` returns `200 OK` with an empty body when the key
  exists; a subsequent `GET /<key>` returns 404.
- Deleting a key that does not exist takes no action (still 200 OK,
  empty body — delete is idempotent, same as create).
- After deletion the key and URL no longer exist in storage.

## Steps 4 (both optional — NOT built here)

- A GUI web form for creating shortened URLs.
- A CI/CD pipeline deploying the service.

See DESIGN.md for the choices this spec leaves open (status code for
create, key length/alphabet, storage, validation rules) and the
deliberate divergences from the page's examples.

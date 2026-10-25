# DESIGN — URL Shortener

Assumptions stated before coding (ponytail: think before coding).

## Stack

Python 3 standard library only, single file `url_shortener.py`, built
on `http.server.ThreadingHTTPServer`. No dependencies, no database:
the challenge page itself says its author used an in-memory store, and
the task for this project allows in-memory storage. Persistence is the
one deliberate scope cut — a restart loses all mappings (see README).

## Storage

Two dicts, guarded by one `threading.Lock` (the server is threaded):

- `key -> long_url`
- `long_url -> key` (reverse index, so idempotent create is O(1))

Delete removes the entry from both dicts.

## Key generation

- Alphabet: base62 (`0-9A-Za-z`), 6 characters — the page's examples
  use 5–6 character keys (`wsf5f`, `Y3S9wb`, `jlrtPU`), and 62^6
  (~56 billion) makes accidental collision negligible at this scale.
- Deterministic: `SHA-256(long_url)`, first bytes mapped to base62.
  Determinism is what makes create idempotent for free — the same URL
  always hashes to the same key, so the reverse index just returns it.
- Collision handling (the page's bonus point): if the generated key
  already maps to a *different* long URL, re-hash
  `SHA-256(long_url + ":" + counter)` with counter = 1, 2, … until a
  free key (or the same URL's key) is found. A unit test forces this
  path by pre-seeding a colliding key.

## API decisions (where the page leaves the choice open)

| Decision | Choice | Reason |
|---|---|---|
| Create success status | `201 Created`, for new and existing URLs alike | "Suitable" code for creating a resource; the page requires the *same* code on repeat, so both paths return 201. |
| `short_url` host | The request's `Host` header, scheme `http` | Reproduces the page's `http://localhost/<key>` when served on localhost, and stays correct on an ephemeral test port. |
| Error bodies | Plain text, e.g. `Missing field: url` | Matches the page's 400 example exactly (plain text, not JSON). |
| URL validation | Must be a non-empty string, scheme `http` or `https`, with a host (`netloc`) | Rejects `""`, `notaurl`, `ftp://…`, non-string values; anything stricter (reachability checks, allow-lists) would be speculative. |
| `GET /` (no key) | `404 URL not found` | There is no key to look up; the root path is the create endpoint (POST), not a redirect. |
| Delete of unknown key | `200 OK`, empty body | The page says delete "takes no action" for a missing key — no error, no state change. |
| Unknown methods / POST to a non-root path | `404 URL not found` for a mistargeted POST; other methods fall back to the stdlib handler's `501` | Out of spec; kept minimal, not tested as API behaviour. |

## Request handling notes

- JSON body must be an object containing a string `url` field:
  malformed JSON → `400 Invalid JSON`; missing field →
  `400 Missing field: url`; wrong type / bad URL →
  `400 Invalid URL: …` with the reason.
- Redirect responses carry an empty body (`Content-Length: 0`), as in
  the page's Step 2 example.
- `Content-Length` is honoured on POST; a body that cannot be read
  (missing length) is treated as empty and fails validation as
  invalid JSON rather than hanging.
- Query strings are ignored: `GET /<key>?anything` redirects on the
  path's key. A key containing `/` (e.g. `/a/b`) is not a single key
  and returns 404.

## CLI

```
python3 url_shortener.py [port]     # default port 8080
```

`create_server(port)` is importable so tests can bind an ephemeral
port (`port=0`) and drive the server over real HTTP. The module runs
only under `if __name__ == "__main__"`, so importing it never starts
a server.

## Deliberate divergences from the page's examples

1. **404 body length.** The page shows `content-length: 15` for
   `URL not found`, but that string is 13 bytes. The body is returned
   verbatim as `URL not found`; the header therefore says 13, not 15.
   The page's own example text is followed, not its arithmetic.
2. **No GUI, no CI/CD.** Both Step 4s are labelled optional on the
   page; per "minimum code, nothing speculative" they are omitted.
3. **In-memory only.** The page suggests a database/Redis for a
   deployed service but explicitly used an in-memory store itself;
   persistence is out of scope for this build and documented in README.

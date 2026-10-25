# url-shortener — Build Your Own URL Shortener

Coding Challenges #12, in `somecoolprojects/`. Docs first, then code —
see `docs/`.

An HTTP service (Python 3 standard library only, single file
`url_shortener.py`) that creates short codes for URLs, redirects short
codes to the originals, and deletes them. Storage is in-memory: a
restart loses all mappings.

## Run

```sh
python3 url_shortener.py          # serves on http://localhost:8080
python3 url_shortener.py 8000     # or another port
```

## API

Create (idempotent — posting the same URL twice returns the same key):

```sh
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.example.com"}'
# {"key": "Y3S9wb", "long_url": "https://www.example.com",
#  "short_url": "http://localhost:8080/Y3S9wb"}
```

Redirect (302) and unknown key (404):

```sh
curl http://localhost:8080/Y3S9wb -i
# HTTP/1.1 302 Found
# Location: https://www.example.com

curl http://localhost:8080/nope -i
# HTTP/1.1 404 Not Found
# URL not found
```

Delete (200, empty body; deleting an unknown key is a no-op):

```sh
curl -X DELETE http://localhost:8080/Y3S9wb -i
# HTTP/1.1 200 OK
```

Invalid creates return `400` with a plain-text message, e.g.
`Missing field: url`. Keys are 6 base62 characters derived from
SHA-256 of the URL, with salted re-hashing on collision.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start the real server on an ephemeral port and drive it over
real HTTP (302s observed via `http.client`, since urllib follows
redirects). See `docs/TEST_PLAN.md` for the case list.

## Files

- `url_shortener.py` — HTTP service (create / redirect / delete).
- `docs/SPEC.md` — challenge spec (steps 1–3; GUI and CI/CD steps
  are optional on the challenge page and not built here).
- `docs/DESIGN.md` — assumptions, key generation, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_url_shortener.py` — the test suite.

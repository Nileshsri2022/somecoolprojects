# web-server — Build Your Own Web Server

Coding Challenges #11, worked in `somecoolprojects/`. Docs first,
then code — see `docs/`.

A small static-file HTTP server in Python 3 standard library only
(single file `web_server.py`, threaded). Serves files from a directory
with correct status codes and content types: `GET` serves, `HEAD`
returns headers only, directories serve `index.html` or 404, paths
escaping the root return 403, missing files 404, other methods 405.

## Usage

```sh
python3 web_server.py
python3 web_server.py --port 8000 --directory ./public
python3 web_server.py --host 127.0.0.1 --port 8080 --directory .
```

Defaults: host `127.0.0.1`, port `8080`, directory = current directory.
Then visit e.g. `http://127.0.0.1:8080/` in a browser, or:

```sh
curl -i http://127.0.0.1:8080/index.html
curl -I http://127.0.0.1:8080/style.css
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start a live server on an OS-assigned ephemeral port and make
real HTTP requests: index/root, HTML/CSS/JS/JSON/text/PNG content
types, subdirectory files, directory-without-index 404, missing-file
404, query-string handling, percent-encoded paths, HEAD headers with
no body, POST 405, `..` / encoded-`..` / symlink traversal 403,
unknown-extension fallback, and Content-Length correctness.

## Files

- `web_server.py` — server, handler, CLI.
- `docs/SPEC.md` — challenge spec (see the caveat there: the challenge
  page fetch failed in this session, so the spec is the standard
  static-file behaviour, not a verified quote of the page).
- `docs/DESIGN.md` — assumptions and request flow.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_web_server.py` — the test suite.

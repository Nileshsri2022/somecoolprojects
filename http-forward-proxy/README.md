# http-forward-proxy — Build Your Own HTTP Forward Proxy Server

Coding Challenges #51, worked in `somecoolprojects/`. Docs first,
then code — see `docs/`.

A small forward proxy in Python 3 standard library only (single
file `proxy.py`, threaded). It forwards HTTP requests in absolute
form (`GET http://host/path`) and origin form, strips hop-by-hop
headers, rewrites the target to origin form, adds
`X-Forwarded-For`, relays the origin's response, refuses hosts
listed in `forbidden-hosts.txt` with 403, refuses responses
containing a word from `banned-words.txt` with 403, logs traffic,
and supports `CONNECT` tunnelling for HTTPS (opaque byte pipe —
it never terminates TLS or inspects tunnelled traffic).

## Usage

```sh
python3 proxy.py
python3 proxy.py --host 127.0.0.1 --port 8989
python3 proxy.py --forbidden-hosts forbidden-hosts.txt \
                 --banned-words banned-words.txt \
                 --log-file proxy.log
```

Defaults: host `127.0.0.1`, port `8989` (the page's port), and the
shipped `forbidden-hosts.txt` / `banned-words.txt` (comment-only,
so empty by default). Pass `--forbidden-hosts none` or
`--banned-words none` to disable a list outright. A listed file
that does not exist is treated as an empty list (warning on stderr).

Then, e.g. against a local origin on port 8000:

```sh
curl --proxy "http://127.0.0.1:8989" "http://127.0.0.1:8000/hello"
curl --proxy "http://127.0.0.1:8989" -v "http://facebook.com/"
# -> 403 Website not allowed: facebook.com (if facebook.com is listed)
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests start a local origin and the proxy on ephemeral ports and
make real proxied requests: absolute/origin-form GET, POST echo,
hop-by-hop stripping, `X-Forwarded-For`, forbidden-host 403
(HTTP and CONNECT), banned-word 403, CONNECT tunnelling, 502 on
unreachable origin, 400 on malformed requests, and logging.
No test contacts an external website.

## Files

- `proxy.py` — server, handler, CLI.
- `forbidden-hosts.txt` — sample blocklist (comment-only by default).
- `banned-words.txt` — sample banned-word list (comment-only).
- `docs/SPEC.md` — challenge spec (slug: `challenge-forward-proxy`).
- `docs/DESIGN.md` — assumptions and request flow.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_proxy.py` — the test suite.

## Divergences from the page (documented)

- Step 3's example shows `Content-Length: 43` for the body
  `Website content not allowed.` (28 bytes); this implementation
  sends the correct length, 28.
- One HTTP request per client connection (`Connection: close`
  both sides); the page does not require keep-alive.
- CONNECT tunnels are never inspected, so banned-word checks do
  not apply inside a tunnel — only the CONNECT target's host is
  checked against the forbidden list.

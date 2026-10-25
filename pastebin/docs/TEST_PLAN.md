# Pastebin — Test Plan

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

Tests live in `tests/test_pastebin.py`. They start a real
`ThreadingHTTPServer` on an ephemeral port (`port=0`, OS-assigned) in
a background thread per test class, talk to it over HTTP with
`urllib`, and shut it down in `tearDownClass`. No external hosting,
no fixed ports, no network beyond localhost.

## Cases (each maps to a SPEC step)

1. `test_home_page` — GET `/` returns 200 and contains the submission
   form (Step 1).
2. `test_create_via_form_redirects_and_retrieves` — POST form content
   returns 303 to `/<id>`; GET that URL returns 200 with the content
   (Steps 1–2).
3. `test_create_via_json` — POST JSON returns 201 with an `id` and
   `url`; GET the URL shows the content (Steps 1–2, API form).
4. `test_unknown_id_404` — GET `/nosuchid` and `/nosuchid/raw`
   return 404 (Steps 2–3).
5. `test_delete_flow` — GET `/<id>/delete` shows a confirmation page;
   POST deletes and redirects; GET `/<id>` is then 404; a second
   POST delete is 404 (Step 3, including double-delete).
6. `test_expiry` — a paste with `expiry_seconds=0` is immediately
   404; a never-expiring paste stays retrievable (Step 4).
7. `test_python_highlighting_and_escaping` — a Python paste's page
   wraps `def` in a keyword span and escapes `<script>` to
   `&lt;script&gt;` (Bonus Step 6 + safety).
8. `test_raw_view` — GET `/<id>/raw` returns the exact bytes with
   `text/plain` (Going Further).
9. `test_empty_content_rejected` — POST with empty content returns
   400 and creates nothing (validation).
10. `test_recent_list` — the home page lists a created paste's link
    and no longer lists it after deletion (Going Further: list).

## Manual check (optional, not part of the suite)

```
python3 pastebin.py --port 8080
# open http://127.0.0.1:8080/ , paste text, submit, view, delete.
```

Stop the server with Ctrl-C. No background servers are left running
by the test suite (each server thread is joined on teardown).

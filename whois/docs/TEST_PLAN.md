# TEST_PLAN — Whois

Run from `~/workspace/somecoolprojects/whois/`:

```sh
python3 -m unittest discover -s tests -v
```

## Constraints

- Tests must NEVER contact a real whois server. All network I/O in
  tests goes to local fake servers on ephemeral ports (port 0).
- Fake servers are started in `setUp` and shut down in `tearDown`
  via `server_close()`; no background process is left running and
  no `pkill` is used (servers live in the test process).

## Cases (`tests/test_whois.py`)

1. `query` sends `query + CRLF` and returns the full response:
   fake server records the exact bytes received; response is read
   past the first chunk (multi-chunk response) until EOF.
2. `parse_whois` drops blank lines and `%` comment lines (including
   `%` after leading whitespace).
3. `parse_whois` lower-cases keys, splits on the first colon only
   (URL/timestamp values intact), and collects repeated keys into
   a list in order.
4. `parse_whois` appends a colon-less line to the previous value
   and drops a leading colon-less line.
5. `find_referral` prefers `refer` over `Registrar WHOIS Server`
   when both are present; falls back to the registrar field when
   there is no `refer`; returns `None` when no referral field
   exists; strips a scheme/`:port` suffix.
6. `lookup` follows a two-hop chain (distinct hosts, `refer:` then
   final response; and a registrar-hop chain via
   `Registrar WHOIS Server`): both hops are returned in order and
   hop 2 received the same query. Chain logic is tested with
   `query()` stubbed, because a referral carries no port — two
   real fake servers cannot share one ephemeral port, so a
   fake-server chain cannot exercise distinct hosts; the network
   half of the chain (send CRLF, read to EOF) is covered by the
   fake-server tests in cases 1 and 10.
7. `lookup` with `follow=False` returns only the first hop even
   when a referral is present.
8. `lookup` stops on a referral loop (hop 2 refers back to hop 1's
   server) instead of looping; it also stops at `max_hops`.
9. `lookup` on a refused connection raises `OSError` (fake server
   shut down before the call, or an unused ephemeral port).
10. `main` end-to-end via a fake server: exit code 0, both hops'
    raw text on stdout; `--parsed` prints parsed lines instead;
    no-argument / empty-query invocations exit non-zero.
11. Query validation: queries containing whitespace are rejected
    by `main` (non-zero exit) without opening a connection.

## Manual check (not part of the suite, needs internet)

```sh
python3 whois.py example.com
python3 whois.py 8.8.8.8
```

Expect the IANA response first, then the registry/RIR response.
This is a smoke check only; it is not run by CI or the test suite.

# SMTP Server — Build Your Own SMTP Server (Coding Challenges #66)

A minimal SMTP server in Python 3 (standard library only): a threaded
TCP server speaking enough of RFC 5321 for an SMTP client to deliver
mail — greeting, HELO/EHLO, MAIL FROM, RCPT TO, DATA (with
dot-unstuffing), RSET, NOOP, QUIT — storing accepted messages in
memory and optionally as `.eml` files.

Built from https://codingchallenges.fyi/challenges/challenge-smtp/

## Run

```sh
python3 smtp_server.py                    # listens on 127.0.0.1:2525
python3 smtp_server.py --port 2526 --maildir ./mail
```

Then deliver mail with any SMTP client, e.g. Python:

```python
import smtplib
with smtplib.SMTP("127.0.0.1", 2525) as c:
    c.ehlo()
    c.sendmail("alice@example.com", ["bob@example.com"],
               "Subject: hi\r\n\r\nhello")
```

Notes:

- The default port is **2525, not 25** — binding port 25 needs root.
  Pass `--port 25` when running privileged; the protocol is identical.
- EHLO advertises no extensions (single `250` line); `SIZE=` and
  other ESMTP parameters are rejected with `501`. There is no
  relaying, TLS, authentication, or POP3/IMAP retrieval — this is a
  local receiving server only. See `docs/SPEC.md` for the full list
  of deliberate divergences.

## Tests

```sh
cd smtp-server
python3 -m unittest discover -s tests -v
```

Tests start the server on an ephemeral port and speak raw SMTP plus
`smtplib`; no real mail server is ever contacted.

## Layout

- `smtp_server.py` — the server (session state machine, store, CLI).
- `docs/SPEC.md` — challenge spec, commands, reply codes, divergences.
- `docs/DESIGN.md` — assumptions made before coding.
- `docs/TEST_PLAN.md` — what the tests cover.
- `tests/test_smtp_server.py` — unittest suite.

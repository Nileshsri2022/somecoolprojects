# SPEC — SMTP Server (Coding Challenges, entry 66)

Source: https://codingchallenges.fyi/challenges/challenge-smtp/
(Slug used: `challenge-smtp` — first guess, no 404, no correction needed.)

The challenge builds a simple SMTP server an SMTP client can connect
to and deliver an email to. Its steps, mapped to this implementation:

| Page step | Behaviour |
|---|---|
| Step 0 — setup | Python 3 standard library only, no third-party packages. |
| Step 1 — listen + 220 | TCP server; on connect, sends `220 <host> CC SMTP Server`. |
| Step 2 — HELO/EHLO | `HELO <domain>` and `EHLO <domain>` → `250 <host>`. The page says HELO alone suffices; EHLO is supported as a plain alias (no extensions advertised). |
| Step 3 — mail headers | `MAIL FROM:<reverse-path>` → `250 OK`; `RCPT TO:<forward-path>` (repeatable) → `250 OK`. |
| Step 4 — DATA + transparency | `DATA` → `354 End data with <CR><LF>.<CR><LF>`; message lines are read until a lone `.` line; dot-stuffed lines (`..` at line start) are unstuffed to a single leading dot (RFC 5321 §4.5.2 transparency). On completion → `250 OK: message queued`, and the message is stored. |
| Step 5 — concurrent clients | One thread per connection; the message store is lock-guarded. |

## Commands and reply codes (full set)

| Command | Success | Error |
|---|---|---|
| (connect) | `220 <host> CC SMTP Server` | — |
| `HELO` / `EHLO` | `250 <host>` | `501` if the domain argument is missing |
| `MAIL FROM:` | `250 OK` | `503` if no HELO yet; `501` on malformed address |
| `RCPT TO:` | `250 OK` | `503` if no MAIL yet; `501` on malformed address |
| `DATA` | `354 ...`, then `250 OK: message queued` | `503` if no MAIL/RCPT yet |
| `RSET` | `250 OK` (clears the in-progress envelope only) | — |
| `NOOP` | `250 OK` | — |
| `QUIT` | `221 Bye` (connection then closes) | — |
| anything else | — | `500 Command not recognized` |
| out-of-sequence command | — | `503 Bad sequence of commands` |

All commands are case-insensitive. Address parsing accepts the
RFC 5321 forms `<addr@example.com>`, `<>` (null reverse-path, MAIL
only), and a bare `addr@example.com` without brackets. Parameters
after the address (e.g. `MAIL FROM:<a@b> SIZE=123`) are rejected
with `501` — see Divergences. An address must contain exactly one
`@` with non-empty local and domain parts.

## Message storage

A stored message records: `mail_from`, `rcpt_tos` (list, in order),
and `data` (the full DATA content as received, after dot-unstuffing,
with lines joined by `\n`; the terminating `.` line is not stored).

- Default: in-memory list, accessible in-process via
  `SMTPServer.messages` (thread-safe snapshot via `get_messages()`).
- `--maildir <dir>`: in addition to memory, each accepted message is
  also written as one file `<dir>/<n>.eml` (n = 1-based arrival
  order), containing `From:`, `To:` header lines followed by the
  DATA content. This is the page's "Going Further" storage option,
  kept minimal: no POP3/IMAP access is provided.

## Success criteria (verifiable)

1. A real stdlib `smtplib` client can `ehlo()`, `sendmail()`, and
   `quit()` against the server, and the message appears in the store
   with the right sender, recipients, and body.
2. Raw-socket sessions reproduce the page's steps: 220 greeting,
   HELO, MAIL FROM, RCPT TO, DATA with dot-stuffing, RSET, QUIT.
3. Two clients sending simultaneously both land in the store.
4. `python3 -m unittest discover -s tests -v` passes.

## Divergences from the page / RFC 5321 (deliberate, minimal)

1. **Default port 2525, not 25.** The page says port 25, but binding
   it needs root. `--port 25` works when run privileged; the protocol
   is identical. Default host is `127.0.0.1` (loopback only) rather
   than all interfaces, for safety.
2. **EHLO advertises no extensions.** It returns a single `250`
   line, not a multiline capability list. Clients needing no
   extensions (including `smtplib`) work unchanged.
3. **No `SIZE=` / other ESMTP parameters, no `VRFY`, no TLS, no
   authentication, no relaying/delivery.** This is a local
   receiving server only, per the page's scope; unknown commands
   get `500`, and address parameters get `501`.
4. **No address validation beyond shape.** Any syntactically
   plausible address is accepted; there is no DNS or mailbox check.
   All recipients are treated as local.
5. **Line endings normalised.** DATA content is stored with `\n`
   line endings regardless of whether the client sent CRLF or LF.
   A lone-LF client is tolerated (strict CRLF-only is not enforced).
6. **No POP3/IMAP retrieval.** The "Going Further" suggestion is
   implemented only as maildir file storage, not as a retrieval
   protocol.

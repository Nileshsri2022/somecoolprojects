# DESIGN — SMTP Server

## Assumptions (stated before coding)

1. Single file, Python 3 stdlib only: `socketserver.ThreadingTCPServer`
   for concurrency (page Step 5), plus `threading.Lock` for the store.
   No `smtpd`/`aiosmtpd` — the point of the challenge is implementing
   the protocol, and those modules would do it for us
   (`smtpd` is also removed in Python 3.12).
2. One thread per connection, one small state machine per session:
   `greeted -> helo -> mail -> rcpt -> data`. State lives on the
   handler, never in globals, so concurrent sessions cannot corrupt
   each other's envelopes.
3. The wire is line-based. `socket.makefile("rwb")` gives buffered
   readline/write; lines are decoded as UTF-8 with `errors="replace"`
   so a stray byte cannot kill a session. SMTP commands are ASCII
   in practice; message bodies are stored as text.
4. The store is the only shared mutable state, guarded by one lock.
   `get_messages()` returns a copy, so callers cannot mutate it.
5. The CLI is a thin wrapper: parse `--host/--port/--maildir`, build
   the server, `serve_forever()`. Tests import the module and start
   the server in a thread on port 0 (ephemeral), so tests never need
   a fixed port or root.
6. No delivery, no DNS, no auth: anything accepted is stored. This
   keeps the code to what the page asks for (receive + store) and
   nothing speculative.

## Structure (`smtp_server.py`)

- `Message` — dataclass: `mail_from`, `rcpt_tos`, `data`.
- `parse_address(arg)` — strips `<>`, validates shape, returns the
  address or raises `ValueError`. Shared by MAIL and RCPT.
- `SMTPServer(socketserver.ThreadingTCPServer)` — holds `messages`,
  `lock`, optional `maildir`; `store_message()` appends + writes the
  `.eml` file when a maildir is configured. `daemon_threads = True`
  so a stray client cannot hang shutdown.
- `SMTPHandler(socketserver.StreamRequestHandler)` — `handle()` sends
  the 220 greeting, then loops: read line, dispatch command, write
  reply. `handle_data()` reads until the lone `.` line, unstuffing
  leading `..` → `.`.
- `main()` — argparse + serve. `allow_reuse_address = True` for
  quick restarts during development.

## Reply-code choices

- `500` for unrecognised commands (RFC: syntax error, command
  unrecognized), `501` for recognised commands with bad arguments,
  `503` for correct commands in the wrong order. These are the
  standard RFC 5321 codes and the ones `smtplib` maps to
  `SMTPException` subclasses, so a misbehaving client fails loudly
  rather than silently.

## What was deliberately NOT built

- ESMTP extensions (SIZE, 8BITMIME, STARTTLS, AUTH), VRFY/EXPN,
  relaying, queueing/retries, POP3/IMAP, MIME parsing. Each would
  be speculative scope beyond the page's five steps; the maildir
  hook is the only "Going Further" piece, and it is file storage
  only.

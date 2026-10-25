# DESIGN — irc-client

Assumptions stated before coding (ponytail: think before
coding, minimum code, nothing speculative).

## Layout

Single file, Python 3 standard library only:

- `irc_client.py` — message parser, client state machine,
  socket loop, CLI.
- `tests/test_irc_client.py` — unittest, plus a fake server.

## Message model

`parse_message(line)` returns a `Message` dataclass:

- `prefix`: str | None — everything after the leading `:`
  up to the first space, or None.
- `command`: str — the command or numeric reply, uppercased
  on output only where the client generates it; parsing keeps
  the server's spelling (numerics are digits, commands are
  already uppercase in practice).
- `params`: list[str] — middle parameters plus the trailing
  parameter (with its leading `:` stripped) as the last item.

Parsing rules: strip one trailing `\r\n` (tolerate a bare
`\n`); if the line starts with `:`, the first token is the
prefix; then split on spaces, and once a token starts with
`:`, the rest of the line (minus that `:`) is one trailing
parameter. Empty lines produce no message and are ignored.

`nick_of(prefix)` returns the part before `!` (or the whole
prefix if there is no `!`); a server name has no `!`, so it
is returned as-is and only used for display of server
notices, never as a chat nick.

## Client state

`IRCClient` holds only what the challenge needs:

- `nick`, `username`, `realname`, `host`, `port`
- `current_channel`: str | None — the one channel assumed
  by the challenge; set on our own JOIN echo, cleared on
  our own PART echo.
- `registered`: bool — set on numeric `001`.
- `pending_channel`: str | None — a `--channel` given on the
  command line; joined automatically when `001` arrives, so
  the client never JOINs before registration.
- `display`: callable(str) — defaults to `print`; tests pass
  a list-appending function so display output is assertable
  without capturing stdout.
- `_buffer`: bytes — partial line accumulation, so a TCP
  segment split mid-line still yields whole messages.

## Handling a server line

`handle_line(line)` parses the line, updates state, returns
a list of raw lines to send back (usually empty, or one
`PONG`), and calls `display()` for human-readable output:

| Incoming | Outgoing | Display |
|---|---|---|
| `PING :token` | `PONG :token` | none (protocol noise) |
| `001 ...` | `JOIN <pending>` if set | the welcome text |
| `002/003/004`, MOTD numerics | — | the trailing text |
| `NOTICE` | — | `* <text>` for server notices, `Nick: <text>` otherwise |
| `353` (NAMES) | — | `Users on #cc: @CCIRC ...` |
| `366` (end of NAMES) | — | none (covered by 353) |
| `JOIN` (self) | — | `You joined #cc`, sets channel |
| `JOIN` (other) | — | `Nick joined #cc` |
| `PART` (self) | — | `You left #cc`, clears channel |
| `PART` (other) | — | `Nick left #cc` (+ reason if given) |
| `NICK` (self) | — | `Old is now known as New`, updates nick |
| `NICK` (other) | — | same translation |
| `PRIVMSG` to channel/our nick | — | `Nick: text` |
| `QUIT` | — | `Nick has left IRC <reason>` |
| `MODE`, other numerics | — | raw line (not hidden, not translated) |
| `433` (nick in use) | — | `Nickname <nick> is already in use` |
| `ERROR` | — | `Error: <text>` |

Unknown commands are displayed raw rather than dropped, so
nothing from the server is silently lost. Nothing else is
translated: inventing translations for commands the challenge
does not mention would be speculative.

## Handling user input

`handle_user_input(text)` returns `(outgoing, error)` where
exactly one is non-empty:

- `/join #cc` → `JOIN #cc` (channel must start with `#` or
  `&`; anything else is an error, not sent).
- `/part` → `PART <current>`; error if not on a channel.
- `/nick NewNick` → `NICK NewNick`.
- `/quit [message]` → `QUIT :message` (or bare `QUIT` with
  no message).
- Any other `/command` → error `Unknown command: ...` (not
  forwarded raw — forwarding arbitrary user text as protocol
  would let a typo send a malformed command).
- Plain text → `PRIVMSG <current> :text`; error if not on a
  channel. Empty input is a no-op.

## Sending

`send_line(line)` appends `\r\n`, encodes UTF-8 with
`errors="replace"`, and sends via `sendall` on the socket
(or via an injected callable in tests). Outgoing lines are
never built with user text in the command position.

## Network loop

`connect()` opens the socket (`socket.create_connection`,
10 s timeout), sends `NICK` then `USER` (`USER <user> 0 *
:<realname>`), and starts a receiver thread that feeds
received bytes through `feed_bytes()` and dispatches each
complete line through `handle_line()`, sending any replies.
The main thread reads stdin lines and dispatches them
through `handle_user_input()`; `/quit` (or EOF / Ctrl-C)
sends `QUIT`, stops the receiver, and closes the socket.
No reconnection: a dropped connection ends the program with
a message, matching the challenge's scope.

## Deliberate divergences from the challenge page

1. **QUIT spelling.** The page's Step 6 shows `QUIT:
   message` (colon attached to the command). That is not a
   valid IRC message: the trailing parameter must be
   separated by a space (`QUIT :message`). This client sends
   the valid form and parses both on receipt.
2. **Challenge URL.** The brief's URL
   `.../challenge-irc-client/` 404s; the live page is
   `.../challenge-irc/`, read directly on 2026-10-25
   during reconciliation. Its steps 1–6 match the
   behaviour above (register → PING/PONG → JOIN/PART →
   NICK → PRIVMSG → QUIT, one channel), and the tests
   pin it.
3. **No public network in tests.** The page's original
   example host was freenode (`irc.freenode.net:6667`),
   which no longer exists in that form. The client
   therefore takes host/port arguments and defaults to
   `127.0.0.1:6667` for local testing; tests use only
   the in-process fake server and contact no public
   network.
4. **Auto-join after 001, not immediately.** Sending JOIN
   before registration is rejected by some servers; joining
   on `001` when `--channel` is given is the conservative
   equivalent of the user typing `/join` right after
   connecting.

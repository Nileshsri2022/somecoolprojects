# TEST_PLAN — irc-client

All tests are `unittest`, run from `irc-client/` with:

```
python3 -m unittest discover -s tests -v
```

No public network, no hard-coded ports: the fake server
binds `127.0.0.1` port `0` (ephemeral) and the client is
given the assigned port. Fake-server threads are daemon
threads and are shut down in `tearDown`; nothing is left
listening after the suite.

## Unit tests (parser + state machine, no sockets)

1. Parse a plain command: `PING :token` → prefix None,
   command PING, params ["token"].
2. Parse a prefixed numeric: the page's Step 2 welcome
   `:*.freenode.net 002 CCIRC :Your host is ...` → prefix,
   command `002`, params `["CCIRC", "Your host is ..."]`.
3. Parse a NOTICE: `:*.freenode.net NOTICE * :* Looking up
   your ident...` → params `["*", "* Looking up your
   ident..."]`.
4. Parse every Step 3 test case verbatim (353, NOTICE,
   MODE, JOIN, PART, NICK) and assert prefix / command /
   params for each.
5. Parse a PRIVMSG with colons inside the text — the text
   after the first ` :` stays whole, including later `:`s.
6. Empty line → None (ignored, no crash).
7. `nick_of`: `JohnC!~JohnC@host` → `JohnC`; a bare server
   name stays whole.
8. PING handling: `handle_line("PING :abc")` returns
   `["PONG :abc"]` and displays nothing.
9. Own JOIN echo sets `current_channel` and displays
   `You joined #cc`; other JOIN displays `Nick joined #cc`
   and does not change the channel.
10. Own PART echo clears `current_channel`; other PART
    displays nick + reason when a reason is present.
11. NICK: own change updates `self.nick` and displays
    `Old is now known as New`; another user's change
    displays the same translation without touching our nick.
12. PRIVMSG display: channel message → `JohnC: Hi There!`;
    private message to our nick → same form.
13. QUIT display: `JohnC has left IRC Quit: Bye bye!`.
14. 353 NAMES display lists the names; 433 displays the
    nick-in-use error.
15. Partial-line buffering: feeding `PING :to` then `ken\r\n`
    yields exactly one PONG, for `token`.

## User-input tests (no sockets)

16. `/join #cc` → `JOIN #cc`; `/join cc` (no `#`) → error,
    nothing sent.
17. `/part` with a channel → `PART #cc`; without one →
    error, nothing sent.
18. `/nick JohnC` → `NICK JohnC`.
19. `/quit Bye bye!` → `QUIT :Bye bye!`; bare `/quit` →
    `QUIT`.
20. Plain text on a channel → `PRIVMSG #cc :text`; plain
    text with no channel → error, nothing sent.
21. Unknown `/bogus` → error, nothing sent; empty input →
    nothing at all.

## Integration tests (fake server, ephemeral port)

22. Full session: fake server reads `NICK`/`USER`, sends
    `001` + `002` + `NOTICE` + `PING`; client answers `PONG`,
    joins on `/join`, receives a channel PRIVMSG from
    another user, sends its own PRIVMSG, then `/quit`.
    Assert every line the server received, in order, and
    the client's displayed lines.
23. Auto-join: a client constructed with a pending channel
    sends `JOIN #cc` immediately after receiving `001`,
    without any user input.

## Manual check (not part of the suite)

Run two clients against a local fake server by hand is not
needed: test 22 covers the same path end to end. A real
public network is never used for verification.

## Success criteria

Every test passes; no test binds a fixed port, contacts a
public host, or leaves a thread/server running after
`tearDown`.

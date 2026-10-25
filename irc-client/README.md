# irc-client — Build Your Own IRC Client

Coding Challenges #16, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A minimal raw-socket IRC client (Python 3 standard library
only, subset of RFC 2812): connect, register with
NICK/USER, answer PING with PONG, join/part one channel,
change nick, send/receive PRIVMSG, and quit politely.
No public network is used: point it at any server you run,
or at the fake server used by the tests.

## Usage

```sh
python3 irc_client.py --host 127.0.0.1 --port 6667 --nick CCClient --channel '#cc'
```

Defaults: host `127.0.0.1`, port `6667`, nick `CCClient`,
user `guest`, real name `Coding Challenges Client`.
`--channel` joins that channel automatically once the
server's `001` welcome arrives; otherwise type `/join`.

Once connected, type:

```
/join #cc     join a channel
/part         leave the current channel
/nick NewNick change nickname
/quit [msg]   leave IRC
<text>        send <text> to the current channel
```

Incoming messages are shown translated, e.g.
`JohnC: Hi There!`, `JohnC is now known as CCTest2`,
`JohnC has left IRC Quit: Bye bye!`. Plain text sent
while not on a channel is refused with an error, not sent.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use a small in-process fake IRC server on an
ephemeral localhost port — no public network, no
hard-coded ports. They cover the parser (including the
challenge's Step 3 test cases verbatim), PING/PONG,
JOIN/PART/NICK/PRIVMSG/QUIT handling, user-input
commands, partial-line buffering, auto-join on `001`,
and a full session against the fake server.

## Files

- `irc_client.py` — parser, client state machine, socket loop, CLI.
- `docs/SPEC.md` — challenge spec and required messages.
- `docs/DESIGN.md` — assumptions and deliberate divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_irc_client.py` — the test suite.

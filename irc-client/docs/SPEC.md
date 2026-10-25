# SPEC — Build Your Own IRC Client (Coding Challenges #16)

Source: Coding Challenges, "Build Your Own IRC Client"
(John Crickett). The challenge page is a subset of RFC 2812
(Internet Relay Chat: Client Protocol); RFC 2813 covers the
server–server protocol and is out of scope here.

Note on the challenge URL: the URL in the task brief,
`https://codingchallenges.fyi/challenges/challenge-irc-client/`,
returned "not found" when fetched. A web search for the
challenge found the live page under the slug `challenge-irc`
(`codingchallenges.fyi/challenges/challenge-irc/`), and the
page body was read directly on 2026-10-25 during
reconciliation (wave 1 caveat). Steps 1–6 below match that
page: connect + NICK/USER, welcome + PING/PONG, JOIN/PART
with the page's test cases, nick changes, PRIVMSG, QUIT.

## Protocol basics

- Transport: TCP. One IRC message per line, terminated by
  CRLF (`\r\n`). Messages are at most 512 bytes including CRLF.
- Message shape: `[:prefix] command params... [:trailing]`.
  The prefix (when present) is a server name or a
  `nick!user@host` mask. The trailing parameter, introduced by
  a `:` after a space, may contain spaces.
- The client never connects to a public network in this repo:
  all tests run against a small in-process fake server on an
  ephemeral localhost port. The original challenge used
  freenode (`irc.freenode.net`, port 6667); that network no
  longer exists in that form, and this client takes the host
  and port as arguments so any server can be used.

## Step 1 — Connect and register

Open a TCP connection to the server, then send exactly two
registration messages:

```
NICK CCClient
USER guest 0 * :Coding Challenges Client
```

(Nickname and real name are configurable in this client;
`CCClient` / `Coding Challenges Client` are the challenge's
examples.) Read back and print the server's replies.

## Step 2 — Welcome messages and PING

Parse the welcome / MOTD replies. The two shapes the page
calls out:

```
:*.freenode.net 002 CCIRC :Your host is *.freenode.net, running version InspIRCd-3
:*.freenode.net NOTICE * :* Looking up your ident...
```

i.e. a numeric reply (`002`, and in general `001`–`004` and
the MOTD numerics) and a `NOTICE`. If the server sends
`PING`, the client MUST answer `PONG` with the same token,
or the server will drop the connection ("Ping Timeout"):

```
PING :server.name  ->  PONG :server.name
```

## Step 3 — Join and leave a channel

Parse `JOIN` and `PART` messages from the server, and the
replies that surround a join. The page's test cases:

```
:*.freenode.net 353 CCIRC = #cc :@CCIRC
:*.freenode.net NOTICE CCIRC :*** Ident lookup timed out, using ~guest instead.
:CCIRC!~guest@freenode-kge.qup.pic9tt.IP MODE CCIRC :+wRix
:CCIRC!~guest@freenode-kge.qup.pic9tt.IP JOIN :#cc
:CCIRC!~guest@freenode-kge.qup.pic9tt.IP PART :#cc
:Guest4454!~guest@freenode-kge.qup.pic9tt.IP NICK :JohnC
```

From each message extract origin, command, optional target,
and parameter. User commands:

```
 /join #cc   ->  JOIN #cc
 /part       ->  PART #cc   (the channel currently joined)
```

Track which channel the client is on. The challenge assumes
the user joins only one channel at a time.

## Step 4 — Nick changes

User command `/nick NewNickname` sends `NICK NewNickname`.
When the server echoes a nick change, present a human
translation, for self and for other users on the channel:

```
:JohnC!~JohnC@... NICK :CCTest2   ->   JohnC is now known as CCTest2
```

## Step 5 — Send and receive channel messages

Anything the user types that is not prefixed with `/` is
chat for the current channel. If the user is not on a
channel, do not send it; report an error instead.

```
PRIVMSG #cc :Hi everyone! How are you all?
```

An incoming channel message is presented translated:

```
:JohnC!~JohnC@... PRIVMSG #cc :Hi There!   ->   JohnC: Hi There!
```

The same display rule applies to a private message addressed
to our own nick.

## Step 6 — Leave politely

User command `/quit message` (message optional) tells the
server the user is leaving. Other clients see something like:

```
:JohnC!~JohnC@... QUIT :Quit: Bye bye!   ->   JohnC has left IRC Quit: Bye bye!
```

This client sends `QUIT :message` (see DESIGN.md for why the
page's literal `QUIT: message` spelling is not used).

## Out of scope

Multiple channels at once, channel keys, TLS, SASL/NickServ
auth, CTCP, DCC, IRCv3 capabilities, reconnection, and any
GUI. One channel, plain TCP, one nick — the lightweight
client the challenge asks for.

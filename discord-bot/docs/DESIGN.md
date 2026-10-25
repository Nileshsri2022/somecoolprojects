# DESIGN — discord-bot

Assumptions stated before coding (ponytail: think before
coding, simplicity first, minimum code, nothing speculative).

## Layout

Single file, Python 3 standard library only:

- `discord_bot.py` — gateway framing, gateway client,
  REST request builder, command dispatcher, challenge
  catalogue, CLI.
- `challenges.json` — seed catalogue (one entry, see below).
- `tests/test_discord_bot.py` — unittest, plus a fake
  gateway over a real `socketpair` and a fake REST sender.

## Choice: minimal gateway framing over stdlib sockets

Discord's Gateway is a WebSocket API, and the standard
library has no WebSocket client. Two options were weighed:

1. A testable event-dispatch core only, with no wire code.
2. A minimal WebSocket framing layer over `socket` + `ssl`
   (handshake + masked client frames + unmasked server
   frame parsing), plus the dispatch core on top.

Option 2 was chosen: it is still small (~100 lines of
framing), it makes the Identify/Heartbeat/Dispatch logic
exercisable end-to-end against a fake gateway in tests,
and it is what a real run actually needs. It is NOT a
general WebSocket library: it supports only what the
gateway needs — single text frames, fragmented text frames
(reassembled), ping → pong, close, and payload lengths
< 126, 126 (16-bit) and 127 (64-bit). Binary frames are
ignored; control-frame payloads are capped by the parser
only in the sense that absurd lengths raise `ValueError`
before allocation of the payload itself is attempted on a
frame header claiming more than 16 MiB (a safety bound,
not a protocol feature).

## Gateway protocol subset

Opcodes (Discord Gateway v10, JSON encoding):

- 0 Dispatch — `t` is the event name, `s` the sequence
  number (stored for Resume), `d` the event payload.
- 1 Heartbeat (server → client: send a heartbeat now).
- 2 Identify — client → server, after Hello.
- 6 Resume — client → server when a previous `session_id`
  and sequence number exist.
- 7 Reconnect — server → client: reconnect (and Resume).
- 9 Invalid Session — server → client: re-Identify
  (after a short wait; `d=false` means do not Resume).
- 10 Hello — `d.heartbeat_interval` (ms) starts heartbeats.
- 11 Heartbeat ACK — clears the "ack pending" flag.

Intents sent in Identify: GUILDS (1<<0) | GUILD_MESSAGES
(1<<9) | MESSAGE_CONTENT (1<<15) = 33281. MESSAGE_CONTENT
is required for Step 1/Step 2 commands to see message
text at all (this is the intent Step Zero tells you to
enable in the portal).

Heartbeat rules: first heartbeat is sent immediately after
Hello (Discord allows a small jitter; this build sends at
once — simpler and within spec), then every
`heartbeat_interval`. If an ACK has not arrived by the
time the next heartbeat is due, the connection is treated
as dead and the client asks to reconnect. `should_heartbeat`
is a pure function of (now, last heartbeat, interval) so
it is unit-testable without sleeping.

Reconnect/backoff: `backoff_seconds(attempt)` =
`min(30, 2 ** attempt)` seconds (attempt 0 → 1 s). This is
a local policy, not a Discord-mandated value; Discord
mandates only that reconnects use Resume where possible
and respect rate limits. Session state (session_id,
sequence) is kept on the client object so a reconnect can
Resume instead of re-Identifying from scratch.

## Message handling

`handle_message(event)` takes a MESSAGE_CREATE payload
(dict) and returns the reply string or `None`:

- Ignore if `author.bot` is true, or `author.id` equals
  the bot's own id (when known) — prevents self-replies.
- Ignore messages with no string `content`.
- `Hello` match: `content.strip().lower() == "hello"` →
  `Hello, {author.username}!`. The author's `username`
  (not the nickname/global name) is used because that is
  the field MESSAGE_CREATE always carries.
- Commands: content starting with `!`, split on
  whitespace; command word lowercased, so `!QUOTE` works.
  Only the first token is the command; `!add` takes the
  rest of the message (re-joined) as its single argument,
  so URLs are not split.
- Unknown `!`-commands return `None` (silently ignored)
  rather than an error reply, to avoid spamming a channel
  on every typo.
- `!help` is a small extra beyond the page: it lists the
  five page commands. It costs one branch and makes the
  bot discoverable; it changes no page behaviour.

## Quote fetching

`fetch_quote(fetcher)` calls the injectable `fetcher(url)`
(which defaults to a `urllib` GET returning parsed JSON)
against `https://dummyjson.com/quotes/random` and formats
`"quote" — author`. Missing fields raise `ValueError`,
which the dispatcher turns into a polite failure reply
instead of crashing the gateway loop. The default fetcher
is never invoked in tests.

## Challenge catalogue

`ChallengeCatalogue(path)` holds a list of
`{"title": ..., "url": ...}` dicts:

- `load()`: missing file → empty list; corrupt JSON or a
  non-list document → empty list (the file is NOT
  overwritten until the next successful `!add`, so a
  corrupt file is never silently clobbered on startup).
- `random_challenge(rng)`: `rng.choice`, defaulting to
  the `random` module; injectable for deterministic tests.
- `add(url, title_fetcher)`: validates, fetches the
  title, appends, saves. Duplicate URLs are rejected
  with a "already listed" reply (a small guard against
  `!list` filling with repeats).
- `save()`: atomic-ish write (temp file + `os.replace`)
  so a crash mid-write does not leave a half file.

URL validation (`is_valid_challenge_url`):

- scheme must be `http` or `https`;
- host must be exactly `codingchallenges.fyi` or
  `www.codingchallenges.fyi` (no subdomains, so
  `evilcodingchallenges.fyi` and `codingchallenges.fyi.evil`
  both fail — this is checked on the parsed netloc, not
  with a substring test);
- path must start with `/challenges/challenge-` and
  contain no query-string trickery beyond the path
  itself (query/fragment are ignored for the check,
  matching how a browser would resolve the link).

Title extraction (`extract_title(html)`): first
`<title>...</title>`, HTML entities unescaped, the
suffix ` | Coding Challenges` stripped when present,
whitespace collapsed. If no title tag is found,
`ValueError` → the dispatcher replies that the title
could not be read.

Seed catalogue (`challenges.json`): exactly one entry —
the Discord challenge itself, whose title and URL were
verified against the page read for this build
(`Build Your Own Discord Bot`,
`https://codingchallenges.fyi/challenges/challenge-discord/`).
Other entries are deliberately NOT invented: the page's
Dropbox catalogue link was not fetched (its contents
could not be verified from the page text alone), and the
user grows the list with `!add` or by editing the JSON.

## REST

`build_send_request(channel_id, content, token)` returns
a `urllib.request.Request` for
`POST https://discord.com/api/v10/channels/{id}/messages`
with `Authorization: Bot <token>` and a JSON body
`{"content": content}`. `send_message(...)` performs it
via an injectable `urlopen` (tests capture the request
and never hit the network). Discord's 2000-character
message limit is enforced client-side: over-long replies
raise `ValueError` before any request is built.

## CLI / live run

`python3 discord_bot.py [--catalogue FILE] [--gateway-url URL]`
reads the token from the `DISCORD_BOT_TOKEN` environment
variable ONLY. No token argument, no token file, no
hardcoded token anywhere in this project (grep for the
placeholder name finds only the env-var reference and
docs). Missing token → stderr message + exit code 2,
and the token value is never printed. The CLI loop:
connect → TLS → WebSocket handshake → wait for Hello →
Identify (or Resume) → loop `step()` until the socket
closes or a reconnect is requested, then reconnect with
backoff. Live testing therefore needs the user's own bot
token and their own invited test server (Step Zero).

## Divergences from the page (complete list)

1. Step 5 (24/7 hosting) is documented, not automated —
   provisioning a host is outside a stdlib bot program.
2. `!help` added (one branch, documented above).
3. Duplicate `!add` URLs rejected (page is silent).
4. Unknown `!`-commands silently ignored (page is silent).
5. Gateway jitter before the first heartbeat omitted
   (send immediately; within spec, simpler).
6. The Dropbox back-catalogue was not imported; the seed
   catalogue holds only the one verified entry.

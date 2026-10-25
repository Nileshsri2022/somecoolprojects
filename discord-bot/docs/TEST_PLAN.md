# TEST_PLAN — discord-bot

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

No test makes a network call to discord.com, dummyjson.com,
or any other host. Network-shaped tests use either pure
in-memory fakes or a real `socketpair` between the client
under test and a fake gateway thread in the same process.

## Cases

WebSocket framing (`ws_encode_frame`, `FrameParser`):

- Small text frame round-trips (masked client frame decodes
  to the same payload and opcode).
- 16-bit length frame (>125 bytes) round-trips.
- 64-bit length frame (>65535 bytes) round-trips.
- Fragmented text frames reassemble into one message.
- Ping frame is reported as opcode 9 (caller turns it
  into a pong); close frame as opcode 8.
- Truncated/incomplete bytes yield no message until the
  rest arrives; a frame header claiming >16 MiB raises
  `ValueError` instead of allocating.

Gateway payloads:

- `identify_payload` carries token (passed in, never
  defaulted), intents 33281, and v10-compatible properties.
- `resume_payload` carries token, session_id, sequence.
- `heartbeat_payload` carries the current sequence (or
  null when none seen yet).

Heartbeat / reconnect:

- `should_heartbeat` false before the interval elapses,
  true at/after it; `backoff_seconds` is 1, 2, 4, … capped
  at 30.
- Handling op 10 stores the interval and marks a heartbeat
  due; op 11 clears ack-pending; op 1 requests an immediate
  heartbeat; op 7 sets reconnect-requested; op 9 with
  `d=false` clears session state (re-Identify, not Resume).

Dispatch / commands (`handle_message`, `Dispatcher`):

- `Hello` (any case, padded) → `Hello, <username>!`;
  `Hello there` is not a greeting → no reply.
- Bot-authored messages and own-id messages ignored.
- `!quote` with a fake fetcher → `"..." — author`;
  fetcher failure → polite failure reply, not an exception.
- `!challenge` with a seeded rng → deterministic entry;
  empty catalogue → "no challenges" reply.
- `!list` formats a numbered list; empty → "No challenges
  yet." reply.
- `!add` with no argument → usage reply; with a non-
  codingchallenges.fyi URL, a wrong-host URL, a
  substring-spoof host, and a non-challenge path →
  invalid-URL reply each; with a valid URL and a fake
  title fetcher → success reply and the entry is saved;
  re-adding the same URL → "already listed" reply.
- Unknown `!`-command → no reply; `!help` lists commands.
- `extract_title` strips the ` | Coding Challenges`
  suffix and unescapes entities; missing `<title>` raises.

Catalogue persistence:

- Missing file loads as empty; corrupt JSON loads as
  empty; `add` + reload round-trips the new entry
  (tmp directory, real files, no network).

REST:

- `build_send_request` targets the v10 channel-messages
  endpoint, uses `Authorization: Bot <token>`, and sends
  `{"content": ...}` as JSON; content over 2000 chars
  raises before any request is built.
- `send_message` with a fake `urlopen` captures exactly
  that request and returns the parsed JSON response.

End-to-end over a real socketpair:

- A fake gateway thread sends a masked/unmasked Hello
  frame, reads the client's Identify frame, then sends a
  MESSAGE_CREATE dispatch for `Hello`; the client replies
  through a fake REST sender with `Hello, <name>!`.
- The same harness sends op 7 (Reconnect) and the client
  reports reconnect-requested.

CLI:

- Missing `DISCORD_BOT_TOKEN` → exit code 2 and no token
  text on stderr (the env var is set to empty in the test).

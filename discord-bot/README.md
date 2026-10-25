# discord-bot — Build Your Own Discord Bot

Coding Challenges #20, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A Python 3 standard-library-only Discord bot implementing the
challenge steps: it connects to the Discord Gateway
(WebSocket, minimal framing over stdlib sockets), listens for
messages, and replies to `Hello`, `!quote`, `!challenge`,
`!list`, and `!add <challenge URL>` (plus a small `!help`).

## Usage (live — needs your own bot)

Live setup is the page's Step Zero, done by you in the
Discord Developer Portal (this code creates nothing there):

1. Create an application, add a bot user, and copy its token
   somewhere safe. **Never put the token in code, a file, or
   a chat message.** This project reads it only from the
   environment variable `DISCORD_BOT_TOKEN`.
2. Enable the **MESSAGE CONTENT INTENT** for the bot, or it
   will not see message text.
3. Generate an OAuth2 invite URL (bot scope, Send Messages
   permission) and invite the bot to a private test server.

Then run:

```sh
DISCORD_BOT_TOKEN=<your-own-token> python3 discord_bot.py
# optional: --catalogue challenges.json --gateway-url <url>
```

Without the variable set, the bot exits with code 2 and
prints only the variable name — never a token value.

Commands (in any channel the bot can read):

```text
Hello                                  -> Hello, <username>!
!quote                                 -> "quote" — author (dummyJSON)
!challenge                             -> random catalogue entry
!list                                  -> numbered catalogue
!add https://codingchallenges.fyi/challenges/challenge-.../
                                       -> validates the URL, reads the
                                          page <title>, saves the entry
!help                                  -> command list
```

Messages from bots (including itself) are ignored, so the
bot cannot reply to its own replies. Unknown `!`-commands
are silently ignored.

The seed catalogue (`challenges.json`) holds one verified
entry — the Discord challenge itself. Grow it with `!add`
or by editing the JSON; additions are saved to disk on
`!add` and survive restarts.

## Step 5 — hosting (not automated)

The page's final step (run 24/7/365) needs a host you
provision yourself, e.g. a small VPS/EC2 instance. Once you
have one, run the bot as a service so it survives logout
and restarts on boot, e.g. a systemd unit along these lines
(adjust paths/user; the token comes from the service's
environment, not the unit file if you prefer):

```ini
[Unit]
Description=discord-bot
After=network-online.target

[Service]
User=discordbot
WorkingDirectory=/home/discordbot/discord-bot
Environment=DISCORD_BOT_TOKEN=<your-own-token>
ExecStart=/usr/bin/python3 discord_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

30 tests, all offline: WebSocket framing, gateway
Identify/Heartbeat/Dispatch/Reconnect handling, command
dispatch, quote/challenge catalogue logic, URL validation
(including substring-spoof hosts), catalogue persistence,
REST request construction, a full client↔fake-gateway run
over a real `socketpair`, and the missing-token CLI exit.
No test contacts discord.com or dummyjson.com.

## Files

- `discord_bot.py` — gateway framing/client, REST sender,
  dispatcher, catalogue, CLI.
- `challenges.json` — seed challenge catalogue.
- `docs/SPEC.md` — challenge spec and command table.
- `docs/DESIGN.md` — assumptions, gateway subset, and the
  complete divergence list.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_discord_bot.py` — the test suite.

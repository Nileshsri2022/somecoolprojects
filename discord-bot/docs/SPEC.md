# SPEC — discord-bot

Source page (read first, 2026-10-25):
https://codingchallenges.fyi/challenges/challenge-discord/
Slug used: `challenge-discord` — no correction needed, first
guess (`challenge-discord`, from the search result) loaded
directly; there was no 404.

## Challenge steps, as written on the page

- **Step Zero** — Create an application in the Discord Developer
  Portal, configure a bot user, save its token somewhere safe,
  enable the **MESSAGE CONTENT INTENT**, set bot permissions,
  generate an OAuth2 invite URL (bot scope) and invite the bot
  to a private test server. Optionally read Discord's tutorial
  on building a Discord app.
- **Step 1 — Hello, World!** — Connect to a server, listen for
  messages, and respond to the greeting `Hello` with the bot's
  own greeting that includes the person's name.
- **Step 2** — Respond to `!quote` with a random quote fetched
  from the dummyJSON `/quotes` endpoint (the page points at
  https://dummyjson.com/; the single-random-quote endpoint is
  `/quotes/random`, returning `{"quote": ..., "author": ...}`).
- **Step 3** — Respond to `!challenge` with a random challenge
  from a catalogue of past Coding Challenges challenges
  (the page offers a JSON download of the back catalogue).
- **Step 4** — `!add <challenge>` (the page's text says
  `!add <challenge>`, its example is `!add <challenge URL>`)
  and `!list` to list all available challenges. `!add` must
  check the URL is a valid URL referring to a valid challenge
  on codingchallenges.fyi, and read the challenge title from
  the `<title>` tag of the HTML. Invalid URLs get an error
  reply. Extra credit: persist newly added challenges so they
  survive a restart.
- **Step 5** — Host the bot somewhere it can run 24/7/365
  (the page suggests an AWS Free Tier EC2 instance, run as a
  daemon, auto-started on boot).

## What this build implements

- Step Zero: documented only (see README "Live setup"). No
  token is created, stored, or requested by this code.
- Step 1: `Hello` (case-insensitive, surrounding whitespace
  ignored) → `Hello, <username>!`
- Step 2: `!quote` → `"quote" — author` via the dummyJSON
  random-quote endpoint. The HTTP fetch is injectable, so
  tests never touch the network.
- Step 3: `!challenge` → a random catalogue entry,
  `Title — URL`.
- Step 4: `!list` (numbered list, or a "none yet" reply when
  empty); `!add <url>` validates scheme/host/path (see
  DESIGN.md), fetches the page title (injectable fetcher),
  appends to the catalogue and saves it to JSON on disk.
- Step 5: NOT implemented as automation — provisioning a
  server is a user-side operation. README documents how to
  run the bot under systemd once the user has a host.
- Gateway/REST plumbing the page implies but does not spell
  out: Discord Gateway (WebSocket) Identify/Heartbeat/
  Dispatch handling and the REST `POST /channels/{id}/messages`
  call, implemented with the Python standard library only.

## Commands (all messages are otherwise ignored)

| Input | Reply |
|---|---|
| `Hello` | `Hello, <username>!` |
| `!quote` | `"..." — author` |
| `!challenge` | `<title> — <url>` |
| `!list` | numbered catalogue, or "No challenges yet." |
| `!add <url>` | success / invalid-URL / fetch-failure reply |
| `!help` | command list (small extra, see DESIGN.md) |

Messages from bots (including this bot itself) are ignored,
so the bot can never reply to its own replies.

## Non-goals

- No voice, no slash commands, no embeds, no reactions.
- No real Discord connection in tests; no network call to
  discord.com or dummyjson.com in tests.
- No token handling beyond reading the `DISCORD_BOT_TOKEN`
  environment variable name at run time (see README).

# Monkeytype — SPEC

Source challenge (read 2026-10-25): https://codingchallenges.fyi/challenges/challenge-monkeytype
— "Build Your Own Monkeytype", a minimalistic typing test inspired by monkeytype.com.

## What the challenge asks for

- **Step 0** — Pick a tech stack and set up a blank project.
- **Step 1** — A typing-test home page with a fixed prompt (random words or a
  favourite quote) and a blinking cursor hint.
- **Step 2** — Show letters/mistakes as the user types; the cursor moves
  through the text; mistakes in red, correct letters in another colour.
- **Step 3** — Record statistics while typing (correct and total characters
  typed so far) and the start/end time (end = when the user types the Nth
  character, where N is the number of characters in the test). On finish show:
  1. WPM — correct characters / 5 / minutes taken.
  2. Raw WPM — characters typed / 5 / minutes taken.
  3. Accuracy — percentage of correctly typed characters.
- **Step 4** — Sign in after seeing a result, including creating an account.
  With an account, keep track of results (date + statistics) and support
  log in, log out, password reset, and account deletion.
- **Step 5** — Replace the fixed prompt with a random set of words: from a
  list of the 1000 most common words, pick 20–30 at random.
- **Step 6** — A leaderboard: top 50 WPM scores with username and accuracy,
  excluding scores with accuracy below 90% (anti-gaming threshold).
- **Going Further** — Graphical summary of results; deploy live; support
  other natural languages.

## What this build does (terminal core)

Single-file Python 3 standard-library program `monkeytype.py`:

- **Words mode (Step 5, default):** 25 random words (configurable 10–50)
  sampled from an embedded common-English word list (422 words).
- **Fixed-prompt mode (Step 1):** `--prompt "..."` uses that exact text
  instead of random words.
- **Live typing (Step 2):** curses UI — prompt on screen, cursor advances,
  correct letters green, mistakes red, untyped letters dim; Backspace
  corrects the previous character; Esc quits without saving. When curses
  is unavailable (or `--no-curses` is given) a line-input fallback prints
  the prompt, times one `input()` line, and scores it the same way.
- **Statistics (Step 3):** live correct/total counts in the curses UI;
  on finish, WPM, raw WPM, accuracy, correct/total characters, and
  elapsed seconds. The test ends automatically when the Nth character
  is typed. Definitions follow the page exactly, with "word" = 5
  characters: `WPM = (correct / 5) / minutes`,
  `raw WPM = (typed / 5) / minutes`,
  `accuracy = 100 * correct / typed` (0 when nothing typed).
  A character counts as correct only if it matches the target at the
  same position; characters typed past the end of the prompt cannot
  occur in the curses UI (input stops at N) and count as incorrect in
  the pure scoring function.
- **Accounts (Step 4, local):** `create-user`, `login`, `logout`,
  `reset-password`, `delete-user` commands. Passwords are never stored
  in plain text: PBKDF2-HMAC-SHA256 with a random 16-byte salt per user.
  A successful login writes a session file in the data directory; the
  next `test` attributes its result to the logged-in user. Results are
  stored per user with an ISO date/time stamp and the full statistics.
  `history` lists a user's results; aggregate stats (best/average WPM,
  average accuracy, test count) are computed from them.
- **Leaderboard (Step 6):** `leaderboard` shows the top 50 results across
  all local users, sorted by WPM descending, filtered to accuracy >= 90%,
  with username, WPM, accuracy, and date.
- **Going Further (partial):** the results screen includes a plain-text
  per-result breakdown (correct/incorrect/total, elapsed time); no
  graphical chart is drawn.

## Deliberate divergences

1. **Terminal, not web (Step 0 choice).** The challenge is aimed at
   frontend developers and suggests a desktop app as an alternative.
   This build is a terminal app (curses + line fallback), not a web
   page. There is no HTML/CSS/JS UI, no blinking-cursor animation in
   the line fallback (the curses UI shows a block cursor that advances
   as you type), and no live deployment.
2. **Word list is a subset, not the full 1000.** The embedded list has
   422 common English words (from general knowledge of common words,
   not copied from the EF page linked by the challenge). Sampling 25
   from 422 still gives varied prompts; the count is stated honestly
   here and in the README rather than claiming 1000.
3. **Accounts are local, not online.** No email verification, no server,
   no password-recovery email: `reset-password` verifies the old
   password (local equivalent of an authenticated reset) and sets a new
   one. No account can appear on a public leaderboard; the leaderboard
   covers only users on this machine's data directory.
4. **Timed modes not built.** Monkeytype also offers timed tests; the
   challenge steps specify only the words/fixed-prompt test ending at
   the Nth character, so only that mode is implemented.
5. **No other languages, no graphical chart.** Listed under "Going
   Further" and not built; see "Not built" below.

## Not built

- Web UI, live deployment, or any network access (the program never
  touches the network).
- Online accounts, leaderboards shared between machines, or social
  features.
- Timed (15/30/60 s) or quote-length modes beyond `--prompt`.
- Other natural languages.
- Graphical (chart/image) result summaries — a text breakdown only.
- Sound, themes, or customisation options from monkeytype.com.

## Data files (default data directory)

- Default: `~/.local/share/monkeytype/` (override with `--data-dir`).
- `users.json` — users, password hashes/salts, and per-user results.
- `session.json` — username of the currently logged-in user, if any.
- Data files are created only when an account/test command needs them;
  the pure scoring/word functions never touch disk.

## CLI

```
python3 monkeytype.py test [--count 25] [--prompt "..."] [--no-curses] [--data-dir DIR]
python3 monkeytype.py history [--user NAME] [--data-dir DIR]
python3 monkeytype.py leaderboard [--data-dir DIR]
python3 monkeytype.py create-user USERNAME [--data-dir DIR]
python3 monkeytype.py login USERNAME [--data-dir DIR]
python3 monkeytype.py logout [--data-dir DIR]
python3 monkeytype.py reset-password USERNAME [--data-dir DIR]
python3 monkeytype.py delete-user USERNAME [--data-dir DIR]
python3 monkeytype.py               # interactive menu (no arguments)
```

Exit codes: 0 on success, 1 on usage/account errors (unknown user, wrong
password, duplicate user), 2 on argparse errors. `test` with Esc in the
curses UI exits 0 without saving a result.

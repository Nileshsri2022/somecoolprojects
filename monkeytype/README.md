# Monkeytype (terminal clone)

A terminal typing test inspired by monkeytype.com, built for the
Coding Challenges "Build Your Own Monkeytype" challenge:
https://codingchallenges.fyi/challenges/challenge-monkeytype

**Terminal-only.** There is no web UI, no online account, and no shared
leaderboard — see `docs/SPEC.md` for the full, honest scope.

## Run

```bash
python3 monkeytype.py            # interactive menu
python3 monkeytype.py test       # curses test, 25 random words
python3 monkeytype.py test --no-curses --prompt "hello world"
python3 monkeytype.py test --count 30
```

While typing in the curses UI: correct letters are green, mistakes red,
untyped letters dim, and the cursor (reverse video) advances as you
type. Backspace corrects; Esc abandons without saving. The test ends
automatically when you type the last character.

## Results

On finish you get WPM (correct chars / 5 / minutes), raw WPM (typed
chars / 5 / minutes), accuracy, correct/total characters, and elapsed
time — exactly the definitions on the challenge page.

## Accounts, history, leaderboard

```bash
python3 monkeytype.py create-user alice
python3 monkeytype.py login alice
python3 monkeytype.py test            # result saved to alice
python3 monkeytype.py history         # alice's results + averages
python3 monkeytype.py leaderboard     # top 50, accuracy >= 90% only
python3 monkeytype.py reset-password alice
python3 monkeytype.py logout
python3 monkeytype.py delete-user alice
```

Passwords are stored only as PBKDF2-HMAC-SHA256 hashes with a random
salt. Data lives in `~/.local/share/monkeytype/` (`users.json`,
`session.json`); pass `--data-dir DIR` (before or after the subcommand)
to use another directory. Accounts and the leaderboard are local to
that directory — nothing is sent over the network.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

27 tests, all headless (word generation, scoring, accounts/storage,
leaderboard, summaries, result formatting). The curses UI itself is
manual-only — it needs a real TTY.

## Structure

- `monkeytype.py` — the whole program (Python 3 standard library only)
- `docs/SPEC.md` — challenge steps, divergences, what is NOT built
- `docs/DESIGN.md` — design notes
- `docs/TEST_PLAN.md` — test coverage and pass criteria
- `tests/test_monkeytype.py` — unittest suite

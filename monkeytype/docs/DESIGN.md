# Monkeytype — DESIGN

## Stack

Python 3 standard library only: `argparse`, `curses` (optional at
runtime), `getpass`, `hashlib`, `json`, `os`, `random`, `secrets`,
`sys`, `time`. One main file, `monkeytype.py`, so the program runs with
just `python3 monkeytype.py`. No third-party packages, no network.

## Pure logic (headless-testable, no I/O)

- `COMMON_WORDS: list[str]` — 422 common English words, all lowercase
  alphabetic, no duplicates.
- `generate_words(pool, count, rng=None) -> list[str]`
  Uses `rng.sample` when `count <= len(pool)`, else `rng.choices`
  (sampling with replacement) so any requested count works. A caller
  supplied `random.Random` makes generation deterministic in tests.
- `make_prompt(words) -> str` — `" ".join(words)`.
- `char_results(target, typed) -> list[bool]` — position-wise
  comparison; position `i` is correct iff `i < len(target)` and
  `typed[i] == target[i]`. Extra typed characters are `False`.
- `score_test(target, typed, elapsed_seconds) -> dict` — counts
  correct/total from `char_results`, then:
  - `minutes = elapsed_seconds / 60`
  - `wpm = (correct / 5) / minutes` if minutes > 0 else 0.0
  - `raw_wpm = (len(typed) / 5) / minutes` if minutes > 0 else 0.0
  - `accuracy = 100 * correct / len(typed)` if typed else 0.0
  - values rounded to 2 decimals in the returned dict; raw counts are
    ints. Zero/negative elapsed time yields 0.0 WPM rather than a
    division error — a test can never take negative time, and a
    zero-second finish is degenerate, not infinite speed.
- `summarise_results(results) -> dict` — count, best WPM, average WPM,
  average accuracy over a list of stored result dicts (0.0s when empty).

## Accounts and storage (disk, still stdlib-only)

- `hash_password(password, salt=None) -> (salt_hex, hash_hex)` —
  PBKDF2-HMAC-SHA256, 200,000 iterations, 16-byte salt from `secrets`.
- `verify_password(password, salt_hex, hash_hex) -> bool` — constant-time
  comparison via `hmac.compare_digest`.
- `UserStore(data_dir)` — loads/saves `users.json` (created lazily):
  - `create_user(username, password)` — raises `ValueError` on empty
    name/password or duplicate user.
  - `verify_user(username, password) -> bool` — False for unknown user.
  - `reset_password(username, old, new)` — raises `ValueError` on
    unknown user or wrong old password.
  - `delete_user(username)` — raises `ValueError` on unknown user.
  - `add_result(username, result)` — appends a result dict (must
    contain at least wpm/accuracy/date); raises on unknown user.
  - `results_for(username) -> list` — [] for unknown user.
  - `leaderboard(limit=50)` — all users' results with
    `accuracy >= 90.0`, sorted by WPM descending (ties: earlier date
    first), truncated to `limit`, each entry annotated with `username`.
- Session: `login` writes `session.json` `{"username": ...}`;
  `logout` removes it; `current_user()` returns the name or None.
  The session file is plain local state, not a security token — it only
  attributes results on the same machine.
- Storage format is JSON with an atomic-ish write (write temp file,
  `os.replace`). Corrupt `users.json` raises rather than silently
  discarding accounts; tests cover round-tripping through a temp dir.

## Terminal UI

- `run_curses_test(prompt) -> (typed, elapsed) | None` — full-screen
  curses: prompt wrapped to terminal width, correct = green, wrong =
  red, untyped = dim, cursor = reverse video on the current position.
  Backspace (KEY_BACKSPACE / 127 / 8) removes the last character.
  Printable characters append until `len(typed) == len(prompt)`, at
  which point the function returns. Esc (27) returns None (abandoned).
  The timer starts on the first keystroke, matching "start time" as
  first input, and ends at the Nth character. Live `correct/total`
  counts are shown in the footer.
- `run_line_test(prompt) -> (typed, elapsed)` — prints the prompt,
  reads one line with `input()`, times the call. Used when curses is
  unavailable or `--no-curses` is passed, and as the non-interactive
  path for environments without a TTY.
- `format_result(result) -> str` — the results screen text (WPM, raw
  WPM, accuracy, correct/total, elapsed). Shared by both UI paths so
  the numbers cannot drift between them.
- Interactive menu (no arguments): numbered menu — take a test,
  history, leaderboard, create/login/logout/reset/delete account,
  quit. The menu reuses the same functions as the subcommands.

## Error handling

- Unknown users, duplicate users, wrong passwords: `ValueError` in the
  library, printed message + exit 1 in the CLI.
- Missing data directory: created on first write, not on read.
- `KeyboardInterrupt` in the curses UI restores the terminal (curses
  wrapper) and abandons the test without saving.

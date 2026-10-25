# Monkeytype — TEST_PLAN

Suite: `tests/test_monkeytype.py`, run with:

```
python3 -m unittest discover -s tests -v
```

All tests are headless: no curses, no TTY, no network, no real user
home. Storage tests use `tempfile.TemporaryDirectory`.

## Coverage

### Word generation
- Default generation returns the requested count, all words from the
  pool, joined prompt has `count - 1` spaces.
- Seeded `random.Random` generation is reproducible.
- Count larger than the pool still returns that many words (replacement).
- `COMMON_WORDS` has no duplicates, is non-empty, and every entry is
  lowercase alphabetic (no punctuation/digits).

### Scoring
- Perfect typing: accuracy 100, WPM == raw WPM == (len/5)/minutes.
- All-wrong typing: WPM 0, accuracy 0, raw WPM > 0.
- Mixed typing: correct count matches position-wise comparison only
  (a right letter in the wrong position is not correct).
- Extra characters past the prompt count as incorrect, not correct.
- Empty typed input: accuracy 0, both WPMs 0, no exception.
- Zero elapsed time: both WPMs 0, no ZeroDivisionError.
- The page's worked definition: e.g. 50 correct chars in 60 s
  -> 10.0 WPM; 60 typed chars in 60 s -> 12.0 raw WPM.
- `char_results` length equals typed length; per-position booleans.

### Accounts and storage
- Create + verify (right password True, wrong password False,
  unknown user False).
- Duplicate username rejected; empty username/password rejected.
- Passwords are not stored in plain text (stored hash != password,
  salt present, different salts for same password on two users).
- Reset with correct old password works, with wrong old password fails
  and leaves the old password valid.
- Delete removes the user and its results; deleting unknown user fails.
- Results round-trip through a fresh `UserStore` on the same dir
  (JSON persistence), with date + stats intact.
- Adding a result for an unknown user fails.

### Leaderboard and summaries
- Top-50 cap, WPM-descending order, username attached.
- Accuracy < 90 excluded; exactly 90.0 included.
- Empty store -> empty leaderboard; empty results -> zeroed summary.
- Summary: best WPM, average WPM, average accuracy, count.

### Results formatting
- `format_result` contains WPM, raw WPM, accuracy, correct/total,
  and elapsed values for a known score.

## Not covered by automated tests (manual only)

- The curses UI itself (requires a TTY; exercised manually, not in CI):
  colours, cursor movement, Backspace, Esc-abandon, auto-finish at N.
- The line-input fallback timing (depends on a human typing).
- The interactive menu (thin wrapper over tested functions).

## Pass criteria

Full suite green (`OK`, 0 failures, 0 errors) before reporting done.
Skips: none expected; any skip must be reported with its reason.

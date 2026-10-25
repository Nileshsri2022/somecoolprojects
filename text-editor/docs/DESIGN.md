# Text Editor — DESIGN

## Architecture

One file, `ccvim.py`, Python 3 standard library only, in two layers:

```
┌─────────────────────────────────────────────┐
│ curses UI (EditorUI) — terminal only        │
│  raw-ish mode, screen drawing, key dispatch │
│  command/search prompts, status bar         │
├─────────────────────────────────────────────┤
│ Buffer — pure logic, no curses, no I/O      │
│  except load()/save() on explicit paths     │
│  lines, cursor, offsets, undo, search,      │
│  replace, rendering of the visible window   │
└─────────────────────────────────────────────┘
```

The split is deliberate: the challenge's interactive requirements (raw
mode, screen clearing, `~` column) cannot be tested headlessly, but every
editing operation can, so all of it lives in `Buffer` and is unit-tested.

## Buffer state

- `lines: list[str]` — always at least one line; an empty document is `[""]`.
  A list of lines is the straightforward structure the page hints at
  ("think about how to handle storing the lines of text efficiently");
  rendering only touches the visible window, so long files do not cost
  a full redraw per keystroke in the UI (curses redraws the window rows).
- `row, col: int` — cursor, 0-based, `col` clamped to `len(lines[row])`.
- `filename: str | None`, `dirty: bool`.
- `row_offset, col_offset: int` — top-left of the visible window.
- `_undo: list[...]` — snapshots of `(lines, row, col)`, capped at 100.
  A snapshot is pushed before every mutating operation; `undo()` pops.
  Simplicity over a diff-based undo tree (documented limit: no redo).
- `last_search: str | None` — pattern for `n`/`N`.

## Invariants (enforced by the methods, covered by tests)

- `0 <= row < len(lines)`; `0 <= col <= len(lines[row])`.
- `lines` is never empty.
- Vertical moves clamp `col` to the new line's length (Vim-like).
- Horizontal moves never cross a line boundary with `h`/`l`
  (crossing happens only via Backspace/Enter in Insert, and via search).
- `dirty` is set by every mutation, cleared by successful `load`/`save`,
  and never set by pure movement, search, or rendering.
- `ensure_visible(height, width)` moves the offsets by the minimum
  amount that puts the cursor on screen; display columns account for
  tab expansion (tab = 4 columns), so a cursor after a tab scrolls
  correctly.

## Rendering

- `expand_tabs(line)` replaces each `\t` with spaces to the next
  multiple-of-4 column (so tabs align, they are not just 4 spaces each).
- `render_screen(height, width)` returns exactly `height` strings:
  visible buffer lines (expanded, truncated to `width`), then `~` for
  rows past end-of-file. The UI reserves the last physical row for the
  status bar and passes `height = screen_rows - 1`.
- `display_col(line, col)` converts a buffer column to a display column
  through tab expansion; `cursor_display_col()` is its cursor form.

## Search and replace

- `find_next(pattern, wrap=True)` / `find_prev(pattern)`: plain
  substring search, scanning from after/before the cursor, wrapping
  once for `find_next`. Returns `bool` and moves the cursor onto the
  match start on success; leaves the cursor untouched on failure.
- `replace_current(old, new)`: replaces the first occurrence of `old`
  on the cursor's line at or after the cursor; `replace_all(old, new)`:
  non-overlapping replacement on every line, returns the count.
  Empty `old` is a no-op returning 0 / False (never an infinite loop).

## Command parsing (pure, tested)

`parse_command(text, filename)` returns `(action, arg)` where action is
one of `quit`, `force_quit`, `write`, `write_quit`, `goto`, `substitute`,
`substitute_all`, `unknown`. It never touches the filesystem, so the UI
can decide about dirty buffers before acting. The substitute syntax is
parsed strictly: `:s/old/new/` and `:s/old/new/g`; anything else is
`unknown`.

## UI key handling

- `curses.wrapper` owns setup/teardown, so the screen is cleared and
  the cursor repositioned on exit even on exceptions, satisfying Step 2.
- `noecho()` + `cbreak()` + `keypad(True)` gives the Step 1 raw-mode
  properties through curses; keys arrive one at a time without Enter.
- Normal-mode dispatch is a small `if/elif` chain (no keymap framework —
  the command set is small and explicit is better here).
- The `:` and `/` prompts read a line on the status row with echo on
  for that prompt only, then restore normal handling.
- `q` / `:q` quit logic lives in the UI (it needs the dirty check plus
  a user-visible message); the pure core deliberately has no opinion
  about quitting.
- `Ctrl-C` (`\x03`) in Normal mode is treated like `q` (warn if dirty),
  never as a process interrupt, while the UI runs; `Ctrl-C` in a prompt
  cancels the prompt.

## Error handling

- Missing file on startup: start with an empty buffer named for that
  path (saving creates it) and show `New file` — this is the standard
  editor behaviour, not an error.
- Unreadable / undecodable file on startup: print the error and exit
  non-zero before entering curses, so the user actually sees it instead
  of it flashing inside the alternate screen.
- Failed save: the error is shown on the status bar and the buffer
  stays dirty; the editor does not quit on `:wq` if the write failed.

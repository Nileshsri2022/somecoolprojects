# Text Editor — TEST_PLAN

## What is tested headlessly (unittest, `tests/test_ccvim.py`)

Everything in the pure `Buffer` class and the pure `parse_command`
function — no terminal, no curses, no keystrokes:

- Construction: empty buffer is `[""]` with cursor (0, 0), clean.
- Cursor movement: `h/j/k/l` each direction, clamping at all four edges,
  column clamping when moving to a shorter line, `goto_line` (including
  out-of-range clamping), first/last line helpers.
- Insertion: insert at start/middle/end, insert newline splits a line
  (both halves preserved, cursor on the new line), tab insertion.
- Deletion: Backspace mid-line, Backspace at column 0 joins lines,
  Backspace at (0, 0) is a no-op, `delete_char` mid-line and at EOL
  (no-op at EOL), `delete_line` (middle, last, and sole line → `[""]`).
- Dirty flag: set by mutations, untouched by movement/search/render,
  cleared by save, set again by a later edit.
- Load/save round-trip via temp files: multi-line content, empty file,
  missing file (empty buffer, filename kept), trailing-newline
  normalisation (see SPEC divergence 3).
- Search: forward find, wrap-around, no-match leaves cursor untouched,
  backward find, empty pattern is a no-op.
- Replace: replace on current line, replace-all count across lines,
  no-match returns 0 / False, empty pattern is a no-op.
- Undo: undoes insert, newline, delete-line; undo on an empty history
  is a no-op; undo restores cursor position.
- Scrolling: `ensure_visible` keeps the cursor on screen when moving
  down past the window and back up; column scrolling with long lines.
- Rendering: `~` rows past EOF, exact row count returned, tab expansion
  to multiples of 4, truncation to the given width.
- Command parsing: every colon command in SPEC (including `:w <file>`,
  `:q!`, `:<number>`, `:s/old/new/` and `/g`), plus unknown commands
  and malformed substitutes.

## What is NOT claimed as headlessly tested

- The interactive curses UI: raw-mode key reading, screen clearing,
  the `~` column on a real terminal, the status bar, prompts, and the
  `q` / dirty-warning quit flow. These need a real terminal (or a pty
  harness, which this task does not build). They are exercised only by
  manual run: `python3 ccvim.py <file>` in a terminal, typing `i`,
  text, `Esc`, `:wq`.
- No performance or large-file benchmark is claimed.

## Running

```
python3 -m unittest discover -s tests -v
```

Exit code 0 with all tests passing is the acceptance gate for this
project. A manual smoke run of the curses UI (open, type, save, quit)
is recommended before demoing, but is not part of the automated suite.

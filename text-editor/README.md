# Build Your Own Text Editor — ccvim

A mini terminal-based text editor (Vim-style subset) in Python 3 standard
library only. Built for the Coding Challenges challenge:

`https://codingchallenges.fyi/challenges/challenge-text-editor`

(also Coding Challenge #73 on Substack). Terminal only — **not** a GUI editor,
and **not** a full Vim clone.

## Run

```
python3 ccvim.py            # empty buffer
python3 ccvim.py notes.txt  # open a file (a missing file starts empty)
```

## Modes

- **NORMAL** (control mode): movement and commands. `Esc` in Insert returns here.
- **INSERT** (editor mode): typing inserts text. Enter splits a line,
  Backspace deletes backwards (joining lines at column 0), `Esc` returns
  to Normal.

## Normal-mode keys

| Key | Action |
|---|---|
| `h j k l`, arrows | Move left / down / up / right (bounds-checked) |
| PageUp / PageDown | Move a screenful |
| `i` | Insert before cursor |
| `a` | Append after cursor |
| `o` | Open a new line below |
| `x` | Delete character under cursor |
| `dd` | Delete current line |
| `u` | Undo |
| `gg` / `G` | First / last line |
| `/pattern` | Search forward (wraps once); `n` next, `N` previous |
| `:` | Command prompt |
| `q` | Quit — immediately if clean, otherwise warns (see below) |

## Colon commands

`:w`, `:w <file>`, `:wq`, `:wq <file>`, `:q`, `:q!`, `:<number>` (go to
line), `:s/old/new/` (replace on current line), `:s/old/new/g` (replace
in whole buffer). Search is a plain substring search, not regex.

`q` / `:q` with unsaved changes do **not** quit; they show
`Unsaved changes — :q! to quit, :wq to save`. Use `:q!` to discard.

## Screen

The editor clears the screen on start and exit, draws `~` on rows past
end-of-file like Vim, scrolls when the document exceeds the screen, expands
tabs to 4-column stops (tabs are stored literally), and shows a status bar
with filename, modified flag (`[+]`), line/column, mode, and messages.

## Files

- `ccvim.py` — the whole editor: pure `Buffer` core + curses UI.
- `docs/SPEC.md` — challenge steps, exact command subset, divergences,
  and what was NOT built.
- `docs/DESIGN.md`, `docs/TEST_PLAN.md` — design and test notes.
- `tests/test_ccvim.py` — headless unittest suite for the pure core.

## Tests

```
python3 -m unittest discover -s tests -v
```

54 tests, all passing. The interactive curses UI itself is not tested
headlessly (it needs a real terminal); all editing logic lives in the
pure `Buffer` class and is covered. See `docs/TEST_PLAN.md`.

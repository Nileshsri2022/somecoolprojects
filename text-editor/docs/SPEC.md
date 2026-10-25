# Text Editor — SPEC

## Challenge source (resolved, not guessed)

- Resolved challenge page:
  `https://codingchallenges.fyi/challenges/challenge-text-editor`
- Found via the site tag index `https://codingchallenges.fyi/challenges/tags`
  → `intermediate` tag page
  (`https://codingchallenges.fyi/challenges/tags/intermediate/`) →
  "Build Your Own Text Editor" link → the page above.
  The original Substack post is Coding Challenge #73:
  `https://codingchallenges.substack.com/p/coding-challenge-73-text-editor`
  (same steps, read and cross-checked).
- Tag-page description: "build your own terminal based text editor — think of
  it as a mini version of Vim, Ed or Nano." This is a **terminal** editor.
  It is NOT a GUI editor.

## Challenge steps, and how each is met

| Page step | Requirement | Implementation |
|---|---|---|
| Step 0 | Set up environment / language of choice | Python 3 standard library only, one file `ccvim.py` |
| Step 1 | Start up, quit on `q`; read stdin unbuffered; disable echo; disable output processing; disable CTRL-C / CTRL-Z / CTRL-M / CTRL-S / CTRL-Q / CTRL-V handling (raw mode) | `curses` UI: `curses.raw()`-equivalent handling via curses (`noecho`, `cbreak`, keypad on). In Normal mode `q` quits when the buffer is clean; see divergence note below. CTRL-C is caught and treated as quit-with-warning, not as a terminal interrupt, while the UI is running |
| Step 2 | Clear screen on start, cursor top-left; clear screen and reposition cursor on exit; draw a `~` column down the left-hand side like Vim | `curses` clears on start/exit; `Buffer.render_screen()` returns `~` for rows past end-of-file; cursor placed at the buffer cursor |
| Step 3 | Move cursor with Vim keys `h` (left), `j` (down), `k` (up), `l` (right); bounds-checked, never off screen | `Buffer.move_*()` clamp row/column; arrow keys also work (a Going Further item) |
| Step 4 | 'Control' mode and 'editor' mode; switch with Escape for control mode and Escape followed by `i` for editor mode; think about efficient line storage / rendering | Two modes: NORMAL (control) and INSERT (editor). `Esc` in Insert returns to Normal; `i` in Normal enters Insert. `Esc` followed by `i` therefore also works (Esc is a no-op in Normal, then `i` enters Insert) — see divergence note. Lines stored as a Python list of strings; rendering is a pure function of the visible window only |
| Step 5 | Open a file given on startup, e.g. `ccvim text.txt`; `:w` saves, `:wq` saves and quits | `ccvim.py [file]`; colon commands `:w`, `:w <file>`, `:wq`, `:wq <file>`, `:q`, `:q!`, `:<number>` (go to line) |
| Going Further | Search, then find and replace | `/pattern` search forward, `n` next, `N` previous, `:s/old/new/` (current line) and `:s/old/new/g` (whole buffer) — see command list in README |
| Going Further | Scrolling when the document is longer than the screen | Pure `Buffer.ensure_visible()` maintains row/column offsets |
| Going Further | Handling tabs | Tabs are stored as `\t`; rendered expanded to 4 columns; Tab key in Insert inserts a literal tab |
| Going Further | Arrow and Page Up/Down keys | Arrow keys move; PageUp/PageDown move a screenful |
| Going Further | Status bar | Last screen line shows filename, modified flag, line/col, mode, and messages |

## Supported command subset (exact — this is NOT a full Vim clone)

Normal mode: `h j k l`, arrows, PageUp/PageDown, `i` (insert before cursor),
`a` (append after cursor), `o` (open a new line below), `x` (delete character
under cursor), `dd` (delete current line), `u` (undo), `G` (last line),
`gg` (first line), `/` (search prompt), `n` / `N` (next/previous match),
`:` (command prompt), `q` (quit — see note), `Esc` (no-op, stays in Normal).

Insert mode: printable characters, Enter (split line), Backspace (delete
backwards, joining lines at column 0), Tab (literal tab), arrows, `Esc`
(return to Normal).

Colon commands: `:w`, `:w <file>`, `:wq`, `:wq <file>`, `:q`, `:q!`,
`:<number>`, `:s/old/new/`, `:s/old/new/g`. Anything else reports
`Unknown command` and does nothing.

Search: `/pattern` searches forward from after the cursor and wraps once to
the top of the file; no match reports `Pattern not found`. Search is a plain
substring search, NOT a regular expression.

## Deliberate divergences / clarifications (honest, not silent)

1. **Mode-switch wording.** The page says "escape key for 'control' mode and
   escape followed by i for 'editor' mode". Taken literally that would make
   entering Insert require two keys after already being in control mode.
   Implemented as standard Vim instead: `Esc` = back to Normal, `i` = into
   Insert. The literal `Esc` then `i` sequence still works, because `Esc`
   in Normal is a no-op and `i` then enters Insert.
2. **`q` with unsaved changes.** Step 1 says quit on `q`; Step 5 adds `:wq`.
   Blindly quitting on `q` would silently discard edits, so: `q` quits
   immediately only when the buffer is clean; when dirty it shows
   `Unsaved changes — :q! to quit, :wq to save` and does not quit.
   `:q` behaves the same way; `:q!` always quits discarding changes.
3. **Trailing newline on save.** Loading strips one trailing newline and
   saving always writes one (for a non-empty buffer). A file that did not
   end with a newline therefore gains one on save. An empty buffer saves
   as an empty (0-byte) file. This is the normal text-editor convention.
4. **Raw mode via curses, not manual termios.** The page's raw-mode
   requirements (unbuffered input, no echo, no output processing, no
   CTRL-* handling) are met through Python's `curses` module (`noecho`,
   `cbreak`, keypad decoding), which is the standard-library way to get
   exactly that terminal behaviour, rather than hand-rolled termios calls.
   The interactive UI therefore cannot be exercised headlessly (see
   TEST_PLAN.md); all editing logic lives in the pure `Buffer` class and
   is tested headlessly.
5. **No `ed`-style line editor, no Nano keybindings.** Only the Vim-style
   subset above is built. Nano-style `^O`/`^X` bindings are NOT supported.
6. **Search is substring, not regex.** The page does not specify regex, so
   no regex engine is claimed.

## NOT built

- A full Vim clone (visual mode, registers, macros, marks, splits, plugins,
  syntax highlighting, line numbers gutter beyond the `~` column).
- A GUI editor of any kind.
- Regex search, incremental search highlighting, or search highlighting.
- Undo redo (`Ctrl-R` / redo stack): only single-direction undo (`u`) is
  implemented; the undo history is capped at 100 snapshots.
- File encodings other than UTF-8 (files are read/written as UTF-8;
  undecodable bytes raise an error shown in the status bar instead of
  being silently mangled).
- Multi-file / tab / buffer switching: one file per invocation.
- Mouse support.

## Usage

```
python3 ccvim.py            # empty buffer
python3 ccvim.py notes.txt  # open existing file, or start empty for a new one
```

## Files

- `ccvim.py` — the whole editor: pure `Buffer` core + curses UI + CLI.
- `tests/test_ccvim.py` — unittest suite for the pure core and command parsing.

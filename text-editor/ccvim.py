#!/usr/bin/env python3
"""ccvim -- a mini terminal text editor (Vim-style subset).

Pure core (Buffer + parse_command) has no curses dependency and is fully
unit-tested headlessly. The curses UI at the bottom is the interactive
front end only. See docs/SPEC.md for the exact supported command subset.

Usage: python3 ccvim.py [file]
"""

import curses
import sys

TAB_WIDTH = 4
UNDO_LIMIT = 100


def expand_tabs(line):
    """Expand tabs to spaces aligned to multiples of TAB_WIDTH."""
    out = []
    col = 0
    for ch in line:
        if ch == "\t":
            spaces = TAB_WIDTH - (col % TAB_WIDTH)
            out.append(" " * spaces)
            col += spaces
        else:
            out.append(ch)
            col += 1
    return "".join(out)


def display_col(line, col):
    """Display column of buffer column `col` in `line` (tab-aware)."""
    return len(expand_tabs(line[:col]))


class Buffer:
    """Pure editing core: lines, cursor, undo, search, replace, render."""

    def __init__(self, lines=None, filename=None):
        self.lines = list(lines) if lines else [""]
        if not self.lines:
            self.lines = [""]
        self.row = 0
        self.col = 0
        self.filename = filename
        self.dirty = False
        self.row_offset = 0
        self.col_offset = 0
        self.last_search = None
        self._undo = []

    # -- internal -----------------------------------------------------
    def _snapshot(self):
        self._undo.append((list(self.lines), self.row, self.col))
        del self._undo[: max(0, len(self._undo) - UNDO_LIMIT)]

    def _clamp(self):
        self.row = max(0, min(self.row, len(self.lines) - 1))
        self.col = max(0, min(self.col, len(self.lines[self.row])))

    # -- file I/O ------------------------------------------------------
    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content == "":
            self.lines = [""]
        else:
            self.lines = content.split("\n")
            if content.endswith("\n"):
                self.lines.pop()
        self.filename = path
        self.row = 0
        self.col = 0
        self.row_offset = 0
        self.col_offset = 0
        self.dirty = False
        self._undo = []

    def save(self, path=None):
        target = path or self.filename
        if not target:
            raise ValueError("No filename: use :w <file>")
        text = "\n".join(self.lines)
        if text:
            text += "\n"
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        self.filename = target
        self.dirty = False

    @property
    def text(self):
        return "\n".join(self.lines)

    # -- movement ------------------------------------------------------
    def move_left(self):
        if self.col > 0:
            self.col -= 1

    def move_right(self):
        if self.col < len(self.lines[self.row]):
            self.col += 1

    def move_up(self):
        if self.row > 0:
            self.row -= 1
            self._clamp()

    def move_down(self):
        if self.row < len(self.lines) - 1:
            self.row += 1
            self._clamp()

    def goto_line(self, n):
        """1-based line number, clamped."""
        self.row = max(0, min(n - 1, len(self.lines) - 1))
        self._clamp()

    def goto_first_line(self):
        self.goto_line(1)

    def goto_last_line(self):
        self.goto_line(len(self.lines))

    # -- editing -------------------------------------------------------
    def insert_char(self, ch):
        self._snapshot()
        line = self.lines[self.row]
        self.lines[self.row] = line[: self.col] + ch + line[self.col :]
        self.col += 1
        self.dirty = True

    def insert_newline(self):
        self._snapshot()
        line = self.lines[self.row]
        self.lines[self.row] = line[: self.col]
        self.lines.insert(self.row + 1, line[self.col :])
        self.row += 1
        self.col = 0
        self.dirty = True

    def backspace(self):
        if self.col > 0:
            self._snapshot()
            line = self.lines[self.row]
            self.lines[self.row] = line[: self.col - 1] + line[self.col :]
            self.col -= 1
            self.dirty = True
        elif self.row > 0:
            self._snapshot()
            prev = self.lines[self.row - 1]
            cur = self.lines.pop(self.row)
            self.row -= 1
            self.col = len(prev)
            self.lines[self.row] = prev + cur
            self.dirty = True
        # else: at (0, 0) -- no-op

    def delete_char(self):
        line = self.lines[self.row]
        if self.col < len(line):
            self._snapshot()
            self.lines[self.row] = line[: self.col] + line[self.col + 1 :]
            self.dirty = True
        # else: at EOL -- no-op

    def delete_line(self):
        self._snapshot()
        del self.lines[self.row]
        if not self.lines:
            self.lines = [""]
        self._clamp()
        self.dirty = True

    def open_line_below(self):
        self._snapshot()
        self.lines.insert(self.row + 1, "")
        self.row += 1
        self.col = 0
        self.dirty = True

    def undo(self):
        if not self._undo:
            return False
        lines, row, col = self._undo.pop()
        self.lines = lines
        self.row, self.col = row, col
        self.dirty = True
        return True

    # -- search / replace ----------------------------------------------
    def find_next(self, pattern, wrap=True):
        if not pattern:
            return False
        self.last_search = pattern
        # From just after the cursor, then (optionally) wrap to the top.
        ranges = [(self.row, self.col + 1)]
        if wrap:
            ranges.append((0, 0))
        seen_rows = set()
        for start_row, start_col in ranges:
            for r in range(start_row, len(self.lines)):
                if r in seen_rows:
                    continue
                seen_rows.add(r)
                line = self.lines[r]
                c0 = start_col if r == start_row else 0
                idx = line.find(pattern, c0)
                if idx != -1:
                    self.row, self.col = r, idx
                    return True
                start_col = 0
        return False

    def find_prev(self, pattern):
        if not pattern:
            return False
        self.last_search = pattern
        for r in range(self.row, -1, -1):
            line = self.lines[r]
            # On the cursor's row only matches starting before the cursor
            # count (so N moves to a strictly earlier match).
            idx = (line.rfind(pattern, 0, self.col) if r == self.row
                   else line.rfind(pattern))
            if idx != -1:
                self.row, self.col = r, idx
                return True
        return False

    def replace_current(self, old, new):
        if not old:
            return False
        line = self.lines[self.row]
        idx = line.find(old, self.col)
        if idx == -1:
            return False
        self._snapshot()
        self.lines[self.row] = line[:idx] + new + line[idx + len(old) :]
        self.col = idx + len(new)
        self.dirty = True
        return True

    def replace_all(self, old, new):
        if not old:
            return 0
        count = 0
        changed = False
        new_lines = []
        for line in self.lines:
            n = line.count(old)
            if n:
                changed = True
                count += n
                new_lines.append(line.replace(old, new))
            else:
                new_lines.append(line)
        if changed:
            self._snapshot()
            self.lines = new_lines
            self._clamp()
            self.dirty = True
        return count

    # -- viewport / rendering -------------------------------------------
    def cursor_display_col(self):
        return display_col(self.lines[self.row], self.col)

    def ensure_visible(self, height, width):
        if height < 1:
            height = 1
        if width < 1:
            width = 1
        if self.row < self.row_offset:
            self.row_offset = self.row
        elif self.row >= self.row_offset + height:
            self.row_offset = self.row - height + 1
        dcol = self.cursor_display_col()
        if dcol < self.col_offset:
            self.col_offset = dcol
        elif dcol >= self.col_offset + width:
            self.col_offset = dcol - width + 1

    def render_screen(self, height, width):
        """Exactly `height` strings: buffer lines, then '~' past EOF."""
        out = []
        for i in range(height):
            r = self.row_offset + i
            if r < len(self.lines):
                expanded = expand_tabs(self.lines[r])
                out.append(expanded[self.col_offset : self.col_offset + width])
            else:
                out.append("~")
        return out

    def status(self, mode, message=""):
        name = self.filename or "[No Name]"
        flag = "[+]" if self.dirty else ""
        parts = [name, flag, f"line {self.row + 1}/{len(self.lines)}",
                 f"col {self.col + 1}", mode]
        if message:
            parts.append(message)
        return " ".join(p for p in parts if p)


def parse_command(text, filename=None):
    """Parse a ':' command. Returns (action, arg); never touches disk.

    Actions: quit, force_quit, write, write_quit, goto, substitute,
    substitute_all, unknown. `arg` is a filename / line number /
    (old, new) tuple / message, depending on the action.
    """
    text = text.strip()
    if text in ("q",):
        return ("quit", None)
    if text == "q!":
        return ("force_quit", None)
    if text == "w":
        return ("write", filename)
    if text.startswith("w "):
        name = text[2:].strip()
        return ("write", name if name else filename)
    if text == "wq":
        return ("write_quit", filename)
    if text.startswith("wq "):
        name = text[3:].strip()
        return ("write_quit", name if name else filename)
    if text.isdigit():
        return ("goto", int(text))
    if text.startswith("s/"):
        body = text[2:]
        parts = body.split("/")
        if len(parts) == 3 and parts[0] and parts[2] == "":
            return ("substitute", (parts[0], parts[1]))
        if len(parts) == 3 and parts[0] and parts[2] == "g":
            return ("substitute_all", (parts[0], parts[1]))
        return ("unknown", text)
    return ("unknown", text)


# ---------------------------------------------------------------------------
# Curses UI (interactive only; not covered by the headless test suite)
# ---------------------------------------------------------------------------

class EditorUI:
    def __init__(self, stdscr, buf):
        self.stdscr = stdscr
        self.buf = buf
        self.mode = "NORMAL"  # or "INSERT"
        self.message = ""
        self.quit = False

    def prompt(self, prefix):
        """Read a line on the status row; returns None if cancelled."""
        rows, cols = self.stdscr.getmaxyx()
        curses.echo()
        self.stdscr.move(rows - 1, 0)
        self.stdscr.clrtoeol()
        self.stdscr.addstr(rows - 1, 0, prefix)
        self.stdscr.refresh()
        chars = []
        while True:
            key = self.stdscr.getch()
            if key in (27, 3):  # Esc / Ctrl-C cancels
                curses.noecho()
                return None
            if key in (10, 13):
                break
            if key in (127, 8, curses.KEY_BACKSPACE):
                if chars:
                    chars.pop()
                    y, x = self.stdscr.getyx()
                    self.stdscr.move(y, max(0, x - 1))
                    self.stdscr.clrtoeol()
            elif 32 <= key < 127:
                chars.append(chr(key))
                self.stdscr.addch(key)
        curses.noecho()
        return "".join(chars)

    def run_command(self, text):
        action, arg = parse_command(text, self.buf.filename)
        if action == "quit":
            if self.buf.dirty:
                self.message = "Unsaved changes -- :q! to quit, :wq to save"
            else:
                self.quit = True
        elif action == "force_quit":
            self.quit = True
        elif action in ("write", "write_quit"):
            try:
                self.buf.save(arg)
                self.message = f'Wrote {self.buf.filename}'
            except (OSError, ValueError) as exc:
                self.message = f"Save failed: {exc}"
                return
            if action == "write_quit":
                self.quit = True
        elif action == "goto":
            self.buf.goto_line(arg)
            self.message = ""
        elif action == "substitute":
            old, new = arg
            if self.buf.replace_current(old, new):
                self.message = "Substituted"
            else:
                self.message = "Pattern not found on this line"
        elif action == "substitute_all":
            old, new = arg
            count = self.buf.replace_all(old, new)
            self.message = f"{count} substitution(s)"
        else:
            self.message = f"Unknown command: :{text}"

    def handle_normal(self, key):
        buf = self.buf
        if key in (ord("q"), 3):  # q or Ctrl-C
            if buf.dirty:
                self.message = "Unsaved changes -- :q! to quit, :wq to save"
            else:
                self.quit = True
        elif key == ord("h") or key == curses.KEY_LEFT:
            buf.move_left()
        elif key == ord("j") or key == curses.KEY_DOWN:
            buf.move_down()
        elif key == ord("k") or key == curses.KEY_UP:
            buf.move_up()
        elif key == ord("l") or key == curses.KEY_RIGHT:
            buf.move_right()
        elif key == curses.KEY_PPAGE:
            for _ in range(20):
                buf.move_up()
        elif key == curses.KEY_NPAGE:
            for _ in range(20):
                buf.move_down()
        elif key == ord("i"):
            self.mode = "INSERT"
            self.message = ""
        elif key == ord("a"):
            buf.move_right()
            self.mode = "INSERT"
        elif key == ord("o"):
            buf.open_line_below()
            self.mode = "INSERT"
        elif key == ord("x"):
            buf.delete_char()
        elif key == ord("u"):
            buf.undo()
        elif key == ord("G"):
            buf.goto_last_line()
        elif key == ord("g"):
            # 'gg' = first line; a lone 'g' waits for the next key.
            nxt = self.stdscr.getch()
            if nxt == ord("g"):
                buf.goto_first_line()
        elif key == ord("/"):
            pattern = self.prompt("/")
            if pattern is not None:
                if pattern and not buf.find_next(pattern):
                    self.message = "Pattern not found"
                else:
                    self.message = ""
        elif key == ord("n"):
            if buf.last_search and not buf.find_next(buf.last_search):
                self.message = "Pattern not found"
        elif key == ord("N"):
            if buf.last_search and not buf.find_prev(buf.last_search):
                self.message = "Pattern not found"
        elif key == ord(":"):
            cmd = self.prompt(":")
            if cmd is not None:
                self.run_command(cmd)
        elif key == ord("d"):
            nxt = self.stdscr.getch()
            if nxt == ord("d"):
                buf.delete_line()
        # Esc and anything else: no-op in Normal mode.

    def handle_insert(self, key):
        buf = self.buf
        if key == 27:  # Esc -> Normal
            buf.move_left()
            self.mode = "NORMAL"
        elif key in (10, 13):
            buf.insert_newline()
        elif key in (127, 8, curses.KEY_BACKSPACE):
            buf.backspace()
        elif key == curses.KEY_LEFT:
            buf.move_left()
        elif key == curses.KEY_RIGHT:
            buf.move_right()
        elif key == curses.KEY_UP:
            buf.move_up()
        elif key == curses.KEY_DOWN:
            buf.move_down()
        elif key == 9:
            buf.insert_char("\t")
        elif 32 <= key < 127:
            buf.insert_char(chr(key))
        # Other control keys are ignored in Insert mode.

    def draw(self):
        rows, cols = self.stdscr.getmaxyx()
        height = max(1, rows - 1)
        self.buf.ensure_visible(height, cols)
        lines = self.buf.render_screen(height, cols)
        self.stdscr.erase()
        for i, line in enumerate(lines):
            try:
                self.stdscr.addstr(i, 0, line)
            except curses.error:
                pass
        status = self.buf.status(self.mode, self.message)
        try:
            self.stdscr.addstr(rows - 1, 0, status[: cols - 1])
        except curses.error:
            pass
        cur_row = self.buf.row - self.buf.row_offset
        cur_col = self.buf.cursor_display_col() - self.buf.col_offset
        try:
            self.stdscr.move(cur_row, cur_col)
        except curses.error:
            pass
        self.stdscr.refresh()

    def run(self):
        while not self.quit:
            self.draw()
            key = self.stdscr.getch()
            if self.mode == "INSERT":
                self.handle_insert(key)
            else:
                self.handle_normal(key)


def main(argv):
    buf = Buffer()
    new_file = False
    if len(argv) > 1:
        path = argv[1]
        try:
            buf.load(path)
        except FileNotFoundError:
            buf.filename = path
            new_file = True
        except (OSError, UnicodeDecodeError) as exc:
            print(f"ccvim: cannot open {path}: {exc}", file=sys.stderr)
            return 1

    def _run(stdscr):
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        ui = EditorUI(stdscr, buf)
        if new_file:
            ui.message = "New file"
        ui.run()

    curses.wrapper(_run)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

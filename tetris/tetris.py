#!/usr/bin/env python3
"""Terminal Tetris — Build Your Own Tetris (codingchallenges.fyi).

Python 3 standard library only. All game rules are pure functions /
methods with no I/O, so they are fully unit-testable without a
terminal. The curses UI at the bottom only reads keys and draws
strings produced by render_text().

Run:  python3 tetris.py
Help: python3 tetris.py --help
"""

import random
import sys
import time

WIDTH = 10
HEIGHT = 20

# Each tetromino as rows of '#' (filled) / '.' (empty).
SHAPES = {
    "I": ("####",),
    "O": ("##",
          "##"),
    "T": (".#.",
          "###"),
    "S": (".##",
          "##."),
    "Z": ("##.",
          ".##"),
    "J": ("#..",
          "###"),
    "L": ("..#",
          "###"),
}

# Points per lock clearing n rows, multiplied by current level.
LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}


def _strip(shape):
    """Remove all-empty outer rows and columns from a shape."""
    rows = [row for row in shape if "#" in row]
    if not rows:
        return shape
    left = min(row.index("#") for row in rows)
    right = max(row.rindex("#") for row in rows)
    return tuple(row[left:right + 1] for row in rows)


def rotate_cw(shape):
    """Rotate a shape matrix 90 degrees clockwise."""
    rotated = tuple("".join(col) for col in zip(*shape[::-1]))
    return _strip(rotated)


def rotate_ccw(shape):
    """Rotate a shape matrix 90 degrees anti-clockwise."""
    rotated = tuple("".join(col) for col in zip(*shape))[::-1]
    return _strip(rotated)


def cells_of(shape):
    """Filled (dx, dy) offsets of a shape."""
    return [(x, y) for y, row in enumerate(shape)
            for x, cell in enumerate(row) if cell == "#"]


def empty_board():
    return [[0] * WIDTH for _ in range(HEIGHT)]


def collides(board, shape, px, py):
    """True if shape at (px, py) would leave the board or overlap."""
    for dx, dy in cells_of(shape):
        x, y = px + dx, py + dy
        if x < 0 or x >= WIDTH or y >= HEIGHT:
            return True
        if y >= 0 and board[y][x]:
            return True
    return False


def lock_piece(board, shape, px, py, letter):
    """Write a piece's cells into the board (in place)."""
    for dx, dy in cells_of(shape):
        x, y = px + dx, py + dy
        if 0 <= y < HEIGHT and 0 <= x < WIDTH:
            board[y][x] = letter
    return board


def clear_lines(board):
    """Remove full rows; return (new board, rows cleared)."""
    kept = [row for row in board if not all(row)]
    cleared = HEIGHT - len(kept)
    return [[0] * WIDTH for _ in range(cleared)] + kept, cleared


def level_for(lines):
    return lines // 10 + 1


def gravity_interval(level):
    """Seconds per gravity step; faster each level, floor 0.05s."""
    return max(0.05, 0.8 * 0.7 ** (level - 1))


def score_for_lines(n, level):
    return LINE_SCORES.get(n, 0) * level


class Piece:
    def __init__(self, kind, shape, x, y):
        self.kind = kind
        self.shape = shape
        self.x = x
        self.y = y

    def rotated(self, direction):
        shape = rotate_cw(self.shape) if direction == "cw" \
            else rotate_ccw(self.shape)
        return Piece(self.kind, shape, self.x, self.y)


class Game:
    """Pure Tetris state. No I/O: the UI owns timing and keys."""

    def __init__(self, pieces=None, rng=None):
        self.board = empty_board()
        self.score = 0
        self.lines = 0
        self.level = 1
        self.state = "playing"  # playing | paused | over
        self.rng = rng if rng is not None else random.Random()
        self._fixed = list(pieces) if pieces is not None else []
        self._fixed_index = 0
        self._bag = []
        self.upcoming = self._draw_kind()
        self.current = None
        self.spawn()

    def _draw_kind(self):
        if self._fixed_index < len(self._fixed):
            kind = self._fixed[self._fixed_index]
            self._fixed_index += 1
            return kind
        if not self._bag:
            self._bag = list(SHAPES)
            self.rng.shuffle(self._bag)
        return self._bag.pop()

    def spawn(self):
        if self.state == "over":
            return
        kind = self.upcoming
        self.upcoming = self._draw_kind()
        shape = SHAPES[kind]
        x = (WIDTH - len(shape[0])) // 2
        self.current = Piece(kind, shape, x, 0)
        if collides(self.board, shape, x, 0):
            self.state = "over"

    def _lock_and_spawn(self):
        lock_piece(self.board, self.current.shape,
                   self.current.x, self.current.y, self.current.kind)
        self.board, cleared = clear_lines(self.board)
        if cleared:
            self.score += score_for_lines(cleared, self.level)
            self.lines += cleared
            self.level = level_for(self.lines)
        self.spawn()

    def move(self, dx):
        """Shift horizontally if free. Returns True if moved."""
        if self.state != "playing" or self.current is None:
            return False
        nx = self.current.x + dx
        if collides(self.board, self.current.shape, nx, self.current.y):
            return False
        self.current.x = nx
        return True

    def rotate(self, direction="cw"):
        """Rotate if free. Returns True if rotated."""
        if self.state != "playing" or self.current is None:
            return False
        new = self.current.rotated(direction)
        if collides(self.board, new.shape, new.x, new.y):
            return False
        self.current.shape = new.shape
        return True

    def soft_drop(self):
        """One row down (+1 point); locks if it cannot move."""
        if self.state != "playing" or self.current is None:
            return False
        if collides(self.board, self.current.shape,
                    self.current.x, self.current.y + 1):
            self._lock_and_spawn()
            return False
        self.current.y += 1
        self.score += 1
        return True

    def hard_drop(self):
        """Drop to the landing spot (+2 per cell), then lock."""
        if self.state != "playing" or self.current is None:
            return False
        distance = 0
        while not collides(self.board, self.current.shape,
                           self.current.x, self.current.y + 1):
            self.current.y += 1
            distance += 1
        self.score += 2 * distance
        self._lock_and_spawn()
        return True

    def tick(self):
        """One gravity step; locks and spawns on landing."""
        if self.state != "playing" or self.current is None:
            return
        if collides(self.board, self.current.shape,
                    self.current.x, self.current.y + 1):
            self._lock_and_spawn()
        else:
            self.current.y += 1


def render_text(game):
    """Full screen text: bordered board + side panel. Pure."""
    board = [row[:] for row in game.board]
    if game.current is not None:
        for dx, dy in cells_of(game.current.shape):
            x, y = game.current.x + dx, game.current.y + dy
            if 0 <= y < HEIGHT and 0 <= x < WIDTH:
                board[y][x] = game.current.kind
    lines = ["+" + "-" * WIDTH + "+"]
    for row in board:
        lines.append("|" + "".join(str(c) if c else " " for c in row) + "|")
    lines.append("+" + "-" * WIDTH + "+")
    panel = ["Score: %d" % game.score,
             "Level: %d" % game.level,
             "Lines: %d" % game.lines,
             "",
             "Next: %s" % game.upcoming]
    panel += list(SHAPES[game.upcoming])
    if game.state == "paused":
        panel += ["", "PAUSED - p to resume"]
    if game.state == "over":
        panel += ["", "GAME OVER", "r restart, q quit"]
    width = max(len(line) for line in lines)
    out = []
    for i, line in enumerate(lines):
        side = panel[i] if i < len(panel) else ""
        out.append(line.ljust(width) + "  " + side)
    return "\n".join(out)


HELP_TEXT = """TETRIS - HOW TO PLAY

Fill horizontal rows to clear them. Clearing several rows
at once scores more: 1 row = 100, 2 = 300, 3 = 500,
4 (Tetris) = 800, all times your level. Level rises
every 10 lines and pieces fall faster.

CONTROLS
  Left / Right   move
  Up or x        rotate clockwise
  z              rotate anti-clockwise
  Down           soft drop (+1 per cell)
  Space          hard drop (+2 per cell)
  p              pause / resume
  q              quit

Press any key to go back.
"""

WELCOME_TEXT = """TETRIS

  Press ENTER or s to start
  Press h for instructions
  Press q to quit
"""


def _draw(stdscr, text):
    stdscr.clear()
    for i, line in enumerate(text.splitlines()):
        try:
            stdscr.addstr(i, 0, line)
        except Exception:
            pass
    stdscr.refresh()


def _run_curses(stdscr):
    import curses
    try:
        curses.curs_set(0)
    except Exception:
        pass
    stdscr.nodelay(True)
    stdscr.keypad(True)

    def wait_screen(text):
        _draw(stdscr, text)
        stdscr.nodelay(False)
        key = stdscr.getch()
        stdscr.nodelay(True)
        return key

    while True:
        key = wait_screen(WELCOME_TEXT)
        if key in (ord("q"), 27):
            return
        if key in (ord("h"), ord("H")):
            wait_screen(HELP_TEXT)
            continue
        if key not in (ord("\n"), ord("\r"), ord("s"), ord("S"),
                       curses.KEY_ENTER):
            continue
        game = Game()
        last_fall = time.monotonic()
        while True:
            _draw(stdscr, render_text(game))
            if game.state == "over":
                stdscr.nodelay(False)
                key = stdscr.getch()
                stdscr.nodelay(True)
                if key == ord("r"):
                    break  # back to welcome; a new game starts there
                if key == ord("q"):
                    return
                continue
            key = stdscr.getch()
            while key != -1:
                if key == ord("q"):
                    return
                elif key == ord("p"):
                    game.state = "paused" if game.state == "playing" \
                        else "playing"
                    last_fall = time.monotonic()
                elif game.state == "playing":
                    if key == curses.KEY_LEFT:
                        game.move(-1)
                    elif key == curses.KEY_RIGHT:
                        game.move(1)
                    elif key in (curses.KEY_UP, ord("x"), ord("X")):
                        game.rotate("cw")
                    elif key in (ord("z"), ord("Z")):
                        game.rotate("ccw")
                    elif key == curses.KEY_DOWN:
                        game.soft_drop()
                        last_fall = time.monotonic()
                    elif key == ord(" "):
                        game.hard_drop()
                        last_fall = time.monotonic()
                key = stdscr.getch()
            if game.state == "playing" and \
                    time.monotonic() - last_fall >= \
                    gravity_interval(game.level):
                game.tick()
                last_fall = time.monotonic()
            time.sleep(0.02)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(
            "Usage: python3 tetris.py [--help]\n\n"
            "Terminal Tetris. Controls:\n"
            "  Left/Right move, Up/x rotate clockwise, z rotate\n"
            "  anti-clockwise, Down soft drop, Space hard drop,\n"
            "  p pause, q quit, r restart on the game-over screen.\n"
            "  h on the welcome screen shows instructions.\n")
        return 0
    if argv:
        sys.stderr.write("Unknown argument: %s\n" % argv[0])
        return 2
    import curses
    curses.wrapper(_run_curses)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

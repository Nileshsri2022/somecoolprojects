"""Terminal Minesweeper — Python 3 standard library only.

Game logic is pure and non-interactive (no input()/print()): it can
be fully unit tested without a terminal. The CLI input loop lives in
``play_game`` / ``main`` at the bottom.

Library coordinates are 0-based; the CLI converts 1-based user input.
"""

import argparse
import random
import sys
import time

DIFFICULTIES = {
    "beginner": (9, 9, 10),
    "intermediate": (16, 16, 40),
    "expert": (16, 30, 99),
}

PLAYING, WON, LOST = "playing", "won", "lost"


class Board:
    """Mutable game state. ``mines`` is a frozenset of (row, col)."""

    def __init__(self, rows, cols, mines):
        self.rows = rows
        self.cols = cols
        self.mines = frozenset(mines)
        self.revealed = set()
        self.flagged = set()
        self.status = PLAYING

    @property
    def mine_count(self):
        return len(self.mines)

    def in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols


def create_board(rows, cols, mine_count, seed=None, safe_cell=None):
    """Create a board with ``mine_count`` uniformly random mines.

    ``seed`` makes placement deterministic (``random.Random(seed)
    .sample`` over all cells). ``safe_cell``, if given, is excluded
    from placement — the first-click guarantee, up front.
    """
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    if not 0 <= mine_count < rows * cols:
        raise ValueError("mine_count must satisfy 0 <= n < rows*cols")
    if safe_cell is not None and not (0 <= safe_cell[0] < rows
                                      and 0 <= safe_cell[1] < cols):
        raise ValueError("safe_cell out of bounds")
    cells = [(r, c) for r in range(rows) for c in range(cols)
             if (r, c) != safe_cell]
    mines = random.Random(seed).sample(cells, mine_count)
    return Board(rows, cols, mines)


def neighbours(board, r, c):
    """In-bounds neighbours of (r, c) — up to 8 cells."""
    return [(nr, nc)
            for nr in (r - 1, r, r + 1)
            for nc in (c - 1, c, c + 1)
            if (nr, nc) != (r, c) and board.in_bounds(nr, nc)]


def neighbour_count(board, r, c):
    """Mines adjacent to (r, c); None if the cell itself is a mine."""
    if (r, c) in board.mines:
        return None
    return sum((nr, nc) in board.mines for nr, nc in neighbours(board, r, c))


def _check_win(board):
    if len(board.revealed) == board.rows * board.cols - board.mine_count:
        board.status = WON


def reveal(board, r, c):
    """Reveal a cell. Returns 'ok', 'mine', or 'ignored'.

    Flood-reveals iteratively through 0-count cells (no recursion,
    so large empty boards are safe). Flagged, already-revealed,
    out-of-bounds, and post-game cells are ignored.
    """
    if board.status != PLAYING:
        return "ignored"
    if not board.in_bounds(r, c):
        return "ignored"
    if (r, c) in board.revealed or (r, c) in board.flagged:
        return "ignored"
    if (r, c) in board.mines:
        board.revealed.add((r, c))
        board.status = LOST
        return "mine"
    stack = [(r, c)]
    while stack:
        cr, cc = stack.pop()
        if (cr, cc) in board.revealed or (cr, cc) in board.flagged:
            continue
        board.revealed.add((cr, cc))
        if neighbour_count(board, cr, cc) == 0:
            stack.extend(n for n in neighbours(board, cr, cc)
                         if n not in board.revealed)
    _check_win(board)
    return "ok"


def toggle_flag(board, r, c):
    """Toggle a flag on a hidden cell. True if anything changed."""
    if board.status != PLAYING:
        return False
    if not board.in_bounds(r, c) or (r, c) in board.revealed:
        return False
    if (r, c) in board.flagged:
        board.flagged.remove((r, c))
    else:
        board.flagged.add((r, c))
    return True


def ensure_safe_first_click(board, cell):
    """Move the mine off ``cell`` if present, preserving mine count.

    The mine goes to the first mine-free cell in row-major order.
    A no-op when ``cell`` was already safe. Used by the CLI so the
    first reveal can never lose; library callers can instead pass
    ``safe_cell`` to ``create_board``.
    """
    if cell not in board.mines:
        return
    for r in range(board.rows):
        for c in range(board.cols):
            if (r, c) not in board.mines and (r, c) != cell:
                mines = set(board.mines)
                mines.remove(cell)
                mines.add((r, c))
                board.mines = frozenset(mines)
                return


def mines_remaining(board):
    return board.mine_count - len(board.flagged)


def render(board, reveal_mines=False):
    """Text board. Hidden '.', flagged 'F', mine '*', 0-count blank."""
    show_mines = reveal_mines or board.status == LOST
    width = len(str(board.cols))
    lines = ["Mines remaining: %d" % mines_remaining(board)]
    lines.append(" " * (width + 1) +
                 " ".join(str(c + 1).rjust(width) for c in range(board.cols)))
    for r in range(board.rows):
        cells = []
        for c in range(board.cols):
            if (r, c) in board.flagged:
                cells.append("F".rjust(width))
            elif (r, c) in board.revealed and (r, c) in board.mines:
                cells.append("*".rjust(width))
            elif (r, c) in board.revealed:
                n = neighbour_count(board, r, c)
                cells.append((" " if n == 0 else str(n)).rjust(width))
            elif show_mines and (r, c) in board.mines:
                cells.append("*".rjust(width))
            else:
                cells.append(".".rjust(width))
        lines.append(str(r + 1).rjust(width) + " " + " ".join(cells))
    return "\n".join(lines)


# --- CLI (all I/O lives here) -------------------------------------------

HELP = ("Commands: r <row> <col> reveal | f <row> <col> flag/unflag | "
        "h help | q quit (rows/cols are 1-based)")


def play_game(rows, cols, mine_count, seed=None):
    board = create_board(rows, cols, mine_count, seed=seed)
    first_move = True
    start = time.monotonic()
    print(render(board))
    print(HELP)
    while board.status == PLAYING:
        try:
            parts = input("> ").split()
        except EOFError:
            print()
            return False
        if not parts:
            continue
        cmd = parts[0].lower()
        if cmd == "q":
            return False
        if cmd == "h":
            print(HELP)
            continue
        if cmd not in ("r", "f") or len(parts) != 3:
            print("Unknown command. " + HELP)
            continue
        try:
            r, c = int(parts[1]) - 1, int(parts[2]) - 1
        except ValueError:
            print("Row and column must be numbers. " + HELP)
            continue
        if not board.in_bounds(r, c):
            print("Out of bounds.")
            continue
        if cmd == "r":
            if first_move:
                ensure_safe_first_click(board, (r, c))
                first_move = False
            result = reveal(board, r, c)
            if result == "ignored":
                print("Cannot reveal that cell (flagged or already open).")
        else:
            if not toggle_flag(board, r, c):
                print("Cannot flag that cell (already open).")
        print(render(board))
    elapsed = time.monotonic() - start
    if board.status == WON:
        print("You win! Time: %.1f seconds." % elapsed)
    else:
        print("Boom! You hit a mine. Time: %.1f seconds." % elapsed)
    try:
        again = input("Play again? [y/N] ").strip().lower()
    except EOFError:
        return False
    return again in ("y", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Terminal Minesweeper")
    parser.add_argument("--difficulty", choices=DIFFICULTIES,
                        default="beginner")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--cols", type=int)
    parser.add_argument("--mines", type=int)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)
    rows, cols, mines = DIFFICULTIES[args.difficulty]
    if args.rows is not None:
        rows = args.rows
    if args.cols is not None:
        cols = args.cols
    if args.mines is not None:
        mines = args.mines
    try:
        while play_game(rows, cols, mines, seed=args.seed):
            pass
    except ValueError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

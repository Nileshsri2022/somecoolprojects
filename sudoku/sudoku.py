"""Terminal Sudoku: board, validation, backtracking solver, puzzle
generation, and an input loop. Standard library only.

Board: list of 9 lists of 9 ints; 0 means empty. Coordinates inside
this module are 0-based; the CLI converts from 1-based input.
All game logic is pure (no I/O) except main()/play().
"""

import random
import sys

SIZE = 9
BOX = 3
EMPTY = 0

DIFFICULTIES = {"easy": 40, "medium": 32, "hard": 28}

# A well-known puzzle and its solution, used by --help text examples
# and the test suite.
EXAMPLE_PUZZLE = (
    "530070000600195000098000060800060003400803001700020006"
    "060000280000419005000080079"
)
EXAMPLE_SOLUTION = (
    "534678912672195348198342567859761423426853791713924856"
    "961537284287419635345286179"
)


def empty_board():
    return [[EMPTY] * SIZE for _ in range(SIZE)]


def copy_board(board):
    return [row[:] for row in board]


def parse_board(text):
    """Parse an 81-char string (digits, '0' or '.' = empty)."""
    text = text.strip()
    if len(text) != SIZE * SIZE:
        raise ValueError("puzzle must be exactly 81 characters")
    board = empty_board()
    for i, ch in enumerate(text):
        if ch in "0.":
            value = EMPTY
        elif ch in "123456789":
            value = int(ch)
        else:
            raise ValueError("invalid character %r in puzzle" % ch)
        board[i // SIZE][i % SIZE] = value
    return board


def board_to_string(board):
    return "".join(str(v) for row in board for v in row)


def box_index(row, col):
    return (row // BOX) * BOX + col // BOX


def _in_range(row, col):
    return 0 <= row < SIZE and 0 <= col < SIZE


def is_valid_move(board, row, col, value):
    """True iff placing value (1-9) in the empty cell is legal."""
    if not _in_range(row, col) or value not in range(1, SIZE + 1):
        return False
    if board[row][col] != EMPTY:
        return False
    if value in board[row]:
        return False
    if any(board[r][col] == value for r in range(SIZE)):
        return False
    br, bc = (row // BOX) * BOX, (col // BOX) * BOX
    return all(
        board[r][c] != value
        for r in range(br, br + BOX)
        for c in range(bc, bc + BOX)
    )


def is_valid_board(board):
    """No duplicate non-zero digit in any row, column, or box."""
    for i in range(SIZE):
        row = [v for v in board[i] if v != EMPTY]
        if len(row) != len(set(row)):
            return False
        col = [board[r][i] for r in range(SIZE) if board[r][i] != EMPTY]
        if len(col) != len(set(col)):
            return False
    for br in range(0, SIZE, BOX):
        for bc in range(0, SIZE, BOX):
            box = [
                board[r][c]
                for r in range(br, br + BOX)
                for c in range(bc, bc + BOX)
                if board[r][c] != EMPTY
            ]
            if len(box) != len(set(box)):
                return False
    return True


def is_complete(board):
    return all(v != EMPTY for row in board for v in row)


def is_solved(board):
    return is_complete(board) and is_valid_board(board)


def find_empty(board):
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] == EMPTY:
                return (r, c)
    return None


def _solve_in_place(board, candidates=None):
    """Backtracking solver; mutates board. True iff solved."""
    cell = find_empty(board)
    if cell is None:
        return is_valid_board(board)
    row, col = cell
    values = list(candidates) if candidates is not None else list(range(1, SIZE + 1))
    for value in values:
        if is_valid_move(board, row, col, value):
            board[row][col] = value
            if _solve_in_place(board, candidates):
                return True
            board[row][col] = EMPTY
    return False


def solve(board):
    """Return a solved copy of board, or None if unsolvable/invalid."""
    if not is_valid_board(board):
        return None
    result = copy_board(board)
    return result if _solve_in_place(result) else None


def count_solutions(board, limit=2):
    """Count solutions up to limit (early exit; limit=2 proves uniqueness)."""
    if not is_valid_board(board):
        return 0
    working = copy_board(board)
    count = [0]

    def search():
        if count[0] >= limit:
            return
        cell = find_empty(working)
        if cell is None:
            count[0] += 1
            return
        row, col = cell
        for value in range(1, SIZE + 1):
            if is_valid_move(working, row, col, value):
                working[row][col] = value
                search()
                working[row][col] = EMPTY
                if count[0] >= limit:
                    return

    search()
    return count[0]


def generate_full_board(rng):
    """Random solved board: backtracking with shuffled candidates."""
    board = empty_board()

    def fill():
        cell = find_empty(board)
        if cell is None:
            return True
        row, col = cell
        values = list(range(1, SIZE + 1))
        rng.shuffle(values)
        for value in values:
            if is_valid_move(board, row, col, value):
                board[row][col] = value
                if fill():
                    return True
                board[row][col] = EMPTY
        return False

    if not fill():
        raise RuntimeError("failed to generate a solved board")
    return board


def generate_puzzle(difficulty="easy", seed=None):
    """Return (puzzle, solution). Removals keep a unique solution."""
    if difficulty not in DIFFICULTIES:
        raise ValueError("unknown difficulty %r (easy/medium/hard)" % difficulty)
    rng = random.Random(seed)
    solution = generate_full_board(rng)
    puzzle = copy_board(solution)
    target = DIFFICULTIES[difficulty]
    givens = SIZE * SIZE
    cells = [(r, c) for r in range(SIZE) for c in range(SIZE)]
    rng.shuffle(cells)
    for row, col in cells:
        if givens <= target:
            break
        saved = puzzle[row][col]
        puzzle[row][col] = EMPTY
        if count_solutions(puzzle, limit=2) == 1:
            givens -= 1
        else:
            puzzle[row][col] = saved
    return puzzle, solution


def fixed_grid(puzzle):
    return [[cell != EMPTY for cell in row] for row in puzzle]


def apply_move(board, fixed, row, col, value):
    """Pure move. Returns (new_board, error_or_None).

    value 0 clears the cell. Fixed cells cannot be set or cleared.
    """
    if not _in_range(row, col):
        return board, "row and column must be 1-9"
    if fixed[row][col]:
        return board, "that cell is a given and cannot be changed"
    if value == EMPTY:
        return clear_cell(board, fixed, row, col)
    if value not in range(1, SIZE + 1):
        return board, "digit must be 0-9"
    if not is_valid_move(board, row, col, value):
        return board, "that digit conflicts with its row, column, or box"
    new = copy_board(board)
    new[row][col] = value
    return new, None


def clear_cell(board, fixed, row, col):
    if not _in_range(row, col):
        return board, "row and column must be 1-9"
    if fixed[row][col]:
        return board, "that cell is a given and cannot be changed"
    new = copy_board(board)
    new[row][col] = EMPTY
    return new, None


def format_board(board, fixed=None):
    """Text grid; '.' for empty, separators every 3 rows/columns."""
    lines = []
    for r in range(SIZE):
        if r and r % BOX == 0:
            lines.append("-" * 21)
        cells = []
        for c in range(SIZE):
            if c and c % BOX == 0:
                cells.append("|")
            v = board[r][c]
            cells.append(str(v) if v != EMPTY else ".")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def parse_command(line):
    """Parse one input line. Returns a tuple; raises ValueError."""
    parts = line.split()
    if not parts:
        raise ValueError("empty command (type 'help')")
    cmd = parts[0].lower()
    if cmd in ("quit", "q", "exit"):
        if len(parts) != 1:
            raise ValueError("'quit' takes no arguments")
        return ("quit",)
    if cmd == "help":
        if len(parts) != 1:
            raise ValueError("'help' takes no arguments")
        return ("help",)
    if cmd == "check":
        if len(parts) != 1:
            raise ValueError("'check' takes no arguments")
        return ("check",)
    if cmd == "solve":
        if len(parts) != 1:
            raise ValueError("'solve' takes no arguments")
        return ("solve",)
    if cmd == "new":
        if len(parts) > 2:
            raise ValueError("usage: new [easy|medium|hard]")
        difficulty = parts[1].lower() if len(parts) == 2 else None
        if difficulty is not None and difficulty not in DIFFICULTIES:
            raise ValueError("unknown difficulty %r" % difficulty)
        return ("new", difficulty)
    if cmd == "clear":
        if len(parts) != 3:
            raise ValueError("usage: clear <row> <col>")
        try:
            row, col = int(parts[1]), int(parts[2])
        except ValueError:
            raise ValueError("row and column must be numbers")
        if not (1 <= row <= SIZE and 1 <= col <= SIZE):
            raise ValueError("row and column must be 1-9")
        return ("clear", row - 1, col - 1)
    # Bare move: "r c v"
    if len(parts) == 3:
        try:
            row, col, value = (int(p) for p in parts)
        except ValueError:
            raise ValueError("move must be numbers: <row> <col> <digit>")
        if not (1 <= row <= SIZE and 1 <= col <= SIZE):
            raise ValueError("row and column must be 1-9")
        if not (0 <= value <= SIZE):
            raise ValueError("digit must be 0-9")
        return ("move", row - 1, col - 1, value)
    raise ValueError("unknown command %r (type 'help')" % cmd)


HELP_TEXT = """Commands (rows/cols 1-9):
  r c v          place digit v at row r, column c (v = 0 clears)
  clear r c      clear a cell you set
  check          say whether the puzzle is solved
  solve          fill the board with the solution
  new [difficulty]  fresh puzzle (easy/medium/hard)
  help           this text
  quit           exit
Givens cannot be changed."""


def play(difficulty):
    puzzle, _solution = generate_puzzle(difficulty)
    board, fixed = puzzle, fixed_grid(puzzle)
    print(format_board(board))
    print("Type 'help' for commands.")
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            break
        try:
            command = parse_command(line)
        except ValueError as exc:
            print("Error:", exc)
            continue
        kind = command[0]
        if kind == "quit":
            break
        if kind == "help":
            print(HELP_TEXT)
        elif kind == "check":
            print("Solved! Well done." if is_solved(board) else "Not solved yet.")
        elif kind == "solve":
            solved = solve(board)
            if solved is None:
                print("No solution exists for this board.")
            else:
                board = solved
                print(format_board(board))
        elif kind == "new":
            puzzle, _solution = generate_puzzle(command[1] or difficulty)
            board, fixed = puzzle, fixed_grid(puzzle)
            print(format_board(board))
        elif kind == "clear":
            board, error = clear_cell(board, fixed, command[1], command[2])
            print("Error: %s" % error if error else format_board(board))
        elif kind == "move":
            board, error = apply_move(board, fixed, *command[1:])
            if error:
                print("Error:", error)
            else:
                print(format_board(board))
                if is_solved(board):
                    print("Solved! Well done.")
                    break
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print("usage: sudoku.py [easy|medium|hard]")
        print("       sudoku.py --solve '<81 chars>'")
        return 0
    if argv and argv[0] == "--solve":
        if len(argv) != 2:
            print("usage: sudoku.py --solve '<81 chars>'", file=sys.stderr)
            return 2
        try:
            board = parse_board(argv[1])
        except ValueError as exc:
            print("Error:", exc, file=sys.stderr)
            return 2
        solved = solve(board)
        if solved is None:
            print("Error: puzzle has no solution", file=sys.stderr)
            return 1
        print(format_board(solved))
        return 0
    if len(argv) > 1:
        print("usage: sudoku.py [easy|medium|hard]", file=sys.stderr)
        return 2
    difficulty = argv[0] if argv else "easy"
    if difficulty not in DIFFICULTIES:
        print("unknown difficulty %r (easy/medium/hard)" % difficulty, file=sys.stderr)
        return 2
    return play(difficulty)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Terminal chess: full rules + random / minimax computer opponents.

Pure functions (board, rules, FEN, engine) contain no I/O, so the
unit tests exercise them without a terminal. The CLI at the bottom
is a thin loop over those functions.

Board: list of 8 rows, row 0 = rank 8. Squares are '.' or a
character: white PNBRQK, black pnbrqk. A square is (row, col),
row 0..7 top-to-bottom, col 0..7 = files a..h.
A move is (from_sq, to_sq, promotion) with promotion None or one
of 'q', 'r', 'b', 'n' (lowercase; colour comes from the mover).

Usage: python3 chess.py [--computer random|minimax] [--depth N]
         [--seed N] [--ascii] [FEN]
Moves are entered in UCI: e2e4, e7e8q. Castling is the king move:
e1g1, e1c1, e8g8, e8c8. Commands: moves, fen, undo, quit.
"""

import argparse
import random
import sys

WHITE = "w"
BLACK = "b"
EMPTY = "."

KNIGHT_OFFSETS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                   (1, -2), (1, 2), (2, -1), (2, 1))
KING_OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1))
ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))
VALUES = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 0}
MATE = 100000


# ---------------------------------------------------------------- squares

def parse_square(name):
    """'e4' -> (row, col); raises ValueError on bad input."""
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError("bad square: %r" % (name,))
    return 8 - int(name[1]), ord(name[0]) - ord("a")


def square_name(sq):
    """(row, col) -> 'e4'."""
    row, col = sq
    return chr(ord("a") + col) + str(8 - row)


def on_board(row, col):
    return 0 <= row < 8 and 0 <= col < 8


def piece_color(piece):
    if piece == EMPTY:
        return None
    return WHITE if piece.isupper() else BLACK


def opponent(color):
    return BLACK if color == WHITE else WHITE


# ---------------------------------------------------------------- state

def starting_board():
    back = "RNBQKBNR"
    board = [[EMPTY] * 8 for _ in range(8)]
    board[0] = list(back.lower())
    board[1] = list("pppppppp")
    board[6] = list("PPPPPPPP")
    board[7] = list(back)
    return board


class GameState:
    def __init__(self, board=None, turn=WHITE, castling=None,
                 en_passant=None, halfmove=0, fullmove=1):
        self.board = board if board is not None else starting_board()
        self.turn = turn
        self.castling = set(castling) if castling else set()
        self.en_passant = en_passant
        self.halfmove = halfmove
        self.fullmove = fullmove

    def copy(self):
        return GameState([row[:] for row in self.board], self.turn,
                         self.castling, self.en_passant,
                         self.halfmove, self.fullmove)

    def __eq__(self, other):
        return (isinstance(other, GameState)
                and self.board == other.board and self.turn == other.turn
                and self.castling == other.castling
                and self.en_passant == other.en_passant)


def start_position():
    return GameState(castling={"K", "Q", "k", "q"})


def from_fen(fen):
    """Parse a FEN string into a GameState."""
    parts = fen.strip().split()
    if len(parts) < 4:
        raise ValueError("bad FEN: %r" % (fen,))
    rows = parts[0].split("/")
    if len(rows) != 8:
        raise ValueError("bad FEN placement: %r" % (fen,))
    board = []
    for row_text in rows:
        row = []
        for ch in row_text:
            if ch.isdigit():
                row.extend([EMPTY] * int(ch))
            elif ch in "PNBRQKpnbrqk":
                row.append(ch)
            else:
                raise ValueError("bad FEN piece: %r" % (ch,))
        if len(row) != 8:
            raise ValueError("bad FEN row: %r" % (row_text,))
        board.append(row)
    if parts[1] not in (WHITE, BLACK):
        raise ValueError("bad FEN side to move: %r" % (parts[1],))
    castling = set() if parts[2] == "-" else set(parts[2])
    if not castling <= {"K", "Q", "k", "q"}:
        raise ValueError("bad FEN castling: %r" % (parts[2],))
    en_passant = None if parts[3] == "-" else parse_square(parts[3])
    halfmove = int(parts[4]) if len(parts) > 4 else 0
    fullmove = int(parts[5]) if len(parts) > 5 else 1
    return GameState(board, parts[1], castling, en_passant,
                     halfmove, fullmove)


def to_fen(state):
    rows = []
    for row in state.board:
        text, empty = "", 0
        for sq in row:
            if sq == EMPTY:
                empty += 1
            else:
                if empty:
                    text += str(empty)
                    empty = 0
                text += sq
        if empty:
            text += str(empty)
        rows.append(text)
    castling = "".join(c for c in "KQkq" if c in state.castling) or "-"
    en_passant = "-" if state.en_passant is None else square_name(state.en_passant)
    return "%s %s %s %s %d %d" % ("/".join(rows), state.turn, castling,
                                  en_passant, state.halfmove, state.fullmove)


# ---------------------------------------------------------------- attacks

def find_king(board, color):
    target = "K" if color == WHITE else "k"
    for row in range(8):
        for col in range(8):
            if board[row][col] == target:
                return (row, col)
    return None


def is_square_attacked(board, sq, by):
    """True if any piece of colour `by` attacks square `sq`."""
    row, col = sq
    # Pawns: a white pawn attacking sq sits one row below it.
    pawn = "P" if by == WHITE else "p"
    pawn_row = row + 1 if by == WHITE else row - 1
    for dcol in (-1, 1):
        if on_board(pawn_row, col + dcol) and board[pawn_row][col + dcol] == pawn:
            return True
    knight = "N" if by == WHITE else "n"
    for drow, dcol in KNIGHT_OFFSETS:
        r, c = row + drow, col + dcol
        if on_board(r, c) and board[r][c] == knight:
            return True
    king = "K" if by == WHITE else "k"
    for drow, dcol in KING_OFFSETS:
        r, c = row + drow, col + dcol
        if on_board(r, c) and board[r][c] == king:
            return True
    for directions, pieces in ((ORTHOGONAL, "RQ"), (DIAGONAL, "BQ")):
        want = tuple(p if by == WHITE else p.lower() for p in pieces)
        for drow, dcol in directions:
            r, c = row + drow, col + dcol
            while on_board(r, c):
                piece = board[r][c]
                if piece != EMPTY:
                    if piece in want:
                        return True
                    break
                r, c = r + drow, c + dcol
    return False


def is_in_check(state, color):
    king = find_king(state.board, color)
    return king is not None and is_square_attacked(
        state.board, king, opponent(color))


# ---------------------------------------------------------------- moves

def _pawn_moves(state, row, col):
    color = state.turn
    direction = -1 if color == WHITE else 1
    start_row = 6 if color == WHITE else 1
    last_row = 0 if color == WHITE else 7
    board = state.board
    moves = []
    one = (row + direction, col)
    if on_board(*one) and board[one[0]][one[1]] == EMPTY:
        if one[0] == last_row:
            moves.extend([( (row, col), one, p) for p in "qrbn"])
        else:
            moves.append(((row, col), one, None))
            two = (row + 2 * direction, col)
            if row == start_row and board[two[0]][two[1]] == EMPTY:
                moves.append(((row, col), two, None))
    for dcol in (-1, 1):
        target = (row + direction, col + dcol)
        if not on_board(*target):
            continue
        piece = board[target[0]][target[1]]
        if piece != EMPTY and piece_color(piece) == opponent(color):
            if target[0] == last_row:
                moves.extend([((row, col), target, p) for p in "qrbn"])
            else:
                moves.append(((row, col), target, None))
        elif target == state.en_passant:
            moves.append(((row, col), target, None))
    return moves


def _castling_moves(state, row, col):
    """Castling moves; check-safety is enforced here, not in the
    legal-move filter, because the filter only checks the king's
    destination square, not the square it passes through."""
    if state.turn == WHITE:
        rights, back_row, king_side, queen_side = "KQ", 7, "K", "Q"
    else:
        rights, back_row, king_side, queen_side = "kq", 0, "k", "q"
    if (row, col) != (back_row, 4):
        return []
    board, enemy = state.board, opponent(state.turn)
    moves = []
    if king_side in state.castling and board[back_row][5] == EMPTY \
            and board[back_row][6] == EMPTY \
            and board[back_row][7] == ("R" if state.turn == WHITE else "r") \
            and not is_in_check(state, state.turn) \
            and not is_square_attacked(board, (back_row, 5), enemy) \
            and not is_square_attacked(board, (back_row, 6), enemy):
        moves.append(((row, col), (back_row, 6), None))
    if queen_side in state.castling and board[back_row][3] == EMPTY \
            and board[back_row][2] == EMPTY and board[back_row][1] == EMPTY \
            and board[back_row][0] == ("R" if state.turn == WHITE else "r") \
            and not is_in_check(state, state.turn) \
            and not is_square_attacked(board, (back_row, 3), enemy) \
            and not is_square_attacked(board, (back_row, 2), enemy):
        moves.append(((row, col), (back_row, 2), None))
    return moves


def pseudo_legal_moves(state):
    """Moves by piece geometry only; may leave the king in check."""
    board, color = state.board, state.turn
    moves = []
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if piece == EMPTY or piece_color(piece) != color:
                continue
            kind = piece.upper()
            if kind == "P":
                moves.extend(_pawn_moves(state, row, col))
            elif kind == "N":
                for drow, dcol in KNIGHT_OFFSETS:
                    target = (row + drow, col + dcol)
                    if on_board(*target):
                        occupier = board[target[0]][target[1]]
                        if occupier == EMPTY or piece_color(occupier) == opponent(color):
                            moves.append(((row, col), target, None))
            elif kind in "BQ":
                directions = DIAGONAL + ORTHOGONAL if kind == "Q" else DIAGONAL
                for drow, dcol in directions:
                    r, c = row + drow, col + dcol
                    while on_board(r, c):
                        occupier = board[r][c]
                        if occupier == EMPTY:
                            moves.append(((row, col), (r, c), None))
                        else:
                            if piece_color(occupier) == opponent(color):
                                moves.append(((row, col), (r, c), None))
                            break
                        r, c = r + drow, c + dcol
            elif kind == "R":
                for drow, dcol in ORTHOGONAL:
                    r, c = row + drow, col + dcol
                    while on_board(r, c):
                        occupier = board[r][c]
                        if occupier == EMPTY:
                            moves.append(((row, col), (r, c), None))
                        else:
                            if piece_color(occupier) == opponent(color):
                                moves.append(((row, col), (r, c), None))
                            break
                        r, c = r + drow, c + dcol
            elif kind == "K":
                for drow, dcol in KING_OFFSETS:
                    target = (row + drow, col + dcol)
                    if on_board(*target):
                        occupier = board[target[0]][target[1]]
                        if occupier == EMPTY or piece_color(occupier) == opponent(color):
                            moves.append(((row, col), target, None))
                moves.extend(_castling_moves(state, row, col))
    return moves


def apply_move(state, move):
    """Return the new state after `move`; `state` is untouched."""
    from_sq, to_sq, promotion = move
    fr, fc = from_sq
    tr, tc = to_sq
    new = state.copy()
    board = new.board
    piece = board[fr][fc]
    color = piece_color(piece)
    captured = board[tr][tc]
    # En passant: the captured pawn sits beside the mover, not on
    # the destination square.
    if piece.upper() == "P" and to_sq == state.en_passant and captured == EMPTY:
        board[fr][tc] = EMPTY
        captured = "p" if color == WHITE else "P"
    board[tr][tc] = board[fr][fc]
    board[fr][fc] = EMPTY
    if promotion is not None:
        board[tr][tc] = promotion.upper() if color == WHITE else promotion
    # Castling: the king moved two squares, so move the rook too.
    if piece.upper() == "K" and abs(tc - fc) == 2:
        rook_from_col = 7 if tc > fc else 0
        rook_to_col = 5 if tc > fc else 3
        board[tr][rook_to_col] = board[tr][rook_from_col]
        board[tr][rook_from_col] = EMPTY
    # Castling rights: king move, rook move, or rook capture.
    if piece.upper() == "K":
        new.castling -= {"K", "Q"} if color == WHITE else {"k", "q"}
    for square, right in (((7, 0), "Q"), ((7, 7), "K"),
                          ((0, 0), "q"), ((0, 7), "k")):
        if from_sq == square or to_sq == square:
            new.castling.discard(right)
    # The passed square sits behind the pawn's destination: White
    # moves toward row 0, so it is one row above the start square.
    new.en_passant = (fr + (-1 if color == WHITE else 1), fc) \
        if piece.upper() == "P" and abs(tr - fr) == 2 else None
    new.halfmove = 0 if piece.upper() == "P" or captured != EMPTY \
        else state.halfmove + 1
    new.fullmove = state.fullmove + (1 if color == BLACK else 0)
    new.turn = opponent(color)
    return new


def legal_moves(state):
    """Pseudo-legal moves that do not leave the mover in check.
    This one filter also handles pins and moving into check."""
    color = state.turn
    return [m for m in pseudo_legal_moves(state)
            if not is_in_check(apply_move(state, m), color)]


def game_status(state):
    """'playing', 'checkmate', 'stalemate', or
    'draw_insufficient_material'."""
    moves = legal_moves(state)
    if not moves:
        return "checkmate" if is_in_check(state, state.turn) else "stalemate"
    minors = [p for row in state.board for p in row
              if p not in (EMPTY, "K", "k")]
    if not minors or (len(minors) == 1 and minors[0].upper() in "NB"):
        return "draw_insufficient_material"
    return "playing"


def perft(state, depth):
    """Node count of the move tree to `depth` (test helper)."""
    if depth == 0:
        return 1
    return sum(perft(apply_move(state, m), depth - 1)
               for m in legal_moves(state))


# ---------------------------------------------------------------- UCI

def move_to_uci(move):
    from_sq, to_sq, promotion = move
    return square_name(from_sq) + square_name(to_sq) + (promotion or "")


def parse_uci(state, text):
    """Parse a UCI string against `state`; raises ValueError."""
    text = text.strip().lower()
    if len(text) not in (4, 5):
        raise ValueError("bad move: %r" % (text,))
    from_sq, to_sq = parse_square(text[:2]), parse_square(text[2:4])
    piece = state.board[from_sq[0]][from_sq[1]]
    promotion = text[4] if len(text) == 5 else None
    if promotion is not None and promotion not in "qrbn":
        raise ValueError("bad promotion piece: %r" % (promotion,))
    last_row = 0 if piece_color(piece) == WHITE else 7
    if piece.upper() == "P" and to_sq[0] == last_row and promotion is None:
        raise ValueError("promotion move needs a piece letter, e.g. e7e8q")
    if promotion is not None and not (piece.upper() == "P"
                                      and to_sq[0] == last_row):
        raise ValueError("only a pawn reaching the last rank promotes")
    return (from_sq, to_sq, promotion)


def play_moves(state, uci_list):
    """Apply a list of UCI strings; raises ValueError on an illegal one."""
    for text in uci_list:
        move = parse_uci(state, text)
        if move not in legal_moves(state):
            raise ValueError("illegal move: %s" % (text,))
        state = apply_move(state, move)
    return state


# ---------------------------------------------------------------- engine

def evaluate(state):
    """Material score from White's perspective."""
    total = 0
    for row in state.board:
        for piece in row:
            if piece != EMPTY:
                value = VALUES[piece.lower()]
                total += value if piece.isupper() else -value
    return total


def _search(state, depth, alpha, beta, ply):
    status = game_status(state)
    if status == "checkmate":
        return -MATE + ply  # side to move is mated; sooner is worse
    if status != "playing":
        return 0  # stalemate / insufficient material: a draw
    if depth == 0:
        score = evaluate(state)
        return score if state.turn == WHITE else -score
    best = -MATE - 1
    for move in legal_moves(state):
        score = -_search(apply_move(state, move), depth - 1,
                         -beta, -alpha, ply + 1)
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def best_move(state, depth=2):
    """Deterministic minimax + alpha-beta move (first best on ties),
    or None on a terminal position."""
    best, best_score = None, -MATE - 1
    for move in legal_moves(state):
        score = -_search(apply_move(state, move), depth - 1,
                         -MATE - 1, MATE + 1, 1)
        if score > best_score:
            best, best_score = move, score
    return best


def random_move(state, rng=None):
    """Step 3 computer: a uniform random legal move, or None."""
    moves = legal_moves(state)
    if not moves:
        return None
    return (rng or random).choice(moves)


# ---------------------------------------------------------------- render / CLI

UNICODE = {"K": "\u2654", "Q": "\u2655", "R": "\u2656",
           "B": "\u2657", "N": "\u2658", "P": "\u2659",
           "k": "\u265a", "q": "\u265b", "r": "\u265c",
           "b": "\u265d", "n": "\u265e", "p": "\u265f", ".": "\u00b7"}


def render_board(state, ascii_pieces=False):
    lines = ["  a b c d e f g h"]
    for row in range(8):
        cells = []
        for piece in state.board[row]:
            cells.append(piece if ascii_pieces or piece == EMPTY
                         else UNICODE[piece])
        lines.append("%d %s %d" % (8 - row, " ".join(cells), 8 - row))
    lines.append("  a b c d e f g h")
    return "\n".join(lines)


def describe_status(state):
    status = game_status(state)
    side = "White" if state.turn == WHITE else "Black"
    if status == "checkmate":
        return "Checkmate! %s wins." % ("Black" if state.turn == WHITE else "White")
    if status == "stalemate":
        return "Stalemate — draw."
    if status == "draw_insufficient_material":
        return "Draw — insufficient material."
    if is_in_check(state, state.turn):
        return "%s to move (in check)." % side
    return "%s to move." % side


def main(argv=None):
    parser = argparse.ArgumentParser(description="Terminal chess.")
    parser.add_argument("fen", nargs="?", help="starting FEN position")
    parser.add_argument("--computer", choices=["random", "minimax"],
                        help="play against the computer (you are White)")
    parser.add_argument("--depth", type=int, default=2,
                        help="minimax search depth (default 2)")
    parser.add_argument("--seed", type=int, help="RNG seed for random mode")
    parser.add_argument("--ascii", action="store_true",
                        help="ASCII pieces instead of Unicode")
    args = parser.parse_args(argv)

    try:
        state = from_fen(args.fen) if args.fen else start_position()
    except ValueError as exc:
        print("Error: %s" % (exc,), file=sys.stderr)
        return 2
    rng = random.Random(args.seed) if args.seed is not None else random
    computer_color = BLACK if args.computer else None
    history = [state]

    while True:
        print(render_board(state, args.ascii))
        print(describe_status(state))
        if game_status(state) != "playing":
            break
        if computer_color is not None and state.turn == computer_color:
            move = random_move(state, rng) if args.computer == "random" \
                else best_move(state, args.depth)
            print("Computer plays %s" % move_to_uci(move))
            state = apply_move(state, move)
            history.append(state)
            continue
        try:
            line = input("Move (UCI, or moves/fen/undo/quit): ").strip()
        except EOFError:
            print()
            break
        if line in ("quit", "exit"):
            break
        if line == "moves":
            print(" ".join(move_to_uci(m) for m in legal_moves(state)))
            continue
        if line == "fen":
            print(to_fen(state))
            continue
        if line == "undo":
            if len(history) > 1:
                history.pop()
                state = history[-1]
            else:
                print("Nothing to undo.")
            continue
        try:
            move = parse_uci(state, line)
        except ValueError as exc:
            print("Invalid move: %s" % (exc,))
            continue
        if move not in legal_moves(state):
            print("Illegal move: %s" % (line,))
            continue
        state = apply_move(state, move)
        history.append(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# TEST_PLAN — Chess

Run from this directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests are pure (no terminal, no stdin/stdout, no randomness
except seeded `random.Random` instances). Positions are built
with `from_fen` or by playing UCI moves from the start position.

## Cases

Starting position & move counts:
- 20 legal moves for White; 20 for Black after 1. e4.
- Perft: depth 1 = 20, depth 2 = 400, depth 3 = 8902.
- Starting FEN round-trips through `from_fen`/`to_fen`.

Piece movement:
- Knight on an empty board: all 8 jumps; blocked by own piece,
  captures enemy piece.
- Bishop/rook/queen rays stop at own piece, capture first enemy
  piece, do not jump over pieces.
- King: one square in all directions; cannot move into check.
- Pawn: single push, double push only from starting rank,
  blocked push illegal, diagonal capture only onto an enemy
  piece, no forward capture, no sideways move without capture.

Special rules:
- En passant: legal only on the move immediately after the
  opponent's double push, and only onto the passed square;
  expires afterwards; the captured pawn is removed.
- Castling: kingside and queenside, both colours, when legal;
  illegal when rights lost (king/rook moved or rook captured),
  when squares between are occupied, when in check, or when
  passing through check; rook lands on the correct square.
- Promotion: pawn reaching the last rank must name a piece;
  all four promotions generated; promoted piece type lands on
  the board; a UCI move without a promotion letter is invalid.
- Pins: a pinned piece may not move if it would expose the king
  (legal-move filter), but may move along the pin line.
- Check: moving into check is illegal; a position in check
  offers only moves that resolve the check (capture, block, move).

Endings:
- Fool's mate (1. f3 e5 2. g4 Qh4#) -> checkmate, Black wins.
- Scholar's mate line is checkmate.
- Stalemate: `7k/5Q2/6K1/8/8/8/8/8 b - - 0 1` -> stalemate.
- Insufficient material: K vs K, K+N vs K, K+B vs K are draws;
  K+Q vs K is not.

FEN / UCI:
- `parse_uci` round-trips; bad squares, bad promotion letters,
  and missing promotion letters raise `ValueError`.
- Castling rights and en-passant square survive `to_fen`.

Engine:
- `random_move` always returns a legal move; seeded RNG gives
  the same move twice.
- `best_move` at depth 1 takes a free queen over a free pawn
  (material ordering); returns `None` on a terminal position.
- Minimax prefers checkmate over a material win (mate score).
- `evaluate` is zero-ish symmetric: `evaluate(state)` negated
  equals the value after swapping sides (sign check on a
  mirrored material position).

CLI (subprocess, piped stdin):
- Two-player game: playing `e2e4` then quitting exits 0 and
  prints the board.
- Invalid move is rejected and the game continues (quit after).
- `--computer random --seed 1` plays a legal reply to `e2e4`
  without hanging.

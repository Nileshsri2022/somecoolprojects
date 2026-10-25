# DESIGN — Chess

## Assumptions (stated before coding, per ponytail)

1. Python 3 standard library only; one main file, `chess.py`.
2. The page gives no move format, board encoding, or engine
   detail, so those choices are this file's, documented in SPEC.md.
3. Rules logic must be pure and terminal-free so unit tests can
   exercise it without a terminal: no `input()`/`print()` inside
   the rules or engine functions; the CLI is a thin loop on top.
4. Simplicity over speed: an 8x8 array of single characters, not
   bitboards (the page mentions bitboards as an option, not a
   requirement). Perft(3) = 8902 nodes runs in well under a second
   with this representation, so bitboards would be premature.

## Representation

- Board: list of 8 rows, row 0 = rank 8, row 7 = rank 1.
  Each square is `'.'` or one character: white `PNBRQK`,
  black `pnbrqk`. Uppercase = white, lowercase = black.
- Square: `(row, col)` tuple, row 0..7 top-to-bottom,
  col 0..7 = files a..h. Helpers `parse_square` / `square_name`
  convert to/from algebraic (`e4`).
- `GameState`: small class holding `board`, `turn` (`'w'`/`'b'`),
  `castling` (set of `'K'`, `'Q'`, `'k'`, `'q'`), `en_passant`
  (square tuple or `None`), `halfmove`, `fullmove`. It has a
  `copy()` method; `apply_move` returns a new state and never
  mutates its input, so the engine can search freely.
- Move: `(from_sq, to_sq, promotion)` tuple, where promotion is
  `None` or one of `'q'`, `'r'`, `'b'`, `'n'` (lowercase; colour
  is taken from the mover). `move_to_uci` / `parse_uci` convert.

## Move generation

Two layers, the standard approach:

1. `pseudo_legal_moves(state)` — moves by piece geometry only:
   sliding pieces walk rays until blocked; knights/kings use
   offset tables; pawns push/capture/double-push/en-passant and
   expand promotions to all four pieces; castling moves are
   emitted when rights are held and the intervening squares are
   empty (check-safety is filtered in layer 2).
2. `legal_moves(state)` — layer 1 filtered by applying each move
   and rejecting it if the mover's own king is left in check.
   This single filter also correctly handles pins and moving
   into check, with no special-casing.

`is_square_attacked(board, sq, by_colour)` answers "does this
colour attack this square?" for both check detection and the
castling through-check rule. It is written as: pawn attacks by
offset, knight/king by offset tables, sliders by ray walks —
checking attackers rather than generating all enemy moves, so it
stays cheap and cannot recurse into `legal_moves`.

## Game status

`game_status(state)` returns one of:
`'playing'`, `'checkmate'`, `'stalemate'`,
`'draw_insufficient_material'`, each derived from
`legal_moves` + `is_in_check` (+ a scan for remaining pieces).
Checkmate = in check with no legal moves; stalemate = not in
check with no legal moves.

## Engine

- `evaluate(state)`: material only, from White's perspective
  (P=100, N=320, B=330, R=500, Q=900, K=0). Checkmate is scored
  as +/-100000 adjusted by search depth (mate sooner is better).
- `best_move(state, depth)`: negamax with alpha-beta pruning.
  Ties keep the first move found, so results are deterministic.
- `random_move(state, rng)`: Step 3 computer — `rng.choice`
  over legal moves; a caller-supplied `random.Random` makes
  tests deterministic.
- No piece-square tables, no quiescence, no transposition table:
  depth 2 is instant, depth 3 is a few seconds at most on the
  starting position — enough for a casual opponent, and the
  code stays short and auditable.

## CLI

`python3 chess.py [--computer {random,minimax}] [--depth N]
[--seed N] [FEN]`. Loop: render board, print status, read a
line. Human lines are parsed as UCI and rejected (with the
reason) if illegal; the computer replies immediately. `undo`
pops the last ply; repeat it to undo further moves. Rendering uses Unicode chess glyphs with an
ASCII fallback (`--ascii`).

## Files

- `chess.py` — board, rules, FEN, engine, render, CLI.
- `tests/test_chess.py` — unittest suite (see TEST_PLAN.md).

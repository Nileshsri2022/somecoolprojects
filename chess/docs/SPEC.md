# SPEC — Chess (Coding Challenges entry 44)

Source: https://codingchallenges.fyi/challenges/challenge-chess/
(slug `challenge-chess`; first guess, no 404, no correction needed.)

## Challenge steps (as written on the page)

- Step 0: pick language/environment; represent board and pieces.
  The heart of the challenge is the chess engine.
- Step 1: display a chess board, pieces in starting positions.
- Step 2: validate possible moves for each piece, from its type,
  location, and surrounding pieces (page suggests TDD here).
- Step 3: player and computer move in turn; reject an invalid human
  move. Computer, for now: list all its legal moves, pick one at random.
- Step 4: after each move, check the winning condition; end the game
  when met.
- Step 5: build the engine: game tree + a pruning algorithm
  (minimax / alpha-beta / MCTS) so the computer looks ahead and
  can win games.

## What this build implements

- Full standard rules, all as pure, non-interactive functions:
  pawn moves (single, double from start, captures), en passant,
  promotion (to Q, R, B, N — the mover chooses), knight, bishop,
  rook, queen and king moves, castling (both sides, both colours,
  only when legal: rights held, squares empty, king not in, through
  or into check), check, checkmate, stalemate, and draw by
  insufficient material (king vs king, king + minor vs king).
- Move input: UCI, e.g. `e2e4`, `e7e8q` (promotion piece letter
  required when a pawn reaches the last rank), plus castling as
  ordinary king moves (`e1g1`, `e1c1`, `e8g8`, `e8c8`). The page
  names no input format, so UCI was chosen: it is unambiguous,
  unlike SAN, which would need disambiguation parsing.
- Terminal UI: printed board, side to move, prompt per move.
  Commands: a UCI move, `moves` (list legal moves), `fen`,
  `undo`, `quit`.
- Computer opponents, both built and tested (Step 3 and Step 5):
  `--computer random` (uniform pick over legal moves, seedable)
  and `--computer minimax` (material evaluation, alpha-beta,
  configurable depth, default 2). `--computer` defaults to minimax.
  Two-player mode is the default (no `--computer` flag).
- FEN import/export (`from_fen` / `to_fen`) for setting up test
  positions; the CLI accepts a starting FEN as an argument.

## Deliberate scope limits (divergences from full FIDE rules)

- No threefold-repetition or fifty-move draw: the page never
  mentions them, and they need game history in the pure state.
  The CLI keeps a move history for `undo` only, not for
  repetition claims.
- No draw offer, resignation, or clock: out of scope for the page.
- No SAN input, no GUI/curses UI, no opening book, no MCTS:
  alpha-beta over material satisfies Step 5's "look ahead"
  requirement at this scale; piece-square tables and quiescence
  search were left out as speculative extras (ponytail).
- Promotion without a piece letter is rejected as invalid
  (ambiguous), rather than silently defaulting to queen.
- Insufficient-material draw is a small extension beyond the
  page's "check for a win" step; it is standard, cheap, and tested.

## Success criteria

- Starting position: 20 legal moves; perft(2) = 400, perft(3) = 8902.
- Fool's mate (f3 e5 g4 Qh4#) is checkmate; the classic
  queen-vs-bare-king stalemate position is stalemate.
- Every rule above has at least one unit test; all tests pass
  with `python3 -m unittest discover -s tests -v` from this directory.

# chess — Build Your Own Chess Game

Coding Challenges #44, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal chess with full rules (castling, en passant, promotion,
check, checkmate, stalemate), plus two computer opponents:
a random mover (challenge Step 3) and a minimax + alpha-beta
engine (Step 5). Python 3 standard library only, one file.

## Usage

```sh
# Two-player game
python3 chess.py

# Against the computer (you play White, minimax depth 2)
python3 chess.py --computer minimax

# Against the random mover, or a deeper engine
python3 chess.py --computer random --seed 1
python3 chess.py --computer minimax --depth 3

# From a FEN position, ASCII pieces instead of Unicode
python3 chess.py --ascii "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
```

Enter moves in UCI: `e2e4`, `e7e8q` (promotion letter required).
Castling is just the king move: `e1g1`, `e1c1`, `e8g8`, `e8c8`.
Commands: `moves` (list legal moves), `fen`, `undo`, `quit`.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps (board display, move validation,
random/minimax computer, win detection): perft counts, every
piece's movement, en passant, castling, promotion, pins, check,
checkmate (Fool's and Scholar's mate), stalemate, insufficient
material, FEN/UCI round-trips, engine behaviour, and the CLI.

## Files

- `chess.py` — board, rules, FEN, engine, render, CLI.
- `docs/SPEC.md` — challenge steps and scope limits.
- `docs/DESIGN.md` — representation and design assumptions.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_chess.py` — the test suite.

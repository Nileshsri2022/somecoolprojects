# tetris — Build Your Own Tetris

Coding Challenges entry, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Terminal Tetris (Python 3 standard library only, `curses` for the
interactive UI). Board 10 x 20, seven tetrominoes in shuffled
7-bags, line clears, levels, scoring, game over + restart.

## Usage

```sh
python3 tetris.py            # play (welcome screen first)
python3 tetris.py --help     # controls, without starting the game
```

## Controls

| Key            | Action                        |
| -------------- | ----------------------------- |
| Left / Right   | Move piece                    |
| Up or `x`      | Rotate clockwise              |
| `z`            | Rotate anti-clockwise         |
| Down           | Soft drop (+1 point per cell) |
| Space          | Hard drop (+2 points per cell)|
| `p`            | Pause / resume                |
| `q`            | Quit                          |
| `r`            | Restart (game-over screen)    |
| `h`            | Help (welcome screen)         |

Scoring per lock (x current level): 1 row = 100, 2 = 300,
3 = 500, 4 (Tetris) = 800. Level rises every 10 lines cleared
and the pieces fall faster.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

All game logic (board, pieces, rotation, line clears, scoring,
levels, game over) is pure and covered by tests that run without
a terminal; only the thin curses UI in `tetris.py` needs one.

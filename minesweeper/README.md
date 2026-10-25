# minesweeper — Build Your Own Minesweeper

Coding Challenges: Build Your Own Minesweeper
(https://codingchallenges.fyi/challenges/challenge-minesweeper/)

Terminal Minesweeper in a single Python file, standard library only.
All game logic is pure, non-interactive functions, fully covered by
unit tests that run without a terminal; a text board + input loop
sits on top.

## Usage

```sh
python3 minesweeper.py                    # beginner: 9x9, 10 mines
python3 minesweeper.py --difficulty expert
python3 minesweeper.py --rows 5 --cols 5 --mines 3 --seed 7
```

In-game commands (rows/columns are 1-based):

```
r <row> <col>   reveal a cell
f <row> <col>   flag / unflag a cell
h               help
q               quit
```

The first cell you reveal is always safe. Win by revealing every
non-mine cell; hit a mine and all mines are shown. At game end you
are offered a fresh board.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover mine placement (seeded, exact count, safe cell),
neighbour counts, flood reveal, flagging, win/lose detection, and
board rendering — see `docs/TEST_PLAN.md`. Design notes and
documented divergences from the challenge page are in `docs/`.

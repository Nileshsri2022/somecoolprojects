# SPEC — Build Your Own Tetris

Source: https://codingchallenges.fyi/challenges/challenge-tetris/
Slug used: `tetris` (first guess, no 404, no correction needed).
Page steps covered: Step 0 (Python 3 stdlib, terminal) through Step 5.

## The game (from the page)

- Board 10 blocks wide, 20 blocks high, with a block border.
- Seven tetrominoes (I, O, T, S, Z, J, L), appearing in random order at
  the top and falling to the bottom; a piece stops when its lowest
  block reaches the bottom of the board (or lands on locked blocks).
- Player controls: move left/right, rotate clockwise and
  anti-clockwise, accelerate downwards (soft drop), hard drop
  (immediately as far down as possible).
- Completed rows disappear and update the score; clearing several
  rows at once scores more than the sum of the single rows
  (page example: one row 10 points, two rows 30, three rows 50).
- Game ends when the board is full — no more pieces can be added at
  the top. After a game ends the player may restart.
- Step 1: a welcome screen offering Start and Instructions
  (controls + gameplay intro). High scores are optional on the page
  ("you could even include some high scores") — NOT implemented
  (see DESIGN.md, divergences).

## Concrete behaviour specified here

- Board: 10 x 20 grid. Empty cell = 0; locked cell = the piece
  letter (`I`, `O`, `T`, `S`, `Z`, `J`, `L`).
- Spawn: new piece centred horizontally at the top row (y = 0,
  fully inside the board). If the spawn position collides with
  locked blocks, the game is over immediately.
- Piece order: 7-bag randomiser — each bag holds one of each of the
  seven pieces in shuffled order; a new bag starts when the previous
  one is exhausted. This satisfies the page's "order is random"
  while guaranteeing no long droughts of one piece.
- Locking: when a piece can no longer move down, it locks into the
  board, full rows are cleared, score/level update, and the next
  piece spawns.
- Scoring (per lock that clears rows; multiplied by current level):
  1 row = 100, 2 rows = 300, 3 rows = 500, 4 rows (Tetris) = 800.
  Soft drop = +1 point per cell descended; hard drop = +2 points
  per cell descended. Level = lines_cleared // 10 + 1.
- Gravity: the piece falls one row per gravity interval;
  interval = max(0.05, 0.8 * 0.7 ** (level - 1)) seconds, so the
  game speeds up as the level rises.
- Rotation: rotate the piece's cell matrix clockwise or
  anti-clockwise; a rotation that would collide or leave the board
  is rejected (piece stays as it was). No wall kicks — see
  divergences.
- Game over: spawn collision. The game-over screen offers restart
  (`r`) or quit (`q`).
- Controls (curses UI): Left/Right move, Up or `x` rotate
  clockwise, `z` rotate anti-clockwise, Down soft drop, Space hard
  drop, `p` pause/resume, `q` quit, `r` restart on the game-over
  screen, any key to leave the help screen.

## Out of scope

- No GUI (per task brief): terminal/curses only.
- No high-score persistence, no hold piece, no wall kicks, no
  hidden rows above the board. Each is a deliberate simplification
  recorded in DESIGN.md.

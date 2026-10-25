#!/usr/bin/env python3
"""Terminal Space Invaders (codingchallenges.fyi, challenge-space-invaders).

Pure game logic (``Game``, ``new_game``, ``step``, ``render`` and friends)
plus a thin curses shell. The logic never touches the terminal, so the
unit tests run without one. Python 3 standard library only.

Controls in the curses UI: Left / A move left, Right / D move right,
Space fires, Q quits, R starts a new game after game over.
"""

import argparse
import curses
import random
import sys
import time
from dataclasses import dataclass, field

ROWS = 5
COLS = 11
PLAYER_LIVES = 3
MAX_BOMBS = 3
DEFAULT_WIDTH = 60
DEFAULT_HEIGHT = 24
DEFAULT_TICK_MS = 80


def score_for_row(row):
    """Classic arcade values: top rows 30, middle rows 20, bottom 10."""
    if row <= 1:
        return 30
    if row <= 3:
        return 20
    return 10


def invader_glyph(row):
    if row <= 1:
        return "W"
    if row <= 3:
        return "V"
    return "U"


@dataclass
class Invader:
    x: int
    y: int
    row: int


@dataclass
class Projectile:
    x: int
    y: int


@dataclass
class Game:
    width: int
    height: int
    player_x: int
    lives: int = PLAYER_LIVES
    score: int = 0
    level: int = 1
    invaders: list = field(default_factory=list)
    direction: int = 1  # +1 right, -1 left
    tick: int = 0
    bullets: list = field(default_factory=list)
    bombs: list = field(default_factory=list)
    shields: set = field(default_factory=set)
    status: str = "playing"  # "playing" or "game_over"

    @property
    def player_y(self):
        return self.height - 2

    @property
    def ground_y(self):
        return self.height - 1


def build_shields(width, height):
    """Four 5x2 bases, evenly spaced, two rows above the player row."""
    shields = set()
    top = height - 2 - 3  # player_y - 3
    for i in range(4):
        start = (i + 1) * width // 5 - 2
        for dx in range(5):
            for dy in range(2):
                shields.add((start + dx, top + dy))
    return shields


def build_formation():
    """5 rows x 11 columns, columns 3 apart, rows 2 apart."""
    return [
        Invader(x=5 + col * 3, y=3 + row * 2, row=row)
        for row in range(ROWS)
        for col in range(COLS)
    ]


def new_game(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
    game = Game(width=width, height=height, player_x=width // 2)
    game.invaders = build_formation()
    game.shields = build_shields(width, height)
    return game


def move_interval(game):
    """Formation step period in ticks: faster as invaders die / levels rise."""
    killed = ROWS * COLS - len(game.invaders)
    return max(2, 10 - (killed // 5) - (game.level - 1) * 2)


def move_player(game, dx):
    if game.status != "playing":
        return
    game.player_x = max(0, min(game.width - 1, game.player_x + dx))


def move_formation(game):
    """One formation step: sideways, or down + reverse at either edge."""
    if not game.invaders:
        return
    if game.direction > 0:
        blocked = any(inv.x + 1 >= game.width for inv in game.invaders)
    else:
        blocked = any(inv.x - 1 < 0 for inv in game.invaders)
    if blocked:
        game.direction = -game.direction
        for inv in game.invaders:
            inv.y += 1
    else:
        for inv in game.invaders:
            inv.x += game.direction


def fire_player(game):
    """One bullet in flight at a time (classic rule); returns success."""
    if game.status != "playing" or game.bullets:
        return False
    game.bullets.append(Projectile(game.player_x, game.player_y - 1))
    return True


def invader_fire(game, rng):
    """Maybe drop a bomb from the bottom-most invader of a random column."""
    if len(game.bombs) >= MAX_BOMBS or not game.invaders:
        return False
    if rng.random() >= 0.15:
        return False
    columns = {}
    for inv in game.invaders:
        columns.setdefault(inv.x, inv)
        if inv.y > columns[inv.x].y:
            columns[inv.x] = inv
    shooter = columns[rng.choice(sorted(columns))]
    game.bombs.append(Projectile(shooter.x, shooter.y + 1))
    return True


def _hit_player(game):
    game.lives -= 1
    game.bullets.clear()
    game.bombs.clear()
    game.player_x = game.width // 2
    if game.lives <= 0:
        game.status = "game_over"


def step(game, dx=0, fire=False, rng=None):
    """Advance one frame. Pure: no I/O, randomness only via ``rng``."""
    if game.status != "playing":
        return
    if rng is None:
        rng = random.Random()
    move_player(game, dx)
    if fire:
        fire_player(game)

    # Projectiles move.
    for bullet in game.bullets:
        bullet.y -= 1
    game.bullets = [b for b in game.bullets if b.y >= 1]
    for bomb in game.bombs:
        bomb.y += 1
    game.bombs = [b for b in game.bombs if b.y < game.ground_y]

    # Bullet collisions: one bullet destroys at most one thing.
    invader_cells = {(inv.x, inv.y): inv for inv in game.invaders}
    surviving_bullets = []
    for bullet in game.bullets:
        hit = invader_cells.get((bullet.x, bullet.y))
        if hit is not None:
            game.invaders.remove(hit)
            game.score += score_for_row(hit.row)
            del invader_cells[(bullet.x, bullet.y)]
        elif (bullet.x, bullet.y) in game.shields:
            game.shields.discard((bullet.x, bullet.y))
        else:
            surviving_bullets.append(bullet)
    game.bullets = surviving_bullets

    # Bomb collisions.
    surviving_bombs = []
    for bomb in game.bombs:
        if (bomb.x, bomb.y) in game.shields:
            game.shields.discard((bomb.x, bomb.y))
        elif bomb.x == game.player_x and bomb.y == game.player_y:
            _hit_player(game)
            surviving_bombs = []
            break
        else:
            surviving_bombs.append(bomb)
    game.bombs = surviving_bombs
    if game.status != "playing":
        return

    # Formation move on its tick, then invader fire.
    game.tick += 1
    if game.tick % move_interval(game) == 0:
        move_formation(game)
    invader_fire(game, rng)

    # End checks: invasion first (it beats a simultaneous level clear).
    if any(inv.y >= game.player_y for inv in game.invaders):
        game.status = "game_over"
        return
    if not game.invaders:
        game.level += 1
        game.invaders = build_formation()
        game.direction = 1
        game.bullets.clear()
        game.bombs.clear()


def render(game):
    """Return the whole screen as one string (info bar + grid)."""
    grid = [[" "] * game.width for _ in range(game.height)]
    for x in range(game.width):
        grid[game.ground_y][x] = "="
    for x, y in game.shields:
        if 0 <= y < game.height:
            grid[y][x] = "#"
    for inv in game.invaders:
        grid[inv.y][inv.x] = invader_glyph(inv.row)
    for bullet in game.bullets:
        grid[bullet.y][bullet.x] = "|"
    for bomb in game.bombs:
        grid[bomb.y][bomb.x] = "!"
    grid[game.player_y][game.player_x] = "^"
    info = "SCORE {}  LIVES {}  LEVEL {}".format(
        game.score, game.lives, game.level)
    lines = [info.ljust(game.width)[: game.width]]
    lines.extend("".join(row) for row in grid[1:])
    if game.status == "game_over":
        lines.append("GAME OVER -- press R for a new game")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Terminal Space Invaders.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--tick-ms", type=int, default=DEFAULT_TICK_MS)
    args = parser.parse_args(argv)
    if args.width < 40:
        parser.error("--width must be at least 40")
    if args.height < 16:
        parser.error("--height must be at least 16")
    if not 20 <= args.tick_ms <= 500:
        parser.error("--tick-ms must be between 20 and 500")
    return args


def main(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    game = new_game(args.width, args.height)
    while True:
        dx, fire = 0, False
        while True:
            key = stdscr.getch()
            if key == -1:
                break
            if key in (ord("q"), ord("Q")):
                return
            if key in (ord("r"), ord("R")) and game.status == "game_over":
                game = new_game(args.width, args.height)
            elif key in (curses.KEY_LEFT, ord("a"), ord("A")):
                dx = -1
            elif key in (curses.KEY_RIGHT, ord("d"), ord("D")):
                dx = 1
            elif key == ord(" "):
                fire = True
        step(game, dx=dx, fire=fire)
        stdscr.erase()
        for i, line in enumerate(render(game).split("\n")):
            try:
                stdscr.addstr(i, 0, line[: args.width])
            except curses.error:
                pass
        stdscr.refresh()
        time.sleep(args.tick_ms / 1000.0)


if __name__ == "__main__":
    args = parse_args()
    try:
        curses.wrapper(main, args)
    except KeyboardInterrupt:
        sys.exit(0)

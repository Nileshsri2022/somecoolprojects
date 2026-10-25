#!/usr/bin/env python3
"""Terminal Snake — pure game logic plus a thin curses UI.

All rules live in :class:`Game`, :func:`spawn_food` and
:func:`tick_interval`; none of them touches the terminal, so they
are fully unit-testable. Only ``main``/``play`` use curses.

Usage: python3 snake.py [--width N] [--height N]
Controls: arrows/WASD to steer, p pause, q quit, r restart.
"""

import argparse
import curses
import random
import sys

# Directions as (dx, dy); y grows downwards.
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRECTIONS = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}

START_LENGTH = 4
POINTS_PER_FOOD = 10
BASE_INTERVAL = 0.150  # seconds per tick at start
INTERVAL_STEP = 0.005  # seconds faster per food eaten
MIN_INTERVAL = 0.060
MIN_SIZE = 5


def tick_interval(foods_eaten):
    """Seconds between ticks; speeds up, floored at MIN_INTERVAL."""
    return max(MIN_INTERVAL, BASE_INTERVAL - INTERVAL_STEP * foods_eaten)


def spawn_food(width, height, occupied, rng):
    """Random free cell, or None if the board is full.

    ``occupied`` is a set of (x, y) cells; ``rng`` is a
    ``random.Random`` (injectable so tests are deterministic).
    """
    free = [(x, y) for y in range(height) for x in range(width)
            if (x, y) not in occupied]
    if not free:
        return None
    return rng.choice(free)


class Game:
    """Pure Snake state. Head is body[0]; body trails behind it."""

    def __init__(self, width=20, height=20, rng=None):
        if width < MIN_SIZE or height < MIN_SIZE:
            raise ValueError("board must be at least %dx%d" % (MIN_SIZE, MIN_SIZE))
        self.width = width
        self.height = height
        self.rng = rng if rng is not None else random.Random()
        cy = height // 2
        # Head at centre, body trailing left, moving right; on narrow
        # boards shift right so the 4-cell body still fits on-board.
        cx = max(width // 2, START_LENGTH - 1)
        self.body = [(cx - i, cy) for i in range(START_LENGTH)]
        self.direction = RIGHT
        self._pending = []  # queued directions, one applied per tick
        self.food = spawn_food(width, height, set(self.body), self.rng)
        self.score = 0
        self.foods_eaten = 0
        self.alive = True
        self.death = None  # None | "wall" | "self" | "win"

    def set_direction(self, direction):
        """Queue a turn; reversals and repeats are ignored."""
        if not self.alive:
            return
        last = self._pending[-1] if self._pending else self.direction
        if direction == last or direction == OPPOSITE[last]:
            return
        self._pending.append(direction)

    def step(self):
        """Advance one tick. No-op once the game is over."""
        if not self.alive:
            return
        if self._pending:
            self.direction = self._pending.pop(0)
        dx, dy = self.direction
        hx, hy = self.body[0]
        head = (hx + dx, hy + dy)
        if not (0 <= head[0] < self.width and 0 <= head[1] < self.height):
            self.alive, self.death = False, "wall"
            return
        eating = head == self.food
        # Tail vacates unless eating, so it is safe to enter then.
        obstacle = self.body if eating else self.body[:-1]
        if head in obstacle:
            self.alive, self.death = False, "self"
            return
        self.body.insert(0, head)
        if eating:
            self.score += POINTS_PER_FOOD
            self.foods_eaten += 1
            self.food = spawn_food(self.width, self.height,
                                   set(self.body), self.rng)
            if self.food is None:  # board completely filled
                self.alive, self.death = False, "win"
        else:
            self.body.pop()

    def render(self):
        """Board as text rows: '#' border, 'O' head, 'o' body, '*' food."""
        grid = [[" "] * self.width for _ in range(self.height)]
        if self.food is not None:
            fx, fy = self.food
            grid[fy][fx] = "*"
        for x, y in self.body[1:]:
            grid[y][x] = "o"
        hx, hy = self.body[0]
        grid[hy][hx] = "O"
        border = "#" * (self.width + 2)
        return [border] + ["#" + "".join(row) + "#" for row in grid] + [border]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Terminal Snake: eat food, grow, don't hit the wall or yourself.")
    parser.add_argument("--width", type=int, default=20, help="board width (default 20)")
    parser.add_argument("--height", type=int, default=20, help="board height (default 20)")
    args = parser.parse_args(argv)
    if args.width < MIN_SIZE or args.height < MIN_SIZE:
        parser.error("board must be at least %dx%d" % (MIN_SIZE, MIN_SIZE))
    return args


KEY_DIRS = {
    curses.KEY_UP: UP, curses.KEY_DOWN: DOWN,
    curses.KEY_LEFT: LEFT, curses.KEY_RIGHT: RIGHT,
    ord("w"): UP, ord("s"): DOWN, ord("a"): LEFT, ord("d"): RIGHT,
    ord("W"): UP, ord("S"): DOWN, ord("A"): LEFT, ord("D"): RIGHT,
}


def main(stdscr, width, height):
    curses.curs_set(0)
    game = Game(width, height)
    paused = False
    while True:
        stdscr.timeout(int(tick_interval(game.foods_eaten) * 1000))
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key == ord("p") and game.alive:
            paused = not paused
        elif key == ord("r") and not game.alive:
            game, paused = Game(width, height), False
        elif key in KEY_DIRS:
            game.set_direction(KEY_DIRS[key])
        # One tick per loop iteration: getch() blocks up to the
        # tick interval, so a keypress just ends the wait early.
        if not paused and game.alive:
            game.step()
        stdscr.clear()
        for i, row in enumerate(game.render()):
            stdscr.addstr(i, 0, row)
        status = "Score: %d  Length: %d" % (game.score, len(game.body))
        if paused:
            status += "  (paused — p to resume)"
        stdscr.addstr(len(game.render()), 0, status)
        if not game.alive:
            msg = ("You win! " if game.death == "win" else "Game over! ") + \
                  "Score: %d — press r for a new game, q to quit." % game.score
            stdscr.addstr(len(game.render()) + 1, 0, msg)
        stdscr.refresh()


def play(argv=None):
    args = parse_args(argv)
    curses.wrapper(main, args.width, args.height)


if __name__ == "__main__":
    try:
        play(sys.argv[1:])
    except KeyboardInterrupt:
        pass

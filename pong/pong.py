"""Terminal Pong (Coding Challenges #36).

Pure game logic (new_game / serve / move_paddle / ai_move /
step / render) plus a thin curses shell. The logic never
touches the terminal, so tests run headless.
"""

import argparse
import curses
import math
import random
import sys
import time
from dataclasses import dataclass


@dataclass
class Game:
    width: int = 80
    height: int = 24
    paddle_height: int = 4
    winning_score: int = 5
    left_y: int = 10
    right_y: int = 10
    ball_x: float = 40.0
    ball_y: float = 12.0
    vx: float = 1.0
    vy: float = 0.0
    left_score: int = 0
    right_score: int = 0
    winner: str | None = None

    @property
    def left_x(self):
        return 1

    @property
    def right_x(self):
        return self.width - 2


def new_game(width=80, height=24, paddle_height=4, winning_score=5,
             rng=None):
    """Fresh game, ball served, paddles centred vertically."""
    _validate(width, height, paddle_height, winning_score)
    state = Game(width=width, height=height,
                 paddle_height=paddle_height,
                 winning_score=winning_score,
                 left_y=(height - paddle_height) // 2,
                 right_y=(height - paddle_height) // 2)
    serve(state, rng=rng)
    return state


def _validate(width, height, paddle_height, winning_score):
    if winning_score < 1:
        raise ValueError("winning_score must be >= 1")
    if width < 10:
        raise ValueError("width must be >= 10")
    if height < 5:
        raise ValueError("height must be >= 5")
    if paddle_height < 2 or paddle_height >= height:
        raise ValueError("paddle_height must be >= 2 and < height")


def serve(state, direction=None, angle_deg=None, rng=None):
    """Place the ball on the centre line, moving at random.

    Explicit direction/angle are for deterministic tests; the
    game always calls serve() with neither, i.e. fully random.
    """
    rng = rng if rng is not None else random
    if direction is None:
        direction = rng.choice((-1, 1))
    if angle_deg is None:
        angle_deg = rng.uniform(-45, 45)
    state.ball_x = float(state.width // 2)
    state.ball_y = float(rng.randrange(state.height))
    state.vx = float(direction)
    state.vy = math.tan(math.radians(angle_deg))


def move_paddle(state, side, delta):
    """Move a paddle by delta rows, clamped to the field."""
    top = 0
    bottom = state.height - state.paddle_height
    if side == "left":
        state.left_y = max(top, min(bottom, state.left_y + delta))
    elif side == "right":
        state.right_y = max(top, min(bottom, state.right_y + delta))
    else:
        raise ValueError("side must be 'left' or 'right'")


def ai_move(state):
    """One beatable-AI tick for the right paddle.

    Moves at most one cell, only while the ball travels
    towards it, towards the ball's current row (no
    prediction of the intercept point).
    """
    if state.vx <= 0 or state.winner is not None:
        return
    centre = state.right_y + (state.paddle_height - 1) / 2
    if state.ball_y > centre + 0.5:
        move_paddle(state, "right", 1)
    elif state.ball_y < centre - 0.5:
        move_paddle(state, "right", -1)


def _paddle_hit_vy(state, paddle_y):
    centre = paddle_y + (state.paddle_height - 1) / 2
    offset = (state.ball_y - centre) / (state.paddle_height / 2)
    return max(-1.0, min(1.0, offset))


def step(state):
    """Advance one tick. Returns an event string or None."""
    if state.winner is not None:
        return None
    old_x = state.ball_x
    state.ball_x += state.vx
    state.ball_y += state.vy
    # Wall bounce: vertical reverses, horizontal untouched.
    if state.ball_y < 0:
        state.ball_y = 0.0
        state.vy = -state.vy
    elif state.ball_y > state.height - 1:
        state.ball_y = float(state.height - 1)
        state.vy = -state.vy
    # Paddle collision (checked before scoring).
    if state.vx < 0 and old_x > state.left_x >= state.ball_x:
        if state.left_y <= state.ball_y < state.left_y + state.paddle_height:
            state.ball_x = float(state.left_x + 1)
            state.vx = -state.vx
            state.vy = _paddle_hit_vy(state, state.left_y)
    elif state.vx > 0 and old_x < state.right_x <= state.ball_x:
        if state.right_y <= state.ball_y < state.right_y + state.paddle_height:
            state.ball_x = float(state.right_x - 1)
            state.vx = -state.vx
            state.vy = _paddle_hit_vy(state, state.right_y)
    # Scoring.
    if state.ball_x < 0:
        state.right_score += 1
        return _after_score(state, "right")
    if state.ball_x >= state.width:
        state.left_score += 1
        return _after_score(state, "left")
    return None


def _after_score(state, scorer):
    score = state.left_score if scorer == "left" else state.right_score
    if score >= state.winning_score:
        state.winner = scorer
        state.vx = 0.0
        state.vy = 0.0
        return scorer + "_wins"
    serve(state)
    return scorer + "_scores"


def is_game_over(state):
    return state.winner is not None


def render(state):
    """Text table: score line + height rows of width chars."""
    if state.winner == "left":
        score_line = "Left wins!"
    elif state.winner == "right":
        score_line = "Right wins!"
    else:
        score_line = f"Left {state.left_score} - {state.right_score} Right"
    ball_col = int(round(state.ball_x))
    ball_row = int(round(state.ball_y))
    centre_col = state.width // 2
    rows = []
    for row in range(state.height):
        cells = [" "] * state.width
        if row % 2 == 0:
            cells[centre_col] = ":"
        rows.append(cells)
    for row in range(state.height):
        if state.left_y <= row < state.left_y + state.paddle_height:
            rows[row][state.left_x] = "|"
        if state.right_y <= row < state.right_y + state.paddle_height:
            rows[row][state.right_x] = "|"
    if 0 <= ball_row < state.height and 0 <= ball_col < state.width:
        rows[ball_row][ball_col] = "O"
    return score_line + "\n" + "\n".join("".join(r) for r in rows)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Terminal Pong")
    parser.add_argument("--winning-score", type=int, default=5)
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=24)
    parser.add_argument("--paddle-height", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        _validate(args.width, args.height, args.paddle_height,
                  args.winning_score)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def play(stdscr, args):
    """Curses shell: keys -> pure functions, ~70 ms per tick."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    state = new_game(args.width, args.height, args.paddle_height,
                     args.winning_score)
    while True:
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return
        if is_game_over(state):
            if key in (ord("r"), ord("R")):
                state = new_game(args.width, args.height,
                                 args.paddle_height,
                                 args.winning_score)
            elif key != -1:
                pass
        elif key in (ord("w"), ord("W"), curses.KEY_UP):
            move_paddle(state, "left", -1)
        elif key in (ord("s"), ord("S"), curses.KEY_DOWN):
            move_paddle(state, "left", 1)
        if not is_game_over(state):
            ai_move(state)
            step(state)
        stdscr.erase()
        try:
            stdscr.addstr(0, 0, render(state))
        except curses.error:
            pass  # terminal smaller than the field: draw what fits
        if is_game_over(state):
            stdscr.addstr("\nPress R for a new game, Q to quit.")
        stdscr.refresh()
        time.sleep(0.07)


def main(argv=None):
    args = parse_args(argv)
    curses.wrapper(play, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

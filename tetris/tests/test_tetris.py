import random
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tetris
from tetris import (Game, Piece, SHAPES, WIDTH, HEIGHT, cells_of,
                    clear_lines, collides, empty_board, gravity_interval,
                    level_for, lock_piece, render_text, rotate_ccw,
                    rotate_cw, score_for_lines)


def game_with_piece(kind, board=None):
    game = Game(pieces=[kind])
    if board is not None:
        game.board = board
    return game


class TestShapes(unittest.TestCase):
    def test_all_seven_kinds_exist(self):
        self.assertEqual(set(SHAPES), {"I", "O", "T", "S", "Z", "J", "L"})

    def test_every_shape_has_four_blocks(self):
        for kind, shape in SHAPES.items():
            with self.subTest(kind=kind):
                self.assertEqual(len(cells_of(shape)), 4)

    def test_four_cw_rotations_return_to_original(self):
        for kind, shape in SHAPES.items():
            with self.subTest(kind=kind):
                rotated = shape
                for _ in range(4):
                    rotated = rotate_cw(rotated)
                self.assertEqual(rotated, shape)

    def test_o_piece_is_rotation_invariant(self):
        self.assertEqual(rotate_cw(SHAPES["O"]), SHAPES["O"])
        self.assertEqual(rotate_ccw(SHAPES["O"]), SHAPES["O"])

    def test_i_piece_alternates_orientation(self):
        vertical = rotate_cw(SHAPES["I"])
        self.assertEqual(len(vertical), 4)  # 4 rows tall
        self.assertEqual(len(vertical[0]), 1)

    def test_ccw_undoes_cw(self):
        for kind, shape in SHAPES.items():
            with self.subTest(kind=kind):
                self.assertEqual(rotate_ccw(rotate_cw(shape)), shape)


class TestCollision(unittest.TestCase):
    def test_empty_board_no_collision(self):
        self.assertFalse(collides(empty_board(), SHAPES["T"], 4, 0))

    def test_left_wall_blocks(self):
        self.assertTrue(collides(empty_board(), SHAPES["O"], -1, 0))

    def test_right_wall_blocks(self):
        self.assertTrue(collides(empty_board(), SHAPES["O"], WIDTH - 1, 0))

    def test_floor_blocks(self):
        self.assertTrue(collides(empty_board(), SHAPES["O"], 0, HEIGHT - 1))

    def test_locked_cell_blocks(self):
        board = empty_board()
        board[5][5] = "X"
        self.assertTrue(collides(board, SHAPES["O"], 5, 5))
        self.assertFalse(collides(board, SHAPES["O"], 0, 0))


class TestMovement(unittest.TestCase):
    def test_move_left_and_right(self):
        game = game_with_piece("O")
        x = game.current.x
        self.assertTrue(game.move(-1))
        self.assertEqual(game.current.x, x - 1)
        self.assertTrue(game.move(1))
        self.assertEqual(game.current.x, x)

    def test_move_rejected_at_left_wall(self):
        game = game_with_piece("O")
        game.current.x = 0
        self.assertFalse(game.move(-1))
        self.assertEqual(game.current.x, 0)

    def test_move_rejected_at_right_wall(self):
        game = game_with_piece("O")
        game.current.x = WIDTH - 2
        self.assertFalse(game.move(1))
        self.assertEqual(game.current.x, WIDTH - 2)

    def test_move_rejected_against_locked_cell(self):
        game = game_with_piece("O")
        game.current.x, game.current.y = 4, 5
        game.board[5][3] = "X"
        self.assertFalse(game.move(-1))

    def test_move_never_changes_y_or_board(self):
        game = game_with_piece("O")
        before = [row[:] for row in game.board]
        y = game.current.y
        game.move(1)
        self.assertEqual(game.current.y, y)
        self.assertEqual(game.board, before)

    def test_rotate_changes_shape_when_free(self):
        game = game_with_piece("T")
        before = game.current.shape
        self.assertTrue(game.rotate("cw"))
        self.assertNotEqual(game.current.shape, before)

    def test_rotate_ccw_reverses_cw(self):
        game = game_with_piece("T")
        before = game.current.shape
        game.rotate("cw")
        game.rotate("ccw")
        self.assertEqual(game.current.shape, before)

    def test_rotate_rejected_at_floor(self):
        # I piece horizontal at the floor: rotating to vertical needs
        # rows below the floor only if placed at the last row.
        game = game_with_piece("I")
        game.current.y = HEIGHT - 1
        before = game.current.shape
        self.assertFalse(game.rotate("cw"))
        self.assertEqual(game.current.shape, before)


class TestGravityAndLocking(unittest.TestCase):
    def test_tick_moves_piece_down_one_row(self):
        game = game_with_piece("O")
        y = game.current.y
        game.tick()
        self.assertEqual(game.current.y, y + 1)

    def test_piece_locks_on_floor_and_next_spawns(self):
        game = Game(pieces=["O", "T"])
        game.current.y = HEIGHT - 2
        game.tick()  # cannot move down: locks, next piece spawns
        self.assertEqual(game.current.kind, "T")
        self.assertEqual(game.current.y, 0)
        self.assertEqual(game.board[HEIGHT - 1][game.current.x], 0)
        # Locked O cells at the bottom rows.
        locked = sum(1 for row in game.board for c in row if c)
        self.assertEqual(locked, 4)

    def test_soft_drop_adds_one_point_per_cell(self):
        game = game_with_piece("O")
        game.soft_drop()
        self.assertEqual(game.score, 1)
        game.soft_drop()
        self.assertEqual(game.score, 2)

    def test_hard_drop_lands_and_scores_two_per_cell(self):
        game = Game(pieces=["O", "T"])
        game.hard_drop()
        self.assertEqual(game.current.kind, "T")
        self.assertEqual(game.score, 2 * (HEIGHT - 2))
        locked = sum(1 for row in game.board for c in row if c)
        self.assertEqual(locked, 4)

    def test_hard_drop_stops_on_locked_cells(self):
        game = Game(pieces=["O", "O"])
        game.board[HEIGHT - 1] = ["X"] * WIDTH
        # Bottom row full already: first piece locks above it.
        game.hard_drop()
        self.assertTrue(any(c == "O" for row in game.board for c in row))


class TestLineClears(unittest.TestCase):
    def test_one_full_row_clears_and_rows_drop(self):
        board = empty_board()
        board[HEIGHT - 1] = ["X"] * WIDTH
        board[HEIGHT - 2][0] = "Y"
        new, cleared = clear_lines(board)
        self.assertEqual(cleared, 1)
        self.assertEqual(new[HEIGHT - 1][0], "Y")
        self.assertEqual(new[0], [0] * WIDTH)

    def test_two_full_rows_both_clear(self):
        board = empty_board()
        board[HEIGHT - 1] = ["X"] * WIDTH
        board[HEIGHT - 2] = ["X"] * WIDTH
        _, cleared = clear_lines(board)
        self.assertEqual(cleared, 2)

    def test_non_full_row_kept(self):
        board = empty_board()
        board[HEIGHT - 1][0] = "X"
        new, cleared = clear_lines(board)
        self.assertEqual(cleared, 0)
        self.assertEqual(new[HEIGHT - 1][0], "X")

    def test_locking_completes_row_scores_and_counts(self):
        game = Game(pieces=["I", "T"])
        # Fill the bottom row except the 4 cells the I piece covers.
        game.board[HEIGHT - 1] = ["X"] * WIDTH
        game.current.shape = SHAPES["I"]
        game.current.x, game.current.y = 3, HEIGHT - 1
        for x in range(3, 7):
            game.board[HEIGHT - 1][x] = 0
        game.tick()  # locks, clears the row
        self.assertEqual(game.lines, 1)
        self.assertEqual(game.score, 100)
        self.assertEqual(game.board[HEIGHT - 1], [0] * WIDTH)

    def test_score_table(self):
        self.assertEqual(score_for_lines(1, 1), 100)
        self.assertEqual(score_for_lines(2, 1), 300)
        self.assertEqual(score_for_lines(3, 1), 500)
        self.assertEqual(score_for_lines(4, 1), 800)
        self.assertEqual(score_for_lines(2, 3), 900)
        self.assertEqual(score_for_lines(0, 1), 0)


class TestLevels(unittest.TestCase):
    def test_level_boundaries(self):
        self.assertEqual(level_for(0), 1)
        self.assertEqual(level_for(9), 1)
        self.assertEqual(level_for(10), 2)
        self.assertEqual(level_for(19), 2)
        self.assertEqual(level_for(20), 3)

    def test_gravity_speeds_up_but_has_floor(self):
        self.assertGreater(gravity_interval(1), gravity_interval(2))
        self.assertGreater(gravity_interval(2), gravity_interval(5))
        for level in (1, 5, 10, 100):
            self.assertGreaterEqual(gravity_interval(level), 0.05)


class TestBagAndOrder(unittest.TestCase):
    def test_seven_bag_contains_each_piece_once(self):
        game = Game(rng=random.Random(42))
        kinds = [game.current.kind]
        for _ in range(6):
            kinds.append(game.upcoming)
            game.spawn()
        self.assertEqual(sorted(kinds), sorted(SHAPES))

    def test_fixed_piece_order_honoured(self):
        game = Game(pieces=["S", "Z", "I"])
        self.assertEqual(game.current.kind, "S")
        self.assertEqual(game.upcoming, "Z")
        game.spawn()
        self.assertEqual(game.current.kind, "Z")
        self.assertEqual(game.upcoming, "I")


class TestGameOver(unittest.TestCase):
    def test_spawn_collision_ends_game(self):
        game = game_with_piece("O")
        game.board[0] = ["X"] * WIDTH
        game.board[1] = ["X"] * WIDTH
        game.spawn()
        self.assertEqual(game.state, "over")

    def test_no_moves_or_ticks_after_game_over(self):
        game = game_with_piece("O")
        game.board[0] = ["X"] * WIDTH
        game.board[1] = ["X"] * WIDTH
        game.spawn()
        self.assertEqual(game.state, "over")
        x, y = game.current.x, game.current.y
        self.assertFalse(game.move(1))
        self.assertFalse(game.rotate("cw"))
        game.tick()
        self.assertEqual((game.current.x, game.current.y), (x, y))

    def test_fresh_game_starts_clean(self):
        game = Game(pieces=["T"])
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.score, 0)
        self.assertEqual(game.lines, 0)
        self.assertEqual(game.level, 1)
        self.assertEqual(game.board, empty_board())


class TestRendering(unittest.TestCase):
    def test_render_shows_border_piece_and_stats(self):
        game = game_with_piece("T")
        text = render_text(game)
        self.assertIn("+" + "-" * WIDTH + "+", text)
        self.assertIn("T", text)
        self.assertIn("Score: 0", text)
        self.assertIn("Level: 1", text)
        self.assertIn("Lines: 0", text)

    def test_render_does_not_mutate_game(self):
        game = game_with_piece("T")
        board_before = [row[:] for row in game.board]
        shape_before = game.current.shape
        render_text(game)
        self.assertEqual(game.board, board_before)
        self.assertEqual(game.current.shape, shape_before)

    def test_lock_piece_writes_letter(self):
        board = empty_board()
        lock_piece(board, SHAPES["O"], 0, 0, "O")
        self.assertEqual(board[0][0], "O")
        self.assertEqual(board[1][1], "O")
        self.assertEqual(board[0][2], 0)


if __name__ == "__main__":
    unittest.main()

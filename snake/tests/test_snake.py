"""Unit tests for snake.py — pure logic only, no terminal needed."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snake import (DOWN, LEFT, RIGHT, UP, Game, parse_args, spawn_food,
                   tick_interval)


def make_game(body, direction, food, width=20, height=20):
    """Game with a hand-set body/direction/food for deterministic tests."""
    game = Game(width, height, rng=random.Random(0))
    game.body = list(body)
    game.direction = direction
    game._pending = []
    game.food = food
    return game


class TestStartState(unittest.TestCase):
    def test_default_start(self):
        game = Game()
        self.assertEqual((game.width, game.height), (20, 20))
        self.assertEqual(len(game.body), 4)
        self.assertEqual(game.direction, RIGHT)
        self.assertTrue(game.alive)
        self.assertEqual(game.score, 0)
        self.assertIsNone(game.death)
        # Head in centre row, body trailing left of it.
        hx, hy = game.body[0]
        self.assertEqual(hy, 10)
        self.assertEqual(game.body, [(hx - i, hy) for i in range(4)])

    def test_food_on_board_not_on_snake(self):
        for seed in range(20):
            game = Game(rng=random.Random(seed))
            self.assertIn(game.food[0], range(20))
            self.assertIn(game.food[1], range(20))
            self.assertNotIn(game.food, game.body)

    def test_small_board_rejected(self):
        with self.assertRaises(ValueError):
            Game(4, 20)
        with self.assertRaises(ValueError):
            Game(20, 4)

    def test_narrow_board_body_fits(self):
        game = Game(5, 5)
        for x, y in game.body:
            self.assertIn(x, range(5))
            self.assertIn(y, range(5))


class TestMovement(unittest.TestCase):
    def test_step_right_keeps_length(self):
        game = make_game([(10, 10), (9, 10), (8, 10), (7, 10)], RIGHT, (0, 0))
        game.step()
        self.assertEqual(game.body[0], (11, 10))
        self.assertEqual(len(game.body), 4)
        self.assertTrue(game.alive)

    def test_each_direction(self):
        for direction, delta in ((UP, (0, -1)), (DOWN, (0, 1)),
                                 (LEFT, (-1, 0)), (RIGHT, (1, 0))):
            game = make_game([(10, 10), (9, 10)], direction, (0, 0))
            game.step()
            self.assertEqual(game.body[0],
                             (10 + delta[0], 10 + delta[1]))

    def test_reversal_ignored(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.set_direction(LEFT)  # reverse of right: ignored
        game.step()
        self.assertEqual(game.body[0], (11, 10))

    def test_legal_turn_applies(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.set_direction(UP)
        game.step()
        self.assertEqual(game.body[0], (10, 9))

    def test_queued_turns_apply_one_per_tick(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.set_direction(UP)
        game.set_direction(LEFT)
        game.step()
        self.assertEqual(game.body[0], (10, 9))   # up first
        game.step()
        self.assertEqual(game.body[0], (9, 9))    # then left, no reversal

    def test_queued_reversal_of_queued_direction_ignored(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.set_direction(UP)
        game.set_direction(DOWN)  # opposite of queued UP: ignored
        game.step()
        self.assertEqual(game.body[0], (10, 9))
        game.step()
        self.assertEqual(game.body[0], (10, 8))  # still going up

    def test_repeat_direction_is_noop(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.set_direction(RIGHT)
        self.assertEqual(game._pending, [])

    def test_dead_game_is_frozen(self):
        game = make_game([(0, 10), (1, 10)], LEFT, (5, 5))
        game.step()  # wall
        self.assertFalse(game.alive)
        body = list(game.body)
        game.set_direction(UP)
        game.step()
        self.assertEqual(game.body, body)


class TestFoodGrowthScoring(unittest.TestCase):
    def test_eating_grows_and_scores(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (11, 10))
        game.step()
        self.assertEqual(len(game.body), 3)
        self.assertEqual(game.score, 10)
        self.assertEqual(game.foods_eaten, 1)
        self.assertTrue(game.alive)
        self.assertNotIn(game.food, game.body)

    def test_not_eating_keeps_length_and_score(self):
        game = make_game([(10, 10), (9, 10)], RIGHT, (0, 0))
        game.step()
        self.assertEqual(len(game.body), 2)
        self.assertEqual(game.score, 0)

    def test_spawn_food_seeded_and_avoids_snake(self):
        occupied = {(0, 0), (1, 0)}
        food = spawn_food(3, 3, occupied, random.Random(42))
        self.assertNotIn(food, occupied)
        self.assertEqual(food, spawn_food(3, 3, occupied, random.Random(42)))

    def test_spawn_food_single_free_cell(self):
        occupied = {(x, y) for x in range(3) for y in range(3)} - {(2, 2)}
        self.assertEqual(spawn_food(3, 3, occupied, random.Random(1)), (2, 2))

    def test_spawn_food_full_board_is_none(self):
        occupied = {(x, y) for x in range(2) for y in range(2)}
        self.assertIsNone(spawn_food(2, 2, occupied, random.Random(1)))

    def test_filling_board_is_win(self):
        # 5x5 board, snake on every cell except (0,0); head next to it.
        all_cells = [(x, y) for y in range(5) for x in range(5)]
        body = [(1, 0)] + [c for c in all_cells if c not in ((0, 0), (1, 0))]
        game = make_game(body, LEFT, (0, 0), width=5, height=5)
        self.assertEqual(len(game.body), 24)
        game.step()
        self.assertEqual(len(game.body), 25)
        self.assertFalse(game.alive)
        self.assertEqual(game.death, "win")
        self.assertIsNone(game.food)


class TestCollisions(unittest.TestCase):
    def test_wall_all_four_edges(self):
        for body, direction in [([(0, 10), (1, 10)], LEFT),
                                ([(19, 10), (18, 10)], RIGHT),
                                ([(10, 0), (10, 1)], UP),
                                ([(10, 19), (10, 18)], DOWN)]:
            game = make_game(body, direction, (5, 5))
            game.step()
            self.assertFalse(game.alive)
            self.assertEqual(game.death, "wall")

    def test_self_collision(self):
        game = make_game([(5, 5), (5, 6), (6, 6), (6, 5)], DOWN, (0, 0))
        game.step()  # head (5,6) is already a body cell
        self.assertFalse(game.alive)
        self.assertEqual(game.death, "self")

    def test_entering_vacated_tail_is_safe(self):
        # Loop: head (5,5) moving left into tail cell (4,5).
        game = make_game([(5, 5), (5, 6), (4, 6), (4, 5)], LEFT, (0, 0))
        game.step()
        self.assertTrue(game.alive)
        self.assertEqual(game.body[0], (4, 5))

    def test_entering_tail_while_eating_is_collision(self):
        game = make_game([(5, 5), (5, 6), (4, 6), (4, 5)], LEFT, (4, 5))
        game.step()
        self.assertFalse(game.alive)
        self.assertEqual(game.death, "self")


class TestSpeedAndRender(unittest.TestCase):
    def test_tick_interval(self):
        self.assertAlmostEqual(tick_interval(0), 0.150)
        self.assertAlmostEqual(tick_interval(10), 0.100)
        self.assertAlmostEqual(tick_interval(1000), 0.060)  # floor

    def test_render_shape_and_chars(self):
        game = make_game([(2, 1), (1, 1)], RIGHT, (3, 1), width=5, height=5)
        rows = game.render()
        self.assertEqual(len(rows), 7)  # 5 + 2 border rows
        self.assertTrue(all(len(r) == 7 for r in rows))
        self.assertEqual(rows[0], "#######")
        self.assertEqual(rows[-1], "#######")
        # Row for y=1 is rows[2]: border, body 'o' at x=1, head 'O' at
        # x=2, food '*' at x=3, border.
        self.assertEqual(rows[2], "# oO* #")

    def test_render_head_matches_body(self):
        game = Game(20, 20, rng=random.Random(3))
        rows = game.render()
        hx, hy = game.body[0]
        self.assertEqual(rows[hy + 1][hx + 1], "O")


class TestCli(unittest.TestCase):
    def test_parse_args_defaults(self):
        args = parse_args([])
        self.assertEqual((args.width, args.height), (20, 20))

    def test_parse_args_custom(self):
        args = parse_args(["--width", "30", "--height", "15"])
        self.assertEqual((args.width, args.height), (30, 15))

    def test_parse_args_too_small_rejected(self):
        with self.assertRaises(SystemExit):
            parse_args(["--width", "2"])


if __name__ == "__main__":
    unittest.main()

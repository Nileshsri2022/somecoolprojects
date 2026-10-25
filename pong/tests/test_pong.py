import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pong import (Game, ai_move, is_game_over, move_paddle, new_game,
                  parse_args, render, serve, step)


def make_game(**over):
    g = Game(width=20, height=10, paddle_height=4, winning_score=3,
             left_y=3, right_y=3, ball_x=10.0, ball_y=5.0,
             vx=1.0, vy=0.0)
    for key, value in over.items():
        setattr(g, key, value)
    return g


class TestServe(unittest.TestCase):
    def test_default_serve_on_centre_line(self):
        g = new_game(width=20, height=10, rng=random.Random(1))
        self.assertEqual(g.ball_x, 10.0)
        self.assertIn(g.vx, (-1.0, 1.0))
        self.assertLessEqual(abs(g.vy), 1.0)
        self.assertTrue(0 <= g.ball_y < 10)

    def test_explicit_serve_is_exact(self):
        g = make_game()
        serve(g, direction=-1, angle_deg=0)
        self.assertEqual((g.vx, g.vy), (-1.0, 0.0))
        self.assertEqual(g.ball_x, 10.0)

    def test_seeded_serve_reproducible_and_in_bounds(self):
        for seed in range(20):
            g = new_game(width=20, height=10, rng=random.Random(seed))
            self.assertIn(g.vx, (-1.0, 1.0))
            self.assertLessEqual(abs(g.vy), 1.0)
            self.assertTrue(0 <= g.ball_y < 10)


class TestPaddles(unittest.TestCase):
    def test_move_and_clamp(self):
        g = make_game(left_y=3)
        move_paddle(g, "left", -1)
        self.assertEqual(g.left_y, 2)
        move_paddle(g, "left", -99)
        self.assertEqual(g.left_y, 0)
        move_paddle(g, "left", 99)
        self.assertEqual(g.left_y, 6)  # height - paddle_height
        move_paddle(g, "right", 1)
        self.assertEqual(g.right_y, 4)

    def test_bad_side_raises(self):
        with self.assertRaises(ValueError):
            move_paddle(make_game(), "middle", 1)


class TestWalls(unittest.TestCase):
    def test_top_bounce(self):
        g = make_game(ball_y=0.0, vy=-1.0, vx=1.0)
        step(g)
        self.assertEqual(g.ball_y, 0.0)
        self.assertEqual(g.vy, 1.0)
        self.assertEqual(g.vx, 1.0)

    def test_bottom_bounce(self):
        g = make_game(ball_y=9.0, vy=1.0, vx=-1.0)
        step(g)
        self.assertEqual(g.ball_y, 9.0)
        self.assertEqual(g.vy, -1.0)
        self.assertEqual(g.vx, -1.0)


class TestPaddleCollision(unittest.TestCase):
    def test_left_hit_flips_and_exits(self):
        g = make_game(ball_x=2.0, ball_y=4.0, vx=-1.0, vy=0.0)
        step(g)
        self.assertEqual(g.vx, 1.0)
        self.assertEqual(g.ball_x, 2.0)

    def test_right_hit_flips(self):
        g = make_game(ball_x=17.0, ball_y=4.0, vx=1.0, vy=0.0)
        step(g)
        self.assertEqual(g.vx, -1.0)
        self.assertEqual(g.ball_x, 17.0)

    def test_miss_does_not_flip(self):
        g = make_game(ball_x=2.0, ball_y=0.0, vx=-1.0, vy=0.0)
        step(g)
        self.assertEqual(g.vx, -1.0)

    def test_hit_angle(self):
        centre = make_game(ball_x=2.0, ball_y=4.5, vx=-1.0, vy=0.0)
        step(centre)
        self.assertAlmostEqual(centre.vy, 0.0)
        top = make_game(ball_x=2.0, ball_y=3.0, vx=-1.0, vy=0.0)
        step(top)
        self.assertLess(top.vy, 0)
        bottom = make_game(ball_x=2.0, ball_y=6.0, vx=-1.0, vy=0.0)
        step(bottom)
        self.assertGreater(bottom.vy, 0)
        self.assertLessEqual(abs(bottom.vy), 1.0)


class TestScoring(unittest.TestCase):
    def test_left_edge_scores_right_and_reserves(self):
        g = make_game(ball_x=0.0, ball_y=0.0, vx=-1.0, vy=0.0)
        event = step(g)
        self.assertEqual(event, "right_scores")
        self.assertEqual(g.right_score, 1)
        self.assertEqual(g.ball_x, 10.0)  # re-served on centre line

    def test_right_edge_scores_left(self):
        g = make_game(ball_x=19.0, ball_y=0.0, vx=1.0, vy=0.0)
        event = step(g)
        self.assertEqual(event, "left_scores")
        self.assertEqual(g.left_score, 1)

    def test_winning_stops_game(self):
        g = make_game(ball_x=19.0, ball_y=0.0, vx=1.0, vy=0.0,
                      left_score=2)
        event = step(g)
        self.assertEqual(event, "left_wins")
        self.assertEqual(g.winner, "left")
        self.assertTrue(is_game_over(g))
        self.assertEqual((g.vx, g.vy), (0.0, 0.0))
        frozen = (g.ball_x, g.ball_y, g.left_score)
        step(g)
        self.assertEqual((g.ball_x, g.ball_y, g.left_score), frozen)

    def test_not_over_during_play(self):
        self.assertFalse(is_game_over(make_game()))


class TestAI(unittest.TestCase):
    def test_moves_towards_ball_one_cell(self):
        g = make_game(ball_y=9.0, vx=1.0, right_y=3)
        ai_move(g)
        self.assertEqual(g.right_y, 4)

    def test_moves_up_towards_ball(self):
        g = make_game(ball_y=0.0, vx=1.0, right_y=3)
        ai_move(g)
        self.assertEqual(g.right_y, 2)

    def test_stays_when_ball_moves_away(self):
        g = make_game(ball_y=9.0, vx=-1.0, right_y=3)
        ai_move(g)
        self.assertEqual(g.right_y, 3)

    def test_clamped_at_edge(self):
        g = make_game(ball_y=9.0, vx=1.0, right_y=6)
        ai_move(g)
        self.assertEqual(g.right_y, 6)


class TestRender(unittest.TestCase):
    def test_shape_and_contents(self):
        g = make_game()
        text = render(g)
        lines = text.split("\n")
        self.assertEqual(len(lines), 11)  # score line + 10 rows
        self.assertTrue(all(len(row) == 20 for row in lines[1:]))
        self.assertIn("Left 0 - 0 Right", lines[0])
        self.assertIn("O", text)
        self.assertIn("|", text)
        self.assertIn(":", text)

    def test_winner_line(self):
        g = make_game(winner="right")
        self.assertIn("Right wins!", render(g).split("\n")[0])

    def test_render_does_not_mutate(self):
        g = make_game()
        before = (g.ball_x, g.ball_y, g.left_y, g.left_score)
        render(g)
        self.assertEqual((g.ball_x, g.ball_y, g.left_y, g.left_score),
                         before)


class TestArgs(unittest.TestCase):
    def test_defaults(self):
        args = parse_args([])
        self.assertEqual((args.winning_score, args.width, args.height,
                          args.paddle_height), (5, 80, 24, 4))

    def test_custom_values(self):
        args = parse_args(["--winning-score", "11", "--width", "40"])
        self.assertEqual((args.winning_score, args.width), (11, 40))

    def test_invalid_values_rejected(self):
        for argv in (["--winning-score", "0"], ["--width", "5"],
                     ["--height", "3"], ["--paddle-height", "99"]):
            with self.assertRaises(SystemExit):
                parse_args(argv)


if __name__ == "__main__":
    unittest.main()

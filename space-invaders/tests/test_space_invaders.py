import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from space_invaders import (  # noqa: E402
    Game, Invader, Projectile, build_formation, fire_player, move_formation,
    move_interval, move_player, new_game, parse_args, render,
    score_for_row, step,
)


class NeverFires:
    """Deterministic RNG stand-in: random() never drops below the 0.15 bar."""

    def random(self):
        return 0.99

    def choice(self, seq):
        return seq[0]


NEVER = NeverFires()


def small_game():
    """Default game with the formation replaced by one invader, for aiming."""
    game = new_game()
    game.invaders = [Invader(x=30, y=5, row=4)]
    return game


class TestNewGame(unittest.TestCase):
    def test_initial_state(self):
        game = new_game()
        self.assertEqual(len(game.invaders), 55)
        self.assertEqual({inv.row for inv in game.invaders}, {0, 1, 2, 3, 4})
        for row in range(5):
            self.assertEqual(
                sum(1 for inv in game.invaders if inv.row == row), 11)
        self.assertEqual(game.player_x, 30)
        self.assertEqual(game.player_y, 22)
        self.assertEqual(game.lives, 3)
        self.assertEqual(game.score, 0)
        self.assertEqual(game.level, 1)
        self.assertEqual(game.direction, 1)
        self.assertEqual(game.status, "playing")
        self.assertEqual(len(game.shields), 4 * 5 * 2)


class TestPlayerMovement(unittest.TestCase):
    def test_moves_and_clamps(self):
        game = new_game()
        move_player(game, -1)
        self.assertEqual(game.player_x, 29)
        game.player_x = 0
        move_player(game, -1)
        self.assertEqual(game.player_x, 0)
        game.player_x = game.width - 1
        move_player(game, 1)
        self.assertEqual(game.player_x, game.width - 1)

    def test_game_over_ignores_moves(self):
        game = new_game()
        game.status = "game_over"
        move_player(game, 1)
        self.assertEqual(game.player_x, 30)


class TestFormation(unittest.TestCase):
    def test_moves_right(self):
        game = small_game()
        move_formation(game)
        self.assertEqual(game.invaders[0].x, 31)

    def test_reverses_and_descends_at_right_edge(self):
        game = small_game()
        game.invaders[0].x = game.width - 1
        move_formation(game)
        self.assertEqual(game.direction, -1)
        self.assertEqual(game.invaders[0].x, game.width - 1)
        self.assertEqual(game.invaders[0].y, 6)

    def test_reverses_and_descends_at_left_edge(self):
        game = small_game()
        game.direction = -1
        game.invaders[0].x = 0
        move_formation(game)
        self.assertEqual(game.direction, 1)
        self.assertEqual(game.invaders[0].x, 0)
        self.assertEqual(game.invaders[0].y, 6)

    def test_step_moves_formation_only_on_its_tick(self):
        game = small_game()
        start_x = game.invaders[0].x
        for _ in range(move_interval(game) - 1):
            step(game, rng=NEVER)
        self.assertEqual(game.invaders[0].x, start_x)
        step(game, rng=NEVER)
        self.assertEqual(game.invaders[0].x, start_x + 1)

    def test_speed_increases_as_invaders_die_and_per_level(self):
        fresh = move_interval(new_game())
        mostly_dead = new_game()
        mostly_dead.invaders = mostly_dead.invaders[:5]
        self.assertLess(move_interval(mostly_dead), fresh)
        higher = new_game()
        higher.level = 3
        self.assertLess(move_interval(higher), fresh)
        self.assertGreaterEqual(move_interval(mostly_dead), 2)


class TestShooting(unittest.TestCase):
    def test_fire_spawns_one_bullet_only(self):
        game = new_game()
        self.assertTrue(fire_player(game))
        self.assertEqual(len(game.bullets), 1)
        self.assertEqual(game.bullets[0].x, game.player_x)
        self.assertEqual(game.bullets[0].y, game.player_y - 1)
        self.assertFalse(fire_player(game))
        self.assertEqual(len(game.bullets), 1)

    def test_bullet_rises_and_leaves(self):
        game = small_game()
        game.bullets = [Projectile(30, 3)]
        step(game, rng=NEVER)
        self.assertEqual([(b.x, b.y) for b in game.bullets], [(30, 2)])
        game.bullets = [Projectile(30, 1)]
        step(game, rng=NEVER)
        self.assertEqual(game.bullets, [])

    def test_bullet_kills_invader_and_scores_by_row(self):
        for row, expected in ((0, 30), (2, 20), (4, 10)):
            game = new_game()
            game.invaders = [Invader(30, 5, row), Invader(10, 5, 4)]
            game.bullets = [Projectile(30, 6)]
            step(game, rng=NEVER)
            self.assertEqual(len(game.invaders), 1)
            self.assertEqual(game.score, expected)
            self.assertEqual(game.bullets, [])

    def test_bullet_destroys_shield_without_scoring(self):
        game = small_game()
        cell = sorted(game.shields)[0]
        game.bullets = [Projectile(cell[0], cell[1] + 1)]
        step(game, rng=NEVER)
        self.assertNotIn(cell, game.shields)
        self.assertEqual(game.score, 0)
        self.assertEqual(game.bullets, [])

    def test_invader_fire_seeded_and_capped(self):
        game = new_game()
        rng = random.Random(7)
        for _ in range(200):
            step(game, rng=rng)
            self.assertLessEqual(len(game.bombs), 3)
            if game.status != "playing":
                break
        # A bomb always spawns directly below a bottom-most invader column.
        game = new_game()
        rng = random.Random(7)
        spawned = False
        for _ in range(200):
            before = len(game.bombs)
            step(game, rng=rng)
            if len(game.bombs) > before:
                spawned = True
                bomb = game.bombs[-1]
                column = [inv for inv in game.invaders if inv.x == bomb.x]
                self.assertTrue(column)
                self.assertEqual(bomb.y, max(inv.y for inv in column) + 1)
                break
        self.assertTrue(spawned)


class TestDamageAndEndings(unittest.TestCase):
    def test_bomb_destroys_shield(self):
        game = small_game()
        cell = sorted(game.shields)[0]
        game.bombs = [Projectile(cell[0], cell[1] - 1)]
        step(game, rng=NEVER)
        self.assertNotIn(cell, game.shields)
        self.assertEqual(game.bombs, [])

    def test_bomb_hits_player_costs_one_life_and_recentres(self):
        game = new_game()
        game.player_x = 10
        game.bombs = [Projectile(10, game.player_y - 1)]
        game.bullets = [Projectile(20, 10)]
        step(game, rng=NEVER)
        self.assertEqual(game.lives, 2)
        self.assertEqual(game.player_x, 30)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.bombs, [])
        self.assertEqual(game.status, "playing")

    def test_third_player_hit_ends_game(self):
        game = new_game()
        game.lives = 1
        game.bombs = [Projectile(game.player_x, game.player_y - 1)]
        step(game, rng=NEVER)
        self.assertEqual(game.status, "game_over")
        score = game.score
        step(game, rng=NEVER)
        self.assertEqual(game.score, score)  # game-over steps are no-ops

    def test_level_advances_when_formation_cleared(self):
        game = new_game()
        game.score = 50
        game.lives = 2
        game.invaders = [Invader(30, 5, 4)]
        game.bullets = [Projectile(30, 6)]
        step(game, rng=NEVER)
        self.assertEqual(game.level, 2)
        self.assertEqual(len(game.invaders), 55)
        self.assertEqual(game.score, 60)
        self.assertEqual(game.lives, 2)

    def test_invasion_ends_game(self):
        game = small_game()
        game.invaders[0].y = game.player_y
        step(game, rng=NEVER)
        self.assertEqual(game.status, "game_over")


class TestRenderAndCli(unittest.TestCase):
    def test_render_contains_key_elements(self):
        out = render(new_game())
        self.assertIn("SCORE 0", out)
        self.assertIn("LIVES 3", out)
        self.assertIn("^", out)
        self.assertIn("W", out)
        self.assertIn("#", out)
        self.assertIn("=" * 10, out)

    def test_render_game_over(self):
        game = new_game()
        game.status = "game_over"
        self.assertIn("GAME OVER", render(game))

    def test_cli_defaults_and_validation(self):
        args = parse_args([])
        self.assertEqual((args.width, args.height, args.tick_ms), (60, 24, 80))
        args = parse_args(["--width", "80", "--tick-ms", "100"])
        self.assertEqual((args.width, args.tick_ms), (80, 100))
        for bad in (["--width", "10"], ["--height", "5"],
                    ["--tick-ms", "5"]):
            with self.assertRaises(SystemExit):
                parse_args(bad)

    def test_build_formation_shape(self):
        formation = build_formation()
        self.assertEqual(len(formation), 55)
        self.assertEqual(score_for_row(0), 30)
        self.assertEqual(score_for_row(3), 20)
        self.assertEqual(score_for_row(4), 10)


if __name__ == "__main__":
    unittest.main()

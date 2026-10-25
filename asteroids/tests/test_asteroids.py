"""Unit tests for asteroids.py — pure logic only, no terminal."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asteroids import (  # noqa: E402
    WIDTH, HEIGHT, DAMPING, ROTATION, THRUST, BULLET_SPEED, BULLET_LIFE,
    MAX_BULLETS, LARGE, MEDIUM, SMALL, ASTEROID_SCORE, SAUCER_SCORE,
    Ship, Asteroid, Bullet, Saucer, Game, wrap, rotate_ship,
    apply_thrust, move_ship, move_asteroid, fire_bullet, split_asteroid,
    collides, spawn_level, spawn_saucer, new_game, step, ship_glyph,
    render_frame,
)


def game_with_rock(**rock_kw):
    """A game whose only asteroid is far from the ship, unless given."""
    game = Game()
    defaults = {"x": 5, "y": 5}
    defaults.update(rock_kw)
    game.asteroids = [Asteroid(**defaults)]
    return game


class TestWrap(unittest.TestCase):
    def test_past_right_edge_reenters_left(self):
        self.assertEqual(wrap(81, WIDTH), 1)
        self.assertEqual(wrap(-1, WIDTH), WIDTH - 1)
        self.assertEqual(wrap(24, HEIGHT), 0)

    def test_ship_and_asteroid_wrap_on_move(self):
        ship = Ship(x=WIDTH - 0.5, y=10, vx=1, vy=0)
        move_ship(ship)
        self.assertAlmostEqual(ship.x, 0.5)
        rock = Asteroid(x=10, y=HEIGHT - 0.2, vx=0, vy=0.5)
        move_asteroid(rock)
        self.assertAlmostEqual(rock.y, 0.3)


class TestShip(unittest.TestCase):
    def test_rotate_right_and_left(self):
        ship = Ship(angle=0)
        rotate_ship(ship, 1)
        self.assertAlmostEqual(ship.angle, ROTATION)
        rotate_ship(ship, -1)
        self.assertAlmostEqual(ship.angle, 0)

    def test_rotate_normalises_past_pi(self):
        ship = Ship(angle=math.pi)
        rotate_ship(ship, 1)
        self.assertAlmostEqual(ship.angle, -math.pi + ROTATION)

    def test_thrust_accelerates_in_facing_direction(self):
        ship = Ship(angle=-math.pi / 2)  # facing up
        apply_thrust(ship)
        self.assertAlmostEqual(ship.vx, 0)
        self.assertAlmostEqual(ship.vy, -THRUST)

    def test_damping_and_inertia(self):
        ship = Ship(x=40, y=12, vx=2, vy=0)
        move_ship(ship)
        self.assertAlmostEqual(ship.x, 42)
        self.assertAlmostEqual(ship.vx, 2 * DAMPING)
        # Still drifting next tick with no thrust applied.
        move_ship(ship)
        self.assertGreater(ship.x, 42)


class TestBullets(unittest.TestCase):
    def test_fires_from_nose_along_facing(self):
        game = game_with_rock()
        bullet = fire_bullet(game)
        self.assertEqual((bullet.x, bullet.y), (WIDTH / 2, HEIGHT / 2 - 2))
        self.assertAlmostEqual(bullet.vx, 0)
        self.assertAlmostEqual(bullet.vy, -BULLET_SPEED)

    def test_inherits_ship_velocity_and_travels_straight(self):
        game = game_with_rock()
        game.ship.vx, game.ship.vy = 1, 0
        bullet = fire_bullet(game)
        self.assertAlmostEqual(bullet.vx, 1)
        self.assertAlmostEqual(bullet.vy, -BULLET_SPEED)
        x, y = bullet.x, bullet.y
        step(game)  # bullet moves; ship/rock far apart, no collision
        moved = game.bullets[0]
        self.assertAlmostEqual(moved.x - x, 1)
        self.assertAlmostEqual(moved.y - y, -BULLET_SPEED)

    def test_bullet_expires(self):
        game = game_with_rock()
        game.bullets = [Bullet(x=10, y=10, vx=0, vy=0, life=1)]
        step(game)
        self.assertEqual(game.bullets, [])

    def test_bullet_cap(self):
        game = game_with_rock()
        for _ in range(MAX_BULLETS):
            self.assertIsNotNone(fire_bullet(game))
        self.assertIsNone(fire_bullet(game))
        self.assertEqual(len(game.bullets), MAX_BULLETS)


class TestAsteroids(unittest.TestCase):
    def test_large_splits_into_two_faster_mediums(self):
        rock = Asteroid(x=20, y=10, vx=0.3, vy=0, size=LARGE)
        kids = split_asteroid(rock)
        self.assertEqual(len(kids), 2)
        self.assertTrue(all(k.size == MEDIUM for k in kids))
        self.assertTrue(all(math.hypot(k.vx, k.vy) > 0.3 for k in kids))
        # Symmetric about the parent heading: vx matches, vy differs.
        self.assertNotAlmostEqual(kids[0].vy, kids[1].vy)

    def test_medium_splits_into_smalls_and_small_dies(self):
        kids = split_asteroid(Asteroid(size=MEDIUM))
        self.assertEqual(len(kids), 2)
        self.assertTrue(all(k.size == SMALL for k in kids))
        self.assertEqual(split_asteroid(Asteroid(size=SMALL)), [])

    def test_stationary_parent_children_still_move(self):
        kids = split_asteroid(Asteroid(vx=0, vy=0, size=LARGE))
        self.assertTrue(all(math.hypot(k.vx, k.vy) > 0 for k in kids))

    def test_bullet_hit_scores_and_splits(self):
        game = game_with_rock(x=40, y=5, vx=0, vy=0, size=LARGE)
        game.bullets = [Bullet(x=40, y=5, vx=0, vy=0)]
        step(game)
        self.assertEqual(game.bullets, [])
        self.assertEqual(game.score, ASTEROID_SCORE[LARGE])
        self.assertEqual(len(game.asteroids), 2)
        self.assertTrue(all(r.size == MEDIUM for r in game.asteroids))

    def test_small_hit_scores_most_and_clears_level(self):
        game = game_with_rock(x=40, y=5, vx=0, vy=0, size=SMALL)
        game.bullets = [Bullet(x=40, y=5, vx=0, vy=0)]
        step(game)
        self.assertEqual(game.score, ASTEROID_SCORE[SMALL])
        # Field cleared -> next level spawns a larger field.
        self.assertEqual(game.level, 2)
        self.assertEqual(len(game.asteroids), 5)
        self.assertTrue(all(r.size == LARGE for r in game.asteroids))

    def test_miss_scores_nothing(self):
        game = game_with_rock()
        game.bullets = [Bullet(x=70, y=20, vx=0, vy=0)]
        step(game)
        self.assertEqual(game.score, 0)
        self.assertEqual(len(game.asteroids), 1)


class TestCollisionsLivesLevels(unittest.TestCase):
    def test_ship_hit_loses_life_and_respawns_invulnerable(self):
        game = game_with_rock(x=WIDTH / 2, y=HEIGHT / 2, vx=0, vy=0)
        step(game)
        self.assertEqual(game.lives, 2)
        self.assertEqual((game.ship.x, game.ship.y), (WIDTH / 2, HEIGHT / 2))
        self.assertGreater(game.invulnerable, 0)
        self.assertFalse(game.game_over)

    def test_invulnerable_ship_loses_no_life(self):
        game = game_with_rock(x=WIDTH / 2, y=HEIGHT / 2, vx=0, vy=0)
        game.invulnerable = 5
        step(game)
        self.assertEqual(game.lives, 3)

    def test_last_life_ends_game_and_freezes(self):
        game = game_with_rock(x=WIDTH / 2, y=HEIGHT / 2, vx=0, vy=0)
        game.lives = 1
        step(game)
        self.assertTrue(game.game_over)
        tick = game.tick
        step(game)
        self.assertEqual(game.tick, tick)  # frozen

    def test_clearing_level_keeps_score_and_lives(self):
        game = game_with_rock(x=40, y=5, vx=0, vy=0, size=SMALL)
        game.score = 500
        game.lives = 2
        game.bullets = [Bullet(x=40, y=5, vx=0, vy=0)]
        step(game)
        self.assertEqual(game.level, 2)
        self.assertEqual(game.score, 500 + ASTEROID_SCORE[SMALL])
        self.assertEqual(game.lives, 2)

    def test_collides_boundary(self):
        self.assertTrue(collides(0, 0, 1, 2, 0, 1))   # touching
        self.assertFalse(collides(0, 0, 1, 2.1, 0, 1))  # apart


class TestSaucer(unittest.TestCase):
    def test_spawn_crosses_horizontally_from_an_edge(self):
        game = Game(rng=__import__("random").Random(7))
        saucer = spawn_saucer(game)
        self.assertIn(saucer.x, (0.0, WIDTH - 1.0))
        self.assertEqual(abs(saucer.vx), 0.4)
        self.assertTrue(2 <= saucer.y <= HEIGHT - 2)

    def test_saucer_wraps_and_can_be_shot(self):
        game = game_with_rock()
        game.saucer = Saucer(x=WIDTH - 0.2, y=10, vx=0.4)
        step(game)
        self.assertAlmostEqual(game.saucer.x, 0.2)
        game.saucer = Saucer(x=30, y=10, vx=0.4)
        game.bullets = [Bullet(x=30, y=10, vx=0, vy=0)]
        step(game)
        self.assertIsNone(game.saucer)
        self.assertEqual(game.score, SAUCER_SCORE)

    def test_ship_hitting_saucer_loses_life(self):
        game = game_with_rock()
        game.saucer = Saucer(x=WIDTH / 2, y=HEIGHT / 2, vx=0)
        step(game)
        self.assertEqual(game.lives, 2)


class TestSpawnAndRender(unittest.TestCase):
    def test_level_spawn_count_and_clearance(self):
        game = new_game(seed=1)
        self.assertEqual(len(game.asteroids), 4)  # 3 + level 1
        for rock in game.asteroids:
            dist = math.hypot(rock.x - WIDTH / 2, rock.y - HEIGHT / 2)
            self.assertGreaterEqual(dist, 12)

    def test_seeded_spawns_are_deterministic(self):
        a, b = new_game(seed=42), new_game(seed=42)
        self.assertEqual([(r.x, r.y) for r in a.asteroids],
                         [(r.x, r.y) for r in b.asteroids])

    def test_render_shape_and_glyphs(self):
        game = game_with_rock(x=5, y=5, size=LARGE)
        game.bullets = [Bullet(x=7, y=5, vx=0, vy=0)]
        game.saucer = Saucer(x=9, y=5, vx=0)
        frame = render_frame(game)
        self.assertEqual(len(frame), HEIGHT)
        self.assertTrue(all(len(row) == WIDTH for row in frame))
        self.assertEqual(frame[5][5], "O")
        self.assertEqual(frame[5][7], "*")
        self.assertEqual(frame[5][9], "U")
        # Ship starts facing up at the centre.
        self.assertEqual(frame[HEIGHT // 2][WIDTH // 2], "^")

    def test_ship_glyph_octants(self):
        self.assertEqual(ship_glyph(0), ">")
        self.assertEqual(ship_glyph(math.pi / 2), "v")
        self.assertEqual(ship_glyph(math.pi), "<")
        self.assertEqual(ship_glyph(-math.pi / 2), "^")

    def test_step_input_rotate_thrust_fire(self):
        game = game_with_rock()
        step(game, rotate=1, thrust=True, fire=True)
        # Ship starts facing up (-pi/2); one right rotation adds ROTATION.
        self.assertAlmostEqual(game.ship.angle, -math.pi / 2 + ROTATION)
        self.assertNotEqual(len(game.bullets), 0)
        self.assertNotEqual((game.ship.vx, game.ship.vy), (0, 0))


if __name__ == "__main__":
    unittest.main()

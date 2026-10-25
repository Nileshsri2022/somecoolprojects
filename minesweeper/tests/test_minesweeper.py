"""Unit tests for minesweeper.py — library only, no terminal needed."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from minesweeper import (Board, create_board, ensure_safe_first_click,
                         mines_remaining, neighbour_count, render,
                         reveal, toggle_flag)


def board_with_mines(rows, cols, mines):
    return Board(rows, cols, set(mines))


class TestCreateBoard(unittest.TestCase):
    def test_exact_mine_count(self):
        b = create_board(9, 9, 10, seed=1)
        self.assertEqual(len(b.mines), 10)

    def test_seed_deterministic(self):
        a = create_board(9, 9, 10, seed=42)
        b = create_board(9, 9, 10, seed=42)
        self.assertEqual(a.mines, b.mines)

    def test_different_seeds_differ(self):
        a = create_board(9, 9, 10, seed=1)
        b = create_board(9, 9, 10, seed=2)
        self.assertNotEqual(a.mines, b.mines)

    def test_safe_cell_never_mined(self):
        for seed in range(20):
            b = create_board(5, 5, 10, seed=seed, safe_cell=(2, 2))
            self.assertNotIn((2, 2), b.mines)

    def test_zero_mines_allowed(self):
        b = create_board(3, 3, 0)
        self.assertEqual(len(b.mines), 0)

    def test_invalid_dimensions(self):
        for rows, cols in [(0, 5), (5, 0), (-1, 5)]:
            with self.assertRaises(ValueError):
                create_board(rows, cols, 1)

    def test_too_many_mines(self):
        # Must leave at least one safe cell.
        with self.assertRaises(ValueError):
            create_board(3, 3, 9)
        with self.assertRaises(ValueError):
            create_board(3, 3, 10)
        with self.assertRaises(ValueError):
            create_board(3, 3, -1)

    def test_safe_cell_out_of_bounds(self):
        with self.assertRaises(ValueError):
            create_board(3, 3, 1, safe_cell=(3, 0))


class TestNeighbourCount(unittest.TestCase):
    def test_corner_edge_centre(self):
        # Mines at (0,0) and (1,1) on a 3x3 board.
        b = board_with_mines(3, 3, [(0, 0), (1, 1)])
        self.assertEqual(neighbour_count(b, 0, 1), 2)
        self.assertEqual(neighbour_count(b, 1, 0), 2)
        self.assertEqual(neighbour_count(b, 0, 2), 1)
        self.assertEqual(neighbour_count(b, 2, 2), 1)
        self.assertEqual(neighbour_count(b, 2, 0), 1)

    def test_zero_and_max(self):
        b = board_with_mines(3, 3, [])
        self.assertEqual(neighbour_count(b, 1, 1), 0)
        ring = [(r, c) for r in range(3) for c in range(3)
                if (r, c) != (1, 1)]
        b = board_with_mines(3, 3, ring)
        self.assertEqual(neighbour_count(b, 1, 1), 8)

    def test_mine_cell_returns_none(self):
        b = board_with_mines(3, 3, [(1, 1)])
        self.assertIsNone(neighbour_count(b, 1, 1))


class TestReveal(unittest.TestCase):
    def test_numbered_reveal_only(self):
        b = board_with_mines(3, 3, [(0, 0)])
        self.assertEqual(reveal(b, 0, 1), "ok")
        self.assertEqual(b.revealed, {(0, 1)})
        self.assertEqual(b.status, "playing")

    def test_flood_stops_at_numbers(self):
        # Single mine in the corner; everything else is 0 or numbered.
        b = board_with_mines(4, 4, [(0, 0)])
        self.assertEqual(reveal(b, 3, 3), "ok")
        # The mine cell itself is never flood-revealed.
        self.assertNotIn((0, 0), b.revealed)
        # Numbered ring around the mine is revealed, but no further.
        self.assertIn((0, 1), b.revealed)
        self.assertIn((1, 0), b.revealed)
        self.assertIn((1, 1), b.revealed)
        self.assertIn((3, 3), b.revealed)
        # Flood on a board with one mine reveals all safe cells -> win.
        self.assertEqual(b.status, "won")

    def test_flood_does_not_cross_mine_wall(self):
        # A full row of mines splits the board; flood from below
        # must not reveal anything above the wall.
        mines = [(2, c) for c in range(5)]
        b = board_with_mines(5, 5, mines)
        reveal(b, 4, 0)
        for r in range(2):
            for c in range(5):
                self.assertNotIn((r, c), b.revealed)
        self.assertIn((4, 0), b.revealed)
        self.assertIn((3, 0), b.revealed)  # numbered neighbour row

    def test_hit_mine_loses(self):
        b = board_with_mines(3, 3, [(1, 1)])
        self.assertEqual(reveal(b, 1, 1), "mine")
        self.assertEqual(b.status, "lost")

    def test_reveal_flagged_ignored(self):
        b = board_with_mines(3, 3, [(0, 0)])
        toggle_flag(b, 1, 1)
        self.assertEqual(reveal(b, 1, 1), "ignored")
        self.assertNotIn((1, 1), b.revealed)
        self.assertEqual(b.status, "playing")

    def test_reveal_revealed_ignored(self):
        b = board_with_mines(3, 3, [(0, 0)])
        reveal(b, 0, 1)
        self.assertEqual(reveal(b, 0, 1), "ignored")

    def test_reveal_out_of_bounds_ignored(self):
        b = board_with_mines(3, 3, [(0, 0)])
        for cell in [(-1, 0), (0, -1), (3, 0), (0, 3)]:
            self.assertEqual(reveal(b, *cell), "ignored")
        self.assertEqual(b.revealed, set())

    def test_reveal_after_game_over_ignored(self):
        b = board_with_mines(3, 3, [(1, 1)])
        reveal(b, 1, 1)  # lose
        self.assertEqual(reveal(b, 0, 0), "ignored")
        self.assertNotIn((0, 0), b.revealed)


class TestFlags(unittest.TestCase):
    def test_toggle_on_off(self):
        b = board_with_mines(3, 3, [(0, 0)])
        self.assertTrue(toggle_flag(b, 1, 1))
        self.assertIn((1, 1), b.flagged)
        self.assertTrue(toggle_flag(b, 1, 1))
        self.assertNotIn((1, 1), b.flagged)

    def test_flag_revealed_ignored(self):
        b = board_with_mines(3, 3, [(0, 0)])
        reveal(b, 0, 1)
        self.assertFalse(toggle_flag(b, 0, 1))
        self.assertNotIn((0, 1), b.flagged)

    def test_flag_out_of_bounds_ignored(self):
        b = board_with_mines(3, 3, [])
        self.assertFalse(toggle_flag(b, 9, 9))

    def test_flag_blocks_reveal_until_removed(self):
        b = board_with_mines(3, 3, [(0, 0)])
        toggle_flag(b, 0, 1)
        self.assertEqual(reveal(b, 0, 1), "ignored")
        toggle_flag(b, 0, 1)
        self.assertEqual(reveal(b, 0, 1), "ok")

    def test_mines_remaining(self):
        b = board_with_mines(3, 3, [(0, 0), (2, 2)])
        self.assertEqual(mines_remaining(b), 2)
        toggle_flag(b, 0, 0)
        self.assertEqual(mines_remaining(b), 1)


class TestWin(unittest.TestCase):
    def test_reveal_last_safe_cell_wins(self):
        b = board_with_mines(2, 2, [(0, 0)])
        reveal(b, 0, 1)
        self.assertEqual(b.status, "playing")
        reveal(b, 1, 0)
        self.assertEqual(b.status, "playing")
        reveal(b, 1, 1)
        self.assertEqual(b.status, "won")

    def test_flagging_all_mines_is_not_a_win(self):
        b = board_with_mines(2, 2, [(0, 0)])
        toggle_flag(b, 0, 0)
        self.assertEqual(b.status, "playing")

    def test_zero_mine_board_wins_on_flood(self):
        b = board_with_mines(3, 3, [])
        reveal(b, 0, 0)
        self.assertEqual(b.status, "won")
        self.assertEqual(len(b.revealed), 9)


class TestSafeFirstClick(unittest.TestCase):
    def test_moves_mine_off_cell(self):
        b = board_with_mines(3, 3, [(1, 1)])
        ensure_safe_first_click(b, (1, 1))
        self.assertNotIn((1, 1), b.mines)
        self.assertEqual(len(b.mines), 1)

    def test_noop_when_safe(self):
        b = board_with_mines(3, 3, [(0, 0)])
        ensure_safe_first_click(b, (2, 2))
        self.assertEqual(b.mines, frozenset({(0, 0)}))


class TestRender(unittest.TestCase):
    def test_hidden_flagged_numbered(self):
        b = board_with_mines(3, 3, [(0, 0)])
        reveal(b, 0, 1)  # count 1
        toggle_flag(b, 2, 2)
        out = render(b)
        self.assertIn("Mines remaining: 0", out)
        lines = out.splitlines()
        # Row 1 (index 2): hidden mine '.', revealed '1', hidden '.'
        # (slice past the row label so the label '1' can't fake a pass)
        self.assertIn("1", lines[2][2:])
        self.assertIn("F", lines[4])

    def test_lost_render_shows_mines(self):
        b = board_with_mines(2, 2, [(0, 0)])
        reveal(b, 0, 0)
        self.assertIn("*", render(b))

    def test_won_render_shows_all_safe(self):
        b = board_with_mines(2, 2, [(0, 0)])
        reveal(b, 0, 1)
        reveal(b, 1, 0)
        reveal(b, 1, 1)
        out = render(b)
        # Mine cell stays hidden ('.'); every safe cell is revealed.
        self.assertIn(".", out.splitlines()[2])
        self.assertNotIn(".", out.splitlines()[3][2:])

    def test_zero_count_renders_blank(self):
        b = board_with_mines(3, 3, [])
        reveal(b, 1, 1)
        lines = render(b).splitlines()
        # Middle row's cells (past the row label '2') contain no digits.
        self.assertFalse(any(ch.isdigit() for ch in lines[3][2:]))


if __name__ == "__main__":
    unittest.main()

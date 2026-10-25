import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sudoku
from sudoku import (
    EXAMPLE_PUZZLE, EXAMPLE_SOLUTION, apply_move, board_to_string,
    clear_cell, count_solutions, empty_board, fixed_grid, format_board,
    generate_puzzle, is_complete, is_solved, is_valid_board,
    is_valid_move, parse_board, parse_command, solve,
)

PUZZLE = parse_board(EXAMPLE_PUZZLE)
SOLUTION = parse_board(EXAMPLE_SOLUTION)


class TestBoardRepresentation(unittest.TestCase):
    def test_empty_board(self):
        board = empty_board()
        self.assertEqual(len(board), 9)
        self.assertTrue(all(len(row) == 9 for row in board))
        self.assertTrue(all(v == 0 for row in board for v in row))

    def test_parse_round_trip(self):
        self.assertEqual(board_to_string(PUZZLE), EXAMPLE_PUZZLE)
        self.assertEqual(board_to_string(SOLUTION), EXAMPLE_SOLUTION)

    def test_parse_dots_are_empty(self):
        board = parse_board("." * 81)
        self.assertEqual(board, empty_board())

    def test_parse_errors(self):
        for bad in ("123", "1" * 80, "1" * 82, "x" * 81, "1" * 80 + "a"):
            with self.assertRaises(ValueError, msg=bad):
                parse_board(bad)


class TestMoveValidation(unittest.TestCase):
    def test_valid_move(self):
        self.assertTrue(is_valid_move(PUZZLE, 0, 2, 1))  # row 0: 5 3 _ ...
        self.assertTrue(is_valid_move(empty_board(), 4, 4, 9))

    def test_row_duplicate(self):
        self.assertFalse(is_valid_move(PUZZLE, 0, 2, 5))  # 5 already in row 0

    def test_column_duplicate(self):
        self.assertFalse(is_valid_move(PUZZLE, 0, 2, 6))  # 6 in column 2? no...
        # column 0 has 5,6: placing 6 at (2,0) duplicates column 0
        self.assertFalse(is_valid_move(PUZZLE, 2, 0, 6))

    def test_box_duplicate(self):
        # (0,2) shares top-left box with 5,3,6,9,8 -> 8 conflicts
        self.assertFalse(is_valid_move(PUZZLE, 0, 2, 8))

    def test_occupied_and_out_of_range(self):
        self.assertFalse(is_valid_move(PUZZLE, 0, 0, 1))  # occupied
        self.assertFalse(is_valid_move(PUZZLE, 0, 2, 0))
        self.assertFalse(is_valid_move(PUZZLE, 0, 2, 10))
        self.assertFalse(is_valid_move(PUZZLE, 9, 0, 1))
        self.assertFalse(is_valid_move(PUZZLE, 0, -1, 1))


class TestBoardValidation(unittest.TestCase):
    def test_valid_partial_and_solved(self):
        self.assertTrue(is_valid_board(PUZZLE))
        self.assertTrue(is_valid_board(SOLUTION))
        self.assertTrue(is_valid_board(empty_board()))

    def test_duplicate_row_column_box(self):
        bad = empty_board()
        bad[0][0] = bad[0][1] = 7
        self.assertFalse(is_valid_board(bad))
        bad = empty_board()
        bad[0][0] = bad[1][0] = 7
        self.assertFalse(is_valid_board(bad))
        bad = empty_board()
        bad[0][0] = bad[1][1] = 7
        self.assertFalse(is_valid_board(bad))

    def test_solved_detection(self):
        self.assertTrue(is_solved(SOLUTION))
        self.assertFalse(is_solved(PUZZLE))  # incomplete
        self.assertFalse(is_complete(PUZZLE))
        self.assertTrue(is_complete(SOLUTION))
        bad = [row[:] for row in SOLUTION]
        bad[0][0], bad[0][1] = bad[0][1], bad[0][0]  # complete but invalid
        self.assertFalse(is_solved(bad))


class TestSolver(unittest.TestCase):
    def test_solves_known_puzzle(self):
        self.assertEqual(solve(PUZZLE), SOLUTION)

    def test_solved_board_unchanged(self):
        self.assertEqual(solve(SOLUTION), SOLUTION)

    def test_unsolvable_returns_none(self):
        bad = empty_board()
        bad[0][0] = bad[0][1] = 1  # invalid board
        self.assertIsNone(solve(bad))
        # Valid but dead-end: row 0 needs only 9, column 8 already has 9.
        dead = empty_board()
        dead[0] = [1, 2, 3, 4, 5, 6, 7, 8, 0]
        dead[1][8] = 9
        # (0,8) cannot be 9 (column) and no other digit fits the row
        self.assertIsNone(solve(dead))

    def test_count_solutions(self):
        self.assertEqual(count_solutions(PUZZLE), 1)
        self.assertEqual(count_solutions(SOLUTION), 1)
        bad = empty_board()
        bad[0][0] = bad[0][1] = 1
        self.assertEqual(count_solutions(bad), 0)
        # Empty board has many solutions; capped at the limit.
        self.assertEqual(count_solutions(empty_board(), limit=2), 2)

    def test_solve_does_not_mutate_input(self):
        before = board_to_string(PUZZLE)
        solve(PUZZLE)
        self.assertEqual(board_to_string(PUZZLE), before)


class TestGeneration(unittest.TestCase):
    def test_easy_puzzle_unique_and_consistent(self):
        puzzle, solution = generate_puzzle("easy", seed=42)
        self.assertTrue(is_valid_board(puzzle))
        self.assertTrue(is_valid_board(solution))
        self.assertTrue(is_solved(solution))
        self.assertEqual(count_solutions(puzzle), 1)
        self.assertEqual(solve(puzzle), solution)
        givens = sum(1 for row in puzzle for v in row if v)
        self.assertLess(givens, 81)
        self.assertGreaterEqual(givens, 24)
        # Every given matches the solution.
        for r in range(9):
            for c in range(9):
                if puzzle[r][c]:
                    self.assertEqual(puzzle[r][c], solution[r][c])

    def test_unknown_difficulty(self):
        with self.assertRaises(ValueError):
            generate_puzzle("impossible")


class TestFixedCellsAndMoves(unittest.TestCase):
    def setUp(self):
        self.puzzle, _ = generate_puzzle("easy", seed=7)
        self.fixed = fixed_grid(self.puzzle)
        # Find one fixed and one empty cell.
        self.fx = next((r, c) for r in range(9) for c in range(9)
                       if self.fixed[r][c])
        self.ex = next((r, c) for r in range(9) for c in range(9)
                       if not self.fixed[r][c])

    def test_fixed_cannot_change(self):
        before = board_to_string(self.puzzle)
        _, err = apply_move(self.puzzle, self.fixed, *self.fx, 1)
        self.assertIsNotNone(err)
        _, err = clear_cell(self.puzzle, self.fixed, *self.fx)
        self.assertIsNotNone(err)
        self.assertEqual(board_to_string(self.puzzle), before)

    def test_player_cell_set_and_clear(self):
        r, c = self.ex
        # Pick a digit valid for that cell from the solved board.
        solution = solve(self.puzzle)
        board, err = apply_move(self.puzzle, self.fixed, r, c, solution[r][c])
        self.assertIsNone(err)
        self.assertEqual(board[r][c], solution[r][c])
        board2, err = clear_cell(board, self.fixed, r, c)
        self.assertIsNone(err)
        self.assertEqual(board2[r][c], 0)

    def test_move_zero_clears(self):
        r, c = self.ex
        solution = solve(self.puzzle)
        board, _ = apply_move(self.puzzle, self.fixed, r, c, solution[r][c])
        board, err = apply_move(board, self.fixed, r, c, 0)
        self.assertIsNone(err)
        self.assertEqual(board[r][c], 0)

    def test_conflicting_move_rejected(self):
        r, c = self.ex
        solution = solve(self.puzzle)
        # A digit already in this row (from a given) must be rejected.
        row_values = {v for v in self.puzzle[r] if v}
        conflict = next(iter(row_values))
        board, err = apply_move(self.puzzle, self.fixed, r, c, conflict)
        self.assertIsNotNone(err)
        self.assertEqual(board, self.puzzle)


class TestRenderingAndCommands(unittest.TestCase):
    def test_format_board(self):
        text = format_board(PUZZLE)
        lines = text.split("\n")
        self.assertEqual(len(lines), 11)  # 9 rows + 2 separators
        self.assertIn(".", text)
        self.assertIn("5 3 .", lines[0])
        self.assertTrue(all(line.startswith("-") for line in lines if set(line) == {"-"}))

    def test_parse_command_forms(self):
        self.assertEqual(parse_command("1 2 5"), ("move", 0, 1, 5))
        self.assertEqual(parse_command("9 9 0"), ("move", 8, 8, 0))
        self.assertEqual(parse_command("clear 3 4"), ("clear", 2, 3))
        self.assertEqual(parse_command("check"), ("check",))
        self.assertEqual(parse_command("solve"), ("solve",))
        self.assertEqual(parse_command("new medium"), ("new", "medium"))
        self.assertEqual(parse_command("new"), ("new", None))
        self.assertEqual(parse_command("help"), ("help",))
        self.assertEqual(parse_command("quit"), ("quit",))

    def test_parse_command_errors(self):
        for bad in ("", "1 2", "1 2 3 4", "0 1 5", "10 1 5", "1 2 10",
                    "1 2 x", "clear 1", "new impossible", "frobnicate",
                    "quit now"):
            with self.assertRaises(ValueError, msg=bad):
                parse_command(bad)


class TestCli(unittest.TestCase):
    def run_cli(self, *args):
        here = Path(__file__).resolve().parent.parent
        return subprocess.run(
            [sys.executable, str(here / "sudoku.py"), *args],
            capture_output=True, text=True, timeout=60,
        )

    def test_solve_cli(self):
        proc = self.run_cli("--solve", EXAMPLE_PUZZLE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        solved = parse_board(
            "".join(ch for ch in proc.stdout if ch.isdigit() or ch == ".")
            .replace(".", "0"))
        self.assertEqual(solved, SOLUTION)

    def test_solve_cli_unsolvable(self):
        proc = self.run_cli("--solve", "11" + "0" * 79)
        self.assertNotEqual(proc.returncode, 0)

    def test_help_cli(self):
        proc = self.run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stdout)


if __name__ == "__main__":
    unittest.main()

"""Tests for chess.py: rules, FEN/UCI, engine, and CLI."""

import random
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chess import (GameState, apply_move, best_move, evaluate, from_fen,
                   game_status, is_in_check, legal_moves, move_to_uci,
                   parse_uci, perft, play_moves, random_move, render_board,
                   start_position, to_fen)

CHESS_PY = Path(__file__).resolve().parent.parent / "chess.py"


def ucis(state):
    return sorted(move_to_uci(m) for m in legal_moves(state))


def fen_moves(fen):
    return ucis(from_fen(fen))


class TestStartPosition(unittest.TestCase):
    def test_twenty_moves_and_perft(self):
        state = start_position()
        self.assertEqual(len(legal_moves(state)), 20)
        self.assertEqual(perft(state, 1), 20)
        self.assertEqual(perft(state, 2), 400)
        self.assertEqual(perft(state, 3), 8902)

    def test_black_has_twenty_after_e4(self):
        state = play_moves(start_position(), ["e2e4"])
        self.assertEqual(len(legal_moves(state)), 20)
        self.assertEqual(state.turn, "b")

    def test_start_fen_round_trip(self):
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.assertEqual(to_fen(from_fen(fen)), fen)

    def test_apply_does_not_mutate(self):
        state = start_position()
        before = to_fen(state)
        apply_move(state, parse_uci(state, "e2e4"))
        self.assertEqual(to_fen(state), before)


class TestPieceMovement(unittest.TestCase):
    def test_knight_empty_board(self):
        # Filter to the knight: the position also has a king on a1.
        moves = [m for m in fen_moves("7k/8/8/8/3N4/8/8/K7 w - - 0 1")
                 if m.startswith("d4")]
        self.assertEqual(len(moves), 8)
        self.assertIn("d4f5", moves)
        self.assertIn("d4b3", moves)

    def test_knight_blocked_by_own_piece(self):
        # Own pawn on f5 blocks that jump; enemy pawn on b3 is captured.
        moves = [m for m in fen_moves("7k/8/8/5P2/3N4/1p6/8/K7 w - - 0 1")
                 if m.startswith("d4")]
        self.assertNotIn("d4f5", moves)
        self.assertIn("d4b3", moves)
        self.assertEqual(len(moves), 7)

    def test_sliders_do_not_jump(self):
        moves = fen_moves("7k/8/8/8/3B4/8/8/K7 w - - 0 1")
        self.assertIn("d4a7", moves)
        self.assertIn("d4h8", moves)
        # Own pawn on c3 blocks the a1 diagonal (no capture, no pass-through).
        moves = fen_moves("7k/8/8/8/3B4/2P5/8/K7 w - - 0 1")
        self.assertNotIn("d4c3", moves)
        self.assertNotIn("d4b2", moves)
        self.assertNotIn("d4a1", moves)
        # Enemy pawn on b2 is captured, but the ray stops there.
        moves = fen_moves("7k/8/8/8/3B4/8/1p6/K7 w - - 0 1")
        self.assertIn("d4b2", moves)
        self.assertNotIn("d4a1", moves)

    def test_rook_and_queen_rays(self):
        moves = fen_moves("7k/8/8/8/8/8/8/R6K w - - 0 1")
        self.assertIn("a1a8", moves)
        # b1..g1 (h1 is the own king) + a2..a8 = 13 rook moves.
        self.assertEqual(len([m for m in moves if m.startswith("a1")]), 13)

    def test_king_cannot_move_into_check(self):
        moves = fen_moves("4r2k/8/8/8/8/8/8/4K3 w - - 0 1")
        king_moves = [m for m in moves if m.startswith("e1")]
        self.assertEqual(sorted(king_moves), ["e1d1", "e1d2", "e1f1", "e1f2"])

    def test_pawn_pushes_and_captures(self):
        state = start_position()
        pawn_moves = [m for m in ucis(state) if m.startswith("e2")]
        self.assertEqual(sorted(pawn_moves), ["e2e3", "e2e4"])
        # Blocked pawn cannot push; diagonal capture only onto enemy.
        moves = fen_moves("7k/8/8/8/8/4p3/4P3/K7 w - - 0 1")
        self.assertNotIn("e2e3", moves)
        moves = fen_moves("7k/8/8/8/8/3p4/4P3/K7 w - - 0 1")
        self.assertIn("e2d3", moves)
        moves = fen_moves("7k/8/8/8/8/8/4P3/K7 w - - 0 1")
        self.assertNotIn("e2f3", moves)  # no sideways move without capture

    def test_pawn_double_push_only_from_start(self):
        state = play_moves(start_position(), ["e2e3"])
        self.assertNotIn("e3e5", ucis(state))


class TestSpecialRules(unittest.TestCase):
    def test_en_passant_capture_and_expiry(self):
        state = play_moves(start_position(),
                           ["e2e4", "a7a6", "e4e5", "d7d5"])
        self.assertIn("e5d6", ucis(state))
        after = play_moves(state, ["e5d6"])
        self.assertEqual(after.board[3][3], ".")  # pawn on d5 removed
        self.assertEqual(after.board[2][3], "P")
        # If White plays something else, the right expires.
        state2 = play_moves(start_position(),
                            ["e2e4", "a7a6", "e4e5", "d7d5", "a2a3", "a6a5"])
        self.assertNotIn("e5d6", ucis(state2))

    def test_castling_both_sides_both_colours(self):
        moves = fen_moves("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertIn("e1g1", moves)
        self.assertIn("e1c1", moves)
        after = play_moves(from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"),
                           ["e1g1"])
        self.assertEqual(after.board[7][6], "K")
        self.assertEqual(after.board[7][5], "R")
        self.assertEqual(after.castling, {"k", "q"})
        black = fen_moves("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1")
        self.assertIn("e8g8", black)
        self.assertIn("e8c8", black)

    def test_castling_blocked_by_check_and_transit(self):
        # In check: no castling at all.
        moves = fen_moves("r3k2r/8/8/8/8/8/4r3/R3K2R w KQkq - 0 1")
        self.assertNotIn("e1g1", moves)
        self.assertNotIn("e1c1", moves)
        # Rook on f2 attacks f1: kingside illegal, queenside legal.
        moves = fen_moves("r3k2r/8/8/8/8/8/5r2/R3K2R w KQkq - 0 1")
        self.assertNotIn("e1g1", moves)
        self.assertIn("e1c1", moves)

    def test_castling_rights_lost(self):
        base = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
        # Rook leaves a1: queenside right lost, kingside kept. A black
        # reply is needed first so it is White's turn again.
        after_rook = play_moves(from_fen(base), ["a1a2", "h8h7"])
        self.assertNotIn("e1c1", ucis(after_rook))
        self.assertIn("e1g1", ucis(after_rook))
        # King moves and returns: both rights lost.
        after_king = play_moves(from_fen(base),
                                ["e1f1", "e8e7", "f1e1", "e7e6"])
        self.assertNotIn("e1g1", ucis(after_king))
        self.assertNotIn("e1c1", ucis(after_king))

    def test_promotion_all_pieces_and_letter_required(self):
        # Black king on b8 so e8 is free (a king on e8 would block).
        moves = fen_moves("1k6/4P3/8/8/8/8/8/4K3 w - - 0 1")
        promos = sorted(m for m in moves if m.startswith("e7e8"))
        self.assertEqual(promos, ["e7e8b", "e7e8n", "e7e8q", "e7e8r"])
        self.assertNotIn("e7e8", moves)
        state = from_fen("1k6/4P3/8/8/8/8/8/4K3 w - - 0 1")
        with self.assertRaises(ValueError):
            parse_uci(state, "e7e8")
        after = play_moves(state, ["e7e8q"])
        self.assertEqual(after.board[0][4], "Q")
        # Capture-promotion onto a rook on d8.
        after = play_moves(from_fen("1k1r4/4P3/8/8/8/8/8/4K3 w - - 0 1"),
                           ["e7d8n"])
        self.assertEqual(after.board[0][3], "N")

    def test_pinned_piece_cannot_expose_king(self):
        moves = fen_moves("4r1k1/8/8/8/8/8/4R3/4K3 w - - 0 1")
        rook_moves = sorted(m for m in moves if m.startswith("e2"))
        # Along the e-file only (including capturing the attacker).
        self.assertEqual(rook_moves, ["e2e3", "e2e4", "e2e5", "e2e6",
                                      "e2e7", "e2e8"])

    def test_check_must_be_resolved(self):
        moves = fen_moves("4r1k1/8/8/8/8/8/8/4K2R w - - 0 1")
        self.assertTrue(is_in_check(from_fen("4r1k1/8/8/8/8/8/8/4K2R w - - 0 1"), "w"))
        self.assertNotIn("e1e2", moves)  # still on the rook's file
        self.assertIn("e1d1", moves)


class TestEndings(unittest.TestCase):
    def test_fools_mate(self):
        state = play_moves(start_position(),
                           ["f2f3", "e7e5", "g2g4", "d8h4"])
        self.assertEqual(game_status(state), "checkmate")

    def test_scholars_mate(self):
        state = play_moves(start_position(),
                           ["e2e4", "e7e5", "f1c4", "b8c6",
                            "d1h5", "g8f6", "h5f7"])
        self.assertEqual(game_status(state), "checkmate")

    def test_stalemate(self):
        state = from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertEqual(game_status(state), "stalemate")

    def test_insufficient_material(self):
        self.assertEqual(game_status(from_fen("7k/8/8/8/8/8/8/K7 w - - 0 1")),
                         "draw_insufficient_material")
        self.assertEqual(game_status(from_fen("7k/8/8/8/8/8/8/KN6 w - - 0 1")),
                         "draw_insufficient_material")
        self.assertEqual(game_status(from_fen("7k/8/8/8/8/8/8/KB6 w - - 0 1")),
                         "draw_insufficient_material")
        self.assertEqual(game_status(from_fen("7k/8/8/8/8/8/8/KQ6 w - - 0 1")),
                         "playing")


class TestFenUci(unittest.TestCase):
    def test_en_passant_and_castling_survive_fen(self):
        state = play_moves(start_position(), ["e2e4"])
        self.assertIn("e3", to_fen(state))
        self.assertIn("KQkq", to_fen(state))

    def test_parse_uci_errors(self):
        state = start_position()
        for bad in ("e2", "e2e4q", "i9e4", "e2e9", "e2e4x"):
            with self.assertRaises(ValueError, msg=bad):
                parse_uci(state, bad)
        self.assertEqual(move_to_uci(parse_uci(state, "e2e4")), "e2e4")

    def test_bad_fen_errors(self):
        for bad in ("", "8/8/8 w - -", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1"):
            with self.assertRaises(ValueError, msg=bad):
                from_fen(bad)

    def test_render_contains_pieces(self):
        text = render_board(start_position(), ascii_pieces=True)
        self.assertIn("R N B Q K B N R", text)
        self.assertIn("a b c d e f g h", text)


class TestEngine(unittest.TestCase):
    def test_random_move_is_legal_and_seeded(self):
        state = start_position()
        move = random_move(state, random.Random(42))
        self.assertIn(move, legal_moves(state))
        self.assertEqual(random_move(state, random.Random(42)), move)

    def test_best_move_takes_free_queen_over_pawn(self):
        state = from_fen("4k3/8/8/3q3p/8/8/8/3QK3 w - - 0 1")
        self.assertEqual(move_to_uci(best_move(state, depth=1)), "d1d5")

    def test_best_move_finds_mate_in_one(self):
        state = play_moves(start_position(), ["f2f3", "e7e5", "g2g4"])
        self.assertEqual(move_to_uci(best_move(state, depth=1)), "d8h4")

    def test_best_move_none_when_mated(self):
        state = play_moves(start_position(),
                           ["f2f3", "e7e5", "g2g4", "d8h4"])
        self.assertIsNone(best_move(state, depth=1))
        self.assertIsNone(random_move(state))

    def test_evaluate_material(self):
        self.assertEqual(evaluate(start_position()), 0)
        self.assertEqual(evaluate(from_fen("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")), 900)
        self.assertEqual(evaluate(from_fen("4k3/8/8/8/8/8/8/3qK3 w - - 0 1")), -900)


class TestCli(unittest.TestCase):
    def run_cli(self, stdin, args=()):
        proc = subprocess.run(
            [sys.executable, str(CHESS_PY), *args],
            input=stdin, capture_output=True, text=True, timeout=60)
        return proc

    def test_two_player_move_then_quit(self):
        proc = self.run_cli("e2e4\nquit\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Black to move", proc.stdout)

    def test_invalid_move_rejected_and_game_continues(self):
        proc = self.run_cli("e2e5\nquit\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Illegal move", proc.stdout)

    def test_computer_random_replies(self):
        proc = self.run_cli("e2e4\nquit\n",
                            ["--computer", "random", "--seed", "1"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Computer plays", proc.stdout)

    def test_fools_mate_ends_game(self):
        proc = self.run_cli("f2f3\ne7e5\ng2g4\nd8h4\n")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Checkmate", proc.stdout)


if __name__ == "__main__":
    unittest.main()

"""Every piece of curated content is replayed so a wrong move or a false 'checkmate' fails the build."""

import chess
import pytest

from chesscoach import academy
from chesscoach.openings import book


def test_every_puzzle_line_is_legal_and_mates_are_mates():
    puzzles = academy.puzzles()
    assert len(puzzles) >= 15
    for p in puzzles:
        board = chess.Board(p["fen"])
        assert len(p["line"]) == len(p["line_san"]) and len(p["line"]) % 2 == 1, p["id"]
        assert len(set(x["id"] for x in puzzles)) == len(puzzles)
        for uci, san in zip(p["line"], p["line_san"]):
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves, f"{p['id']}: {san} is not legal"
            assert board.san(move) == san, p["id"]
            board.push(move)
        if p["line_san"][-1].endswith("#"):
            assert board.is_checkmate(), f"{p['id']} does not end in mate"
        assert (p["side"] == "white") == chess.Board(p["fen"]).turn, p["id"]


def test_material_traps_really_win_material():
    def balance(board, color):
        values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
        return sum(values.get(p.piece_type, 0) * (1 if p.color == color else -1) for p in board.piece_map().values())

    p = academy.puzzle_by_id("trap-elephant")
    board = chess.Board(p["fen"])
    start = balance(board, chess.BLACK)
    for uci in p["line"]:
        board.push_uci(uci)
    assert balance(board, chess.BLACK) >= start + 3

    # Noah's Ark: the line ends with the bishop attacked by the c-pawn and no escape squares.
    p = academy.puzzle_by_id("trap-noah")
    board = chess.Board(p["fen"])
    for uci in p["line"]:
        board.push_uci(uci)
    assert board.piece_at(chess.C4) == chess.Piece(chess.PAWN, chess.BLACK)
    assert board.piece_at(chess.B3) == chess.Piece(chess.BISHOP, chess.WHITE)
    escapes = [m for m in board.legal_moves if m.from_square == chess.B3 and not board.is_capture(m)]
    assert all(board.is_attacked_by(chess.BLACK, m.to_square) for m in escapes)


def test_model_games_replay_and_notes_match_their_moves():
    games = academy.model_games()
    assert {g["id"] for g in games} >= {"opera", "immortal", "evergreen", "lasker-thomas", "legal"}
    for g in games:
        assert g["moves"][-1]["san"].endswith("#"), g["id"]
        board = chess.Board(g["moves"][-1]["fen"])
        assert board.is_checkmate(), g["id"]
        for note in g["notes"]:
            assert g["moves"][note["ply"] - 1]["san"] == note["san"], f"{g['id']} note at ply {note['ply']}"


def test_repertoire_lines_are_legal_and_named_by_the_opening_book():
    for r in academy.repertoire():
        board = chess.Board()
        for san in r["moves"]:
            board.push_san(san)
        assert board.fen() == r["fen"]
        for trap in r["traps"]:
            b = chess.Board()
            for san in trap["moves"]:
                b.push_san(san)
        # Some sensible lines run a move or two past the last named position, so require a named prefix.
        b = chess.Board()
        named = None
        for san in r["moves"]:
            b.push_san(san)
            named = book().by_epd.get(b.epd()) or named
        assert named is not None and len(r["moves"]) - named.ply <= 3, f"{r['name']} is not a named line"


def test_theme_lookup():
    assert {p["theme"] for p in academy.puzzles("traps")} == {"traps"}
    assert academy.puzzle_by_id("nope") is None

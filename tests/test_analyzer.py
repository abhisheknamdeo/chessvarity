import io

import chess
import chess.pgn
import pytest

from chesscoach.analyzer import _allowed_threat, analyze_game, pick_color


def game_from(moves: str, black="Ayaan", white="Opponent") -> chess.pgn.Game:
    pgn = f'[White "{white}"]\n[Black "{black}"]\n\n{moves}\n'
    return chess.pgn.read_game(io.StringIO(pgn))


def test_pick_color_by_name_or_explicit_color():
    game = game_from("1. e4 e5")
    assert pick_color(game, "ayaan", None) == chess.BLACK
    assert pick_color(game, None, "white") == chess.WHITE
    with pytest.raises(ValueError):
        pick_color(game, "Nobody", None)


def test_scholars_mate_reports_missed_mate_threat(engine):
    game = game_from("1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0")
    result = analyze_game(game, engine, chess.BLACK)
    moment = next(m for m in result["moments"] if m["category"] == "missed_threat")
    assert moment["played"]["san"] == "Nf6"
    assert moment["threat"]["kind"] == "mate"
    assert moment["threat"]["san"] == "Qxf7#"
    assert moment["opponent_last"]["san"] == "Qh5"
    # Real defences are offered, not the move that was played.
    good = [c["san"] for c in moment["candidates"] if c["good"]]
    assert good and "Nf6" not in good
    assert moment["skill"] == "threat_recognition"
    assert result["skills"]["threat_recognition"]["score"] == 0


def test_hanging_the_queen_is_a_blunder_check_moment(engine):
    game = game_from("1. e4 e5 2. Nf3 Nc6 3. Bc4 Qg5 4. Nxg5 1-0")
    result = analyze_game(game, engine, chess.BLACK)
    moment = next(m for m in result["moments"] if m["category"] == "hung_piece")
    assert moment["played"]["san"] == "Qg5"
    assert moment["allowed"]["san"] == "Nxg5"
    assert moment["allowed"]["kind"] == "capture"
    assert moment["puzzle"]["good_moves"]


def test_recapture_after_an_even_trade_is_not_a_hung_piece(engine):
    board = chess.Board("4k3/4n3/8/5b2/8/8/2B5/4K3 w - - 0 1")
    move = chess.Move.from_uci("c2f5")  # Bxf5, and Nxf5 recaptures
    after = board.copy()
    after.push(move)
    nxt = engine.analyse(after)
    assert _allowed_threat(after, nxt, chess.WHITE, 20.0, move, gained=3) is None
    # Without the piece we just took, the same recapture would be a real loss.
    assert _allowed_threat(after, nxt, chess.WHITE, 20.0, move, gained=0).san == "Nxf5"


def test_result_is_inferred_for_a_bare_move_list(engine):
    game = chess.pgn.read_game(io.StringIO("1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"))
    result = analyze_game(game, engine, chess.BLACK)
    assert result["game"]["result"] == "1-0"
    assert result["game"]["white"] == "White" and result["game"]["player"] == "Black"


def test_a_sound_game_produces_no_problem_moments(engine):
    game = game_from("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6")
    result = analyze_game(game, engine, chess.BLACK)
    assert result["moments"] == []
    assert result["accuracy"] > 85

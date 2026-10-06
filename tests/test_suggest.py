"""Move suggestions: the reasons come from board facts, so they can be checked without an engine."""

import chess

from chesscoach import suggest
from chesscoach.engine import MATE_CP, Line

SCHOLAR = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"


def line(board, san, cp, *more, mate=None):
    """A fake engine line (cp from White's view) starting with `san`."""
    b = board.copy()
    pv = []
    for s in (san, *more):
        pv.append(b.push_san(s))
    return Line(pv[0], cp, mate, pv)


def test_a_move_that_stops_a_mate_threat_and_hits_the_queen_says_so():
    board = chess.Board(SCHOLAR)                                           # Black to move, Qxf7# is threatened
    out = suggest.build(board, [line(board, "g6", 20, "Qd1"), line(board, "Qe7", 40, "Qd1"), line(board, "a6", 900, "Qxf7")], 3)
    best, mid, bad = out["moves"]
    assert (best["san"], best["quality"], best["label"]) == ("g6", "best", "Best move")
    text = " ".join(best["reasons"])
    assert "stops your opponent's threat of checkmate with Qxf7#" in text
    assert "attacks the queen on h5" in text
    assert best["line"] == "3... g6 4. Qd1"
    assert best["reply"]["san"] == "Qd1" and best["reply"]["text"].startswith("White would most likely answer Qd1")
    assert mid["quality"] in ("equal", "good") and "stops your opponent's threat of checkmate" in " ".join(mid["reasons"])
    assert (bad["san"], bad["quality"]) == ("a6", "bad") and "blunder" in bad["label"]
    assert any("does not deal with the threat of checkmate with Qxf7#" in w for w in bad["warnings"])
    ctx = out["context"]
    assert ctx["side"] == "Black" and not ctx["in_check"] and ctx["threats"] == ["White threatens checkmate with Qxf7#."]


def test_checkmate_and_forced_mate_are_named():
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    move = line(board, "Ra8#", MATE_CP, mate=1)
    out = suggest.build(board, [move], 1)["moves"][0]
    assert out["reasons"][0] == "It is checkmate." and out["score"] == "mate in 1"
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    slower = Line(chess.Move.from_uci("a1a7"), MATE_CP, 3, [chess.Move.from_uci("a1a7")])
    assert any("forces checkmate in 3 moves" in r for r in suggest.build(board, [slower], 1)["moves"][0]["reasons"])


def test_winning_a_loose_piece_is_explained_with_the_material_won():
    board = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    top = suggest.build(board, [line(board, "Nxd5", 900)], 1)["moves"][0]
    assert any("It wins material" in r and "queen on d5" in r for r in top["reasons"])
    assert top["headline"].startswith("You capture the queen on d5")


def test_getting_out_of_check_and_running_into_mate_are_flagged():
    board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")               # White is in check by the rook on e2
    out = suggest.build(board, [line(board, "Kxe2", 0)], 1)
    assert out["context"]["in_check"] is True
    assert any("out of check by capturing the checking piece" in r for r in out["moves"][0]["reasons"])
    lost = Line(chess.Move.from_uci("e1d1"), -MATE_CP, -2, [chess.Move.from_uci("e1d1")])
    board = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    out = suggest.build(board, [line(board, "Kd2", 0), lost], 2)["moves"]
    assert out[1]["quality"] == "bad" and "forced mate" in out[1]["label"] and "forced checkmate in 2" in out[1]["warnings"][0]


def test_a_quiet_move_still_gets_a_concrete_reason():
    board = chess.Board(chess.STARTING_FEN)
    got = suggest.build(board, [line(board, "e4", 30, "c5"), line(board, "Nf3", 28, "d5")], 2)["moves"]
    assert any("share of the centre" in r for r in got[0]["reasons"]) and got[0]["reasons"]
    assert any("develops the knight" in r and "1 of 4" in r for r in got[1]["reasons"])
    assert all(m["reasons"] and m["headline"] for m in got)


def test_scores_words_and_lines():
    white, black = chess.WHITE, chess.BLACK
    assert suggest.score_text(Line(chess.Move.null(), 40, None, []), white) == "+0.4"
    assert suggest.score_text(Line(chess.Move.null(), 40, None, []), black) == "-0.4"
    assert suggest.score_text(Line(chess.Move.null(), MATE_CP, 3, []), white) == "mate in 3"
    assert suggest.score_text(Line(chess.Move.null(), MATE_CP, 3, []), black) == "mated in 3"
    assert [suggest.eval_words(x) for x in (95, 80, 65, 56, 50, 44, 30, 15, 5)] == [
        "winning", "clearly better", "better", "slightly better", "equal", "slightly worse", "worse", "clearly worse", "losing"]
    assert [suggest.quality(g, 0, False)[0] for g in (0, 4, 10, 20, 40)] == ["best", "good", "ok", "weak", "bad"]
    assert suggest.quality(0.5, 1, False)[0] == "equal"
    board = chess.Board()
    e4, c5 = chess.Move.from_uci("e2e4"), chess.Move.from_uci("c7c5")
    assert suggest.pv_text(board, [e4, c5]) == "1. e4 c5"
    board.push(e4)
    assert suggest.pv_text(board, [c5]) == "1... c5"


def test_the_api_returns_reasons_lines_and_a_read_on_the_position(tmp_path, engine):
    from fastapi.testclient import TestClient
    from chesscoach.api import create_app
    from chesscoach.config import Settings

    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as client:
        client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "A"})
        out = client.post("/api/play/suggest", json={"fen": SCHOLAR, "n": 3}).json()
        assert len(out["moves"]) == 3 and out["context"]["threats"] and out["context"]["side"] == "Black"
        for i, m in enumerate(out["moves"]):
            assert m["rank"] == i + 1 and m["reasons"] and m["headline"] and m["line"] and m["label"] and m["score"]
            assert m["quality"] in ("best", "equal", "good", "ok", "weak", "bad")
        assert out["moves"][0]["quality"] == "best" and out["moves"][0]["gap"] == 0
        assert any("checkmate" in r for r in out["moves"][0]["reasons"])                # the mate threat is dealt with
        hint = client.post("/api/play/hint", json={"fen": SCHOLAR}).json()
        assert hint["reasons"] and hint["context"]["threats"] and hint["san"] == hint["san"].strip()

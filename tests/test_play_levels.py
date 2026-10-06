"""The computer opponent: book moves, legal replies at every level, sensible choices when it matters."""

import chess
import pytest

from chesscoach import play
from chesscoach.engine import DEFAULT_ENGINE


@pytest.fixture(scope="module")
def engine():
    if not DEFAULT_ENGINE.exists():
        pytest.skip("Stockfish binary not available")
    e = play.PlayEngine()
    yield e
    e.close()


def test_levels_run_from_weak_to_strong():
    elos = [lv["elo"] for lv in play.LEVELS]
    assert elos == sorted(elos) and play.LEVELS[4]["elo"] == 1700
    temps = [lv["temp"] for lv in play.LEVELS]
    assert temps == sorted(temps, reverse=True) and temps[-1] == 0


def test_opening_book_has_real_first_moves():
    first = play.opening_book()[chess.Board().epd()]
    assert {"e2e4", "d2d4", "c2c4", "g1f3"} <= set(first)


def test_every_level_plays_a_legal_move_and_uses_the_book_early(engine):
    start = chess.Board()
    for level in play.LEVELS:
        move = engine.reply(start, level["id"])
        assert move in start.legal_moves
        assert move.uci() in play.opening_book()[start.epd()]  # the first move always comes from real openings


def test_forced_move_and_mate_in_one(engine):
    only = chess.Board("7k/8/8/8/8/8/6q1/7K w - - 0 1")  # king takes the queen: the only legal move
    assert engine.reply(only, 3).uci() == "h1g2"
    mate = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")  # Rd8 is mate
    for level in (3, 5, 6, 8):
        assert engine.reply(mate, level).uci() == "d1d8"


def test_the_default_level_is_1700(tmp_path):
    from chesscoach.routes_play import Position
    assert Position(fen=chess.STARTING_FEN).level == 5

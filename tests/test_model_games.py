"""The rated model-games library is generated data, so every game is replayed and checked."""

import json
from collections import Counter

import chess
import pytest

from chesscoach import academy

DATA = academy.LICHESS_GAMES
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="run tools/build_model_games.py to build the library")

BAND_LIMITS = {"under-1200": (0, 1200), "1200-1499": (1200, 1500), "1500-1799": (1500, 1800),
               "1800-1999": (1800, 2000), "2000-2299": (2000, 2300), "2300-plus": (2300, 9999)}
ALLOWED_KEYS = {"id", "band", "avg", "white_rating", "black_rating", "result", "month", "opening_eco", "opening_name",
                "book_plies", "moves", "score", "summary", "lessons", "themes", "commentary"}


@pytest.fixture(scope="module")
def games():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_there_are_hundreds_of_games_in_every_rating_band(games):
    rated = [g for g in games if not g["id"].startswith("classic-")]
    assert len(rated) >= 300
    counts = Counter(g["band"] for g in rated)
    assert set(counts) == set(BAND_LIMITS)
    assert all(n >= 40 for n in counts.values()), counts
    assert len({g["id"] for g in games}) == len(games)


def test_every_game_replays_legally_and_ends_in_checkmate(games):
    for g in games:
        board = chess.Board()
        for san in g["moves"]:
            board.push_san(san)
        assert board.is_checkmate(), g["id"]
        assert g["result"] == ("1-0" if board.turn == chess.BLACK else "0-1"), g["id"]


def test_every_move_has_commentary_in_order(games):
    for g in games:
        assert [c["ply"] for c in g["commentary"]] == list(range(1, len(g["moves"]) + 1)), g["id"]
        assert all(len(c["text"]) > 20 for c in g["commentary"]), g["id"]
        assert "Checkmate" in g["commentary"][-1]["text"], g["id"]
        assert g["summary"] and g["themes"], g["id"]


def test_bands_match_ratings_and_no_player_names_are_kept(games):
    for g in games:
        if g["id"].startswith("classic-"):
            continue
        lo, hi = BAND_LIMITS[g["band"]]
        assert lo <= g["avg"] <= hi, g["id"]   # the shown rating is rounded, so a 1499.5 average may read 1500
        assert abs(g["white_rating"] - g["black_rating"]) <= 250
        assert set(g) <= ALLOWED_KEYS, set(g) - ALLOWED_KEYS
    text = DATA.read_text(encoding="utf-8")
    assert "http" not in text and "@" not in text


def test_the_library_api_data_shapes():
    index = academy.model_index()
    assert len(index) >= 300
    bands = {b["key"]: b["count"] for b in academy.model_bands()}
    assert bands["historic"] == 5 and bands["2300-plus"] >= 40
    rated = next(g for g in index if g["band"] == "1500-1799")
    detail = academy.model_detail(rated["id"])
    assert detail["moves"][-1]["san"].endswith("#") and detail["commentary"] and detail["moves"][0]["fen"]
    classic = academy.model_detail("opera")
    assert classic["commentary"] and classic["notes"] and classic["band"] == "historic"

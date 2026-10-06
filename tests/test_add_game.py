"""The Add a game page: reading a PGN before saving it, matching tournaments, and the new add options."""

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

PGN = """[Event "Bradley Open 2026"]
[Site "Bradley, IL"]
[Date "2026.09.27"]
[Round "3"]
[White "Namdeo, Ayaan"]
[Black "Smith, John"]
[WhiteElo "1435"]
[BlackElo "1521"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 1-0
"""
TWO = PGN + """
[Event "Club night"]
[White "Lee, David"]
[Black "Namdeo, Ayaan"]
[Result "0-1"]

1. d4 d5 2. c4 e6 0-1
"""


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: None)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Ayaan Namdeo"})
        yield c


def test_a_pgn_is_read_without_saving_and_the_player_is_found(client):
    r = client.post("/api/games/preview", json={"pgn": PGN}).json()
    assert r["ok"] and len(r["games"]) == 1
    g = r["games"][0]
    assert (g["white"], g["black"], g["white_elo"], g["black_elo"]) == ("Namdeo, Ayaan", "Smith, John", "1435", "1521")
    assert (g["result"], g["date"], g["event"], g["round"], g["site"], g["moves"]) == ("1-0", "2026-09-27", "Bradley Open 2026", "3", "Bradley, IL", 5)
    assert g["side"] == "white" and g["opening_name"] and not g["duplicate"] and g["match"] is None
    pid = client.get("/api/auth/me").json()["player"]["id"]
    assert client.get(f"/api/players/{pid}/library").json() == []          # nothing was saved


def test_unreadable_games_get_a_friendly_message(client):
    bad = client.post("/api/games/preview", json={"pgn": "1. e4 e5 2. Ke3 Ke6 3. Qxz9"}).json()
    assert bad == {"ok": False, "error": "We couldn't read this game.", "hint": bad["hint"]}
    assert "move" in bad["hint"] and "illegal" not in bad["hint"].lower()
    assert client.post("/api/games/preview", json={"pgn": "hello"}).json()["ok"] is False


def test_several_games_and_a_matching_tournament_round(client):
    ev = client.post("/api/events", json={"name": "Bradley Open", "start_date": "2026-09-26", "kind": "past", "rounds": 4}).json()
    r = client.post("/api/games/preview", json={"pgn": TWO}).json()
    first, second = r["games"]
    assert (first["side"], second["side"]) == ("white", "black")
    assert first["match"]["event_id"] == ev["id"] and first["match"]["round"] == "3"
    assert first["match"]["round_id"] == ev["rounds"][2]["id"]
    assert second["match"] is None                                          # "Club night" is not one of my tournaments


def test_add_with_an_exact_date_without_analysis_and_only_chosen_games(client):
    res = client.post("/api/games", json={"pgn": TWO, "include": [1], "analyze": False, "date": "2026-08-14",
                                          "prefer_pgn_date": False}).json()
    assert len(res["games"]) == 1
    g = res["games"][0]
    assert (g["white"], g["color"], g["status"], g["date"]) == ("Lee, David", "black", "saved", "2026.08.14")
    again = client.post("/api/games/preview", json={"pgn": TWO}).json()["games"]
    assert (again[0]["duplicate"], again[1]["duplicate"]) == (False, True)
    assert client.post("/api/games", json={"pgn": TWO, "include": []}).status_code == 400
    assert client.post("/api/games", json={"pgn": PGN, "date": "27/09/2026"}).status_code == 400


def test_a_side_can_be_chosen_per_game(client):
    bare = "1. e4 e5 2. Nf3 Nc6\n\n1. d4 d5 2. c4 c6"
    assert client.post("/api/games", json={"pgn": bare}).status_code == 400            # nobody's name: which side?
    res = client.post("/api/games", json={"pgn": bare, "sides": ["black", "white"]}).json()
    assert [g["color"] for g in res["games"]] == ["black", "white"]
    assert all(g["status"] == "queued" for g in res["games"])                         # analysis starts by default


def test_static_files_are_revalidated_so_updates_show_up(client):
    r = client.get("/static/js/app.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache" and r.headers.get("etag")
    again = client.get("/static/js/app.js", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304                                    # unchanged: nothing re-downloaded

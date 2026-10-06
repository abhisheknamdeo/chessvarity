"""Model-game review progress and the opponent's rating field."""

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

WIN = """[Event "Weekend Open"]
[Date "2026.09.08"]
[White "Ayaan"]
[Black "Rival"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d4 exd4 6. cxd4 Bb4+ 7. Nc3 1-0
"""


@pytest.fixture()
def client(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Ayaan"})
        yield c


def first_game(client):
    return client.get("/api/library/model-games", params={"limit": 1}).json()["games"][0]


def test_reviewing_a_model_game_move_by_move_marks_it_in_progress_then_completed(client):
    game = first_game(client)
    gid, total = game["id"], game["plies"]
    assert game["review"] == {"seen": 0, "percent": 0, "status": "new", "total": total}

    part = client.post(f"/api/library/model-games/{gid}/review", json={"plies": [1, 2, 3, 3]}).json()
    assert (part["seen"], part["status"]) == (3, "in_progress") and part["percent"] == round(300 / total)
    again = client.post(f"/api/library/model-games/{gid}/review", json={"plies": [3, 4]}).json()
    assert again["seen"] == 4 and again["plies"] == [1, 2, 3, 4]                      # moves are only ever added
    assert client.get(f"/api/library/model-games/{gid}/review").json()["plies"] == [1, 2, 3, 4]

    listed = next(g for g in client.get("/api/library/model-games", params={"limit": 100}).json()["games"] if g["id"] == gid)
    assert listed["review"]["status"] == "in_progress"
    assert [g["id"] for g in client.get("/api/library/model-games", params={"status": "in_progress"}).json()["games"]] == [gid]
    assert client.get("/api/library/model-games", params={"status": "completed"}).json()["games"] == []
    assert client.get("/api/library/model-games", params={"status": "new", "limit": 100}).json()["total"] == \
        client.get("/api/library/model-games").json()["total"] - 1

    # Nonsense move numbers count for nothing; only stepping through every move completes a game.
    client.post(f"/api/library/model-games/{gid}/review", json={"plies": [0, -5, total + 1, 99999]})
    assert client.get(f"/api/library/model-games/{gid}/review").json()["status"] == "in_progress"
    done = client.post(f"/api/library/model-games/{gid}/review", json={"plies": list(range(1, total + 1))}).json()
    assert (done["status"], done["percent"], done["seen"]) == ("completed", 100, total)
    summary = client.get("/api/library/model-games").json()["summary"]
    assert summary == {"completed": 1, "in_progress": 0}

    reset = client.delete(f"/api/library/model-games/{gid}/review").json()
    assert reset["status"] == "new" and reset["seen"] == 0


def test_review_progress_is_per_student_and_unknown_games_are_refused(client):
    gid = first_game(client)["id"]
    client.post(f"/api/library/model-games/{gid}/review", json={"plies": [1]})
    assert client.post("/api/library/model-games/no-such-game/review", json={"plies": [1]}).status_code == 404
    assert client.get("/api/library/model-games/no-such-game/review").status_code == 404
    assert client.delete("/api/library/model-games/no-such-game/review").status_code == 404
    assert client.post(f"/api/library/model-games/{gid}/review", json={"plies": list(range(500))}).status_code == 422
    client.post("/api/auth/logout")
    assert client.get(f"/api/library/model-games/{gid}/review").status_code == 401
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "B"})
    assert client.get(f"/api/library/model-games/{gid}/review").json()["status"] == "new"


def test_the_opponents_rating_is_saved_shown_and_editable(client):
    res = client.post("/api/games", json={"pgn": WIN, "opponent_rating": 1350})
    assert res.status_code == 200, res.text
    game = res.json()["games"][0]
    assert (game["color"], game["black_elo"], game["white_elo"]) == ("white", "1350", "")        # the rival was Black
    assert client.post("/api/games", json={"pgn": "1. e4 e5", "color": "white", "opponent_rating": 4000}).status_code == 422
    assert client.app.state.worker.wait_idle(120)

    edited = client.patch(f"/api/games/{game['id']}", json={"opponent_rating": 1420}).json()
    assert edited["black_elo"] == "1420"
    assert client.patch(f"/api/games/{game['id']}", json={"opponent_rating": 0}).json()["black_elo"] == ""     # 0 clears it
    assert client.patch(f"/api/games/{game['id']}", json={"opponent": "Rival Two"}).json()["black_elo"] == ""   # untouched otherwise


def test_a_rating_already_in_the_pgn_is_kept_unless_one_is_typed(client):
    def game(moves):
        return ('[White "Ayaan"]\n[Black "Rival"]\n[Date "2026.09.08"]\n[BlackElo "1500"]\n[Result "1-0"]\n\n' + moves + " 1-0\n")

    kept = client.post("/api/games", json={"pgn": game("1. d4 d5 2. c4 e6 3. Nc3 Nf6")})
    assert kept.json()["games"][0]["black_elo"] == "1500"
    typed = client.post("/api/games", json={"pgn": game("1. e4 c5 2. Nf3 d6 3. d4 cxd4"), "opponent_rating": 1600})
    assert typed.json()["games"][0]["black_elo"] == "1600"

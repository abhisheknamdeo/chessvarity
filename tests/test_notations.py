"""Scoresheets saved before the moves are entered, and their photos moving to the game once it's added."""

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 500


@pytest.fixture()
def app(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: None)
    with TestClient(app):
        yield app


def user(app, email):
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": email, "password": "correct horse", "display_name": "Ayaan"}).status_code == 200
    return c


def test_save_a_scoresheet_now_and_add_the_moves_later(app):
    c = user(app, "a@example.com")
    n = c.post("/api/notations", json={"title": "Round 3 vs John", "played_on": "2026-10-03"}).json()
    up = c.post(f"/api/notations/{n['id']}/scoresheets", content=JPEG, headers={"Content-Type": "image/jpeg"})
    assert up.status_code == 200 and len(up.json()["sheets"]) == 1
    listed = c.get("/api/notations").json()
    assert [(x["title"], x["played_on"], len(x["sheets"])) for x in listed] == [("Round 3 vs John", "2026-10-03", 1)]
    sheet = listed[0]["sheets"][0]["id"]
    assert c.get(f"/api/scoresheets/{sheet}").status_code == 200

    game = c.post("/api/games", json={"pgn": "1. e4 e5 2. Nf3 Nc6", "color": "white", "notation_id": n["id"]}).json()["games"][0]
    assert [s["id"] for s in c.get(f"/api/games/{game['id']}/scoresheets").json()["sheets"]] == [sheet]   # the photo moved
    assert c.get("/api/notations").json() == []                                                           # nothing left waiting


def test_saved_scoresheets_are_private_and_can_be_thrown_away(app):
    a, b = user(app, "a@example.com"), user(app, "b@example.com")
    n = a.post("/api/notations", json={"title": "Club night"}).json()
    a.post(f"/api/notations/{n['id']}/scoresheets", content=JPEG, headers={"Content-Type": "image/jpeg"})
    assert b.get("/api/notations").json() == []
    assert b.post(f"/api/notations/{n['id']}/scoresheets", content=JPEG, headers={"Content-Type": "image/jpeg"}).status_code == 404
    assert b.delete(f"/api/notations/{n['id']}").status_code == 404
    assert a.patch(f"/api/notations/{n['id']}", json={"title": "Club night, game 2"}).json()["title"] == "Club night, game 2"
    assert a.post(f"/api/notations/{n['id']}/scoresheets", content=b"not a photo").status_code == 400
    assert a.delete(f"/api/notations/{n['id']}").json() == {"ok": True}
    assert a.get("/api/notations").json() == []

"""The calendar's details (tournament statuses, games, goal steps) and the tournament preparation checklist."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: None)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Ayaan"})
        yield c


def soon(days):
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def test_calendar_items_carry_what_the_details_panel_shows(client):
    pid = client.get("/api/auth/me").json()["player"]["id"]
    ev = client.post("/api/events", json={"name": "NJ Open", "start_date": soon(6), "end_date": soon(7), "kind": "upcoming", "rounds": 5,
                                          "reg_deadline": soon(3), "reg_status": "done", "hotel_status": "todo"}).json()
    client.post("/api/goals", json={"title": "Solve 50 puzzles", "due_date": soon(10), "steps": ["Week 1", "Week 2"]})
    items = client.get(f"/api/players/{pid}/calendar", params={"start": soon(0), "end": soon(30)}).json()["items"]
    t = next(i for i in items if i["type"] == "tournament")
    assert (t["rounds"], t["games_with_moves"], t["statuses"]["reg_status"], t["statuses"]["hotel_status"]) == (5, 0, "done", "todo")
    assert t["prep"]["percent"] == 0 and [s["key"] for s in t["prep"]["steps"]] == ["review", "tactics", "endgame", "openings", "practice"]
    assert next(s for s in t["prep"]["steps"] if s["key"] == "openings")["href"] == f"#/prep?event={ev['id']}"
    d = next(i for i in items if i["type"] == "deadline")
    assert (d["event_name"], d["event_start"], d["done"]) == ("NJ Open", soon(6), True)
    g = next(i for i in items if i["type"] == "goal")
    assert (g["steps"], g["steps_done"]) == (2, 0)


def test_preparation_steps_can_be_ticked(client):
    pid = client.get("/api/auth/me").json()["player"]["id"]
    ev = client.post("/api/events", json={"name": "NJ Open", "start_date": soon(6), "kind": "upcoming"}).json()
    r = client.patch(f"/api/events/{ev['id']}/prep", json={"step": "openings", "done": True}).json()
    assert r["percent"] == 20 and next(s for s in r["steps"] if s["key"] == "openings")["done"]
    client.patch(f"/api/events/{ev['id']}/prep", json={"step": "endgame", "done": True})
    client.patch(f"/api/events/{ev['id']}/prep", json={"step": "openings", "done": False})
    t = next(i for i in client.get(f"/api/players/{pid}/calendar").json()["items"] if i["type"] == "tournament")
    assert t["prep"]["percent"] == 20 and [s["key"] for s in t["prep"]["steps"] if s["done"]] == ["endgame"]
    assert client.patch(f"/api/events/{ev['id']}/prep", json={"step": "nope", "done": True}).status_code == 422
    # Tactics ticks itself once a puzzle has been solved this week.
    client.post(f"/api/players/{pid}/puzzles/mate-1/solved")
    t = next(i for i in client.get(f"/api/players/{pid}/calendar").json()["items"] if i["type"] == "tournament")
    assert next(s for s in t["prep"]["steps"] if s["key"] == "tactics")["done"]

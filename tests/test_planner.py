"""The tournament planner (registration, hotel, travel flags) and the calendar feed."""

import datetime as dt
import sqlite3

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings
from chesscoach.db import EVENT_COLUMNS, Database


@pytest.fixture()
def client(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Duke"})
        c.pid = c.get("/api/auth/me").json()["player"]["id"]
        yield c


def test_a_new_tournament_starts_with_everything_still_to_do(client):
    made = client.post("/api/events", json={
        "name": "Nationals", "start_date": "2026-12-04", "end_date": "2026-12-06", "kind": "upcoming", "location": "Orlando, FL",
        "address": "Hilton, 6001 Destination Pkwy", "website": "https://example.org/nationals", "entry_fee": "$120",
        "reg_deadline": "2026-11-15", "hotel_name": "Hilton Orlando", "hotel_checkin": "2026-12-03", "hotel_checkout": "2026-12-07"}).json()
    plan = made["plan"]
    assert (plan["address"], plan["website"], plan["entry_fee"]) == ("Hilton, 6001 Destination Pkwy", "https://example.org/nationals", "$120")
    assert (plan["reg_deadline"], plan["hotel_checkin"], plan["hotel_checkout"]) == ("2026.11.15", "2026.12.03", "2026.12.07")
    assert (plan["attending"], plan["reg_status"], plan["hotel_status"]) == ("maybe", "todo", "todo")
    assert made["needs"] == ["registration", "payment", "hotel", "travel"]


def test_flags_are_updated_one_at_a_time_and_the_to_do_list_shrinks(client):
    event = client.post("/api/events", json={"name": "State Open", "start_date": "2026-11-14", "kind": "upcoming"}).json()
    url = f"/api/events/{event['id']}/plan"
    done = client.patch(url, json={"reg_status": "done", "paid_status": "done", "reg_confirmation": "REG-4471"}).json()
    assert done["needs"] == ["hotel", "travel"] and done["plan"]["reg_confirmation"] == "REG-4471"
    local = client.patch(url, json={"hotel_status": "na", "travel_status": "na"}).json()          # a local event: no hotel, no travel
    assert local["needs"] == [] and local["plan"]["reg_status"] == "done"                         # earlier changes are kept
    again = client.patch(url, json={"hotel_status": "todo", "hotel_name": "Motel 6", "attending": "going"}).json()
    assert again["needs"] == ["hotel"] and again["plan"]["hotel_name"] == "Motel 6" and again["plan"]["attending"] == "going"
    skipped = client.patch(url, json={"attending": "skip"}).json()
    assert skipped["needs"] == []                                                                  # not going: nothing to do
    assert client.patch(url, json={}).json()["plan"]["attending"] == "skip"                        # an empty update changes nothing
    # The ordinary edit keeps the planning details when it does not mention them.
    edited = client.patch(f"/api/events/{event['id']}", json={"name": "State Open 2026", "start_date": "2026-11-14", "kind": "upcoming"}).json()
    assert edited["name"] == "State Open 2026" and edited["plan"]["hotel_name"] == "Motel 6" and edited["plan"]["reg_status"] == "done"


def test_planner_input_is_checked(client):
    event = client.post("/api/events", json={"name": "Open", "kind": "upcoming"}).json()
    url = f"/api/events/{event['id']}/plan"
    assert client.patch(url, json={"website": "javascript:alert(1)"}).status_code == 400            # only real links are stored
    assert client.patch(url, json={"website": "ftp://example.org"}).status_code == 400
    assert client.patch(url, json={"website": "HTTPS://Example.org/x"}).status_code == 200
    assert client.patch(url, json={"reg_deadline": "next week"}).status_code == 400
    assert client.patch(url, json={"reg_status": "maybe"}).status_code == 422
    assert client.patch(url, json={"attending": "definitely"}).status_code == 422
    assert client.patch(url, json={"hotel_name": "x" * 101}).status_code == 422
    assert client.post("/api/events", json={"name": "Bad", "website": "example.org"}).status_code == 400


def test_the_calendar_lists_tournaments_deadlines_hotels_and_goals(client):
    client.post("/api/events", json={"name": "Nationals", "start_date": "2026-12-04", "end_date": "2026-12-06", "kind": "upcoming",
                                     "reg_deadline": "2026-11-15", "hotel_name": "Hilton", "hotel_checkin": "2026-12-03", "hotel_checkout": "2026-12-07"})
    client.post("/api/events", json={"name": "Fall Open", "start_date": "2026-09-05", "kind": "past"})
    client.post("/api/events", json={"name": "Someday Open", "kind": "upcoming"})                     # no date yet
    client.post("/api/events", json={"name": "Skipped", "start_date": "2026-12-20", "kind": "upcoming", "attending": "skip", "reg_deadline": "2026-12-01"})
    client.post("/api/goals", json={"title": "Fewer blunders", "due_date": "2026-11-01"})
    client.post("/api/goals", json={"title": "No date"})
    cal = client.get(f"/api/players/{client.pid}/calendar").json()
    got = [(i["type"], i["title"], i["start"], i["end"]) for i in cal["items"]]
    assert ("tournament", "Fall Open", "2026-09-05", "2026-09-05") in got                          # a one-day event ends the day it starts
    assert ("tournament", "Nationals", "2026-12-04", "2026-12-06") in got
    assert ("deadline", "Register by: Nationals", "2026-11-15", "2026-11-15") in got
    assert ("hotel", "Hotel: Hilton", "2026-12-03", "2026-12-07") in got
    assert ("goal", "Goal: Fewer blunders", "2026-11-01", "2026-11-01") in got
    assert not any(t == "deadline" and "Skipped" in title for t, title, *_ in got)                 # no deadline for an event being skipped
    assert not any("No date" in title for _, title, *_ in got) and cal["undated"] == 1
    assert [i["start"] for i in cal["items"]] == sorted(i["start"] for i in cal["items"])
    assert cal["today"] == dt.date.today().isoformat()
    nationals = next(i for i in cal["items"] if i["type"] == "tournament" and i["title"] == "Nationals")
    assert nationals["needs"] == ["registration", "payment", "hotel", "travel"] and nationals["kind"] == "upcoming"
    hotel_na = client.get(f"/api/players/{client.pid}/events").json()
    eid = next(e["id"] for e in hotel_na if e["name"] == "Nationals")
    client.patch(f"/api/events/{eid}/plan", json={"hotel_status": "na"})
    assert not any(i["type"] == "hotel" for i in client.get(f"/api/players/{client.pid}/calendar").json()["items"])     # no hotel needed


def test_planner_data_is_private(client):
    event = client.post("/api/events", json={"name": "Mine", "start_date": "2026-11-14", "kind": "upcoming"}).json()
    mine = client.pid
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "B"})
    assert client.patch(f"/api/events/{event['id']}/plan", json={"reg_status": "done"}).status_code == 404
    assert client.get(f"/api/players/{mine}/calendar").status_code == 404
    client.post("/api/auth/logout")
    assert client.get(f"/api/players/{mine}/calendar").status_code == 401


def test_a_database_from_before_the_planner_gets_the_new_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, player_id INTEGER NOT NULL, name TEXT NOT NULL,
            start_date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'past', source TEXT NOT NULL DEFAULT 'manual', uscf_event_id TEXT NOT NULL DEFAULT '',
            section TEXT NOT NULL DEFAULT '', rating_system TEXT NOT NULL DEFAULT '', rating_before INTEGER, rating_after INTEGER,
            time_control TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
        INSERT INTO events(id, user_id, player_id, name, start_date, kind, created_at) VALUES (7, 1, 1, 'Old Open', '2026.05.02', 'upcoming', 1.0);
    """)
    old.commit()
    old.close()
    db = Database(path)
    have = {r["name"] for r in db.all("PRAGMA table_info(events)")}
    assert set(EVENT_COLUMNS) <= have
    row = db.one("SELECT * FROM events WHERE id = 7")
    assert (row["name"], row["reg_status"], row["attending"], row["hotel_name"]) == ("Old Open", "todo", "maybe", "")   # data kept, defaults filled
    Database(path)                                                                                                      # opening it again is harmless

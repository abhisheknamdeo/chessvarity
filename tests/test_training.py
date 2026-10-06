"""The training schedule: repeating sessions, cancelling and attending them, and their place on the calendar."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from chesscoach import training
from chesscoach.api import create_app
from chesscoach.config import Settings


@pytest.fixture()
def client(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Duke"})
        c.pid = c.get("/api/auth/me").json()["player"]["id"]
        yield c


def row(**over):
    base = {"id": 1, "title": "Tactics class", "kind": "class", "start_date": "2026-10-06", "start_time": "16:30", "end_time": "17:30",
            "location": "Club", "coach": "Coach Lee", "topic": "Tactics", "notes": "", "recurrence": "none", "weekdays": "", "until": "",
            "skips": "[]", "done": "[]"}
    return {**base, **over}


D = dt.date


def test_a_one_off_session_appears_only_on_its_day():
    r = row()
    assert training.dates_between(r, D(2026, 10, 1), D(2026, 10, 31)) == [D(2026, 10, 6)]
    assert training.dates_between(r, D(2026, 10, 7), D(2026, 10, 31)) == []
    assert training.dates_between(r, D(2026, 9, 1), D(2026, 10, 5)) == []


def test_weekly_sessions_on_one_or_several_weekdays():
    r = row(recurrence="weekly")                                               # 2026-10-06 is a Tuesday
    assert training.dates_between(r, D(2026, 10, 1), D(2026, 10, 27)) == [D(2026, 10, 6), D(2026, 10, 13), D(2026, 10, 20), D(2026, 10, 27)]
    twice = row(recurrence="weekly", weekdays="1,3")                           # Tuesdays and Thursdays
    got = training.dates_between(twice, D(2026, 10, 1), D(2026, 10, 15))
    assert got == [D(2026, 10, 6), D(2026, 10, 8), D(2026, 10, 13), D(2026, 10, 15)]      # nothing before the first date
    assert training.dates_between(twice, D(2027, 3, 1), D(2027, 3, 7)) == [D(2027, 3, 2), D(2027, 3, 4)]   # far in the future too


def test_every_other_week_and_monthly_and_an_end_date():
    every_other = row(recurrence="biweekly")
    assert training.dates_between(every_other, D(2026, 10, 1), D(2026, 11, 10)) == [D(2026, 10, 6), D(2026, 10, 20), D(2026, 11, 3)]
    monthly = row(recurrence="monthly", start_date="2026-01-31")
    got = training.dates_between(monthly, D(2026, 1, 1), D(2026, 4, 30))
    assert got == [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31), D(2026, 4, 30)]            # short months use their last day
    ends = row(recurrence="weekly", until="2026-10-13")
    assert training.dates_between(ends, D(2026, 10, 1), D(2027, 1, 1)) == [D(2026, 10, 6), D(2026, 10, 13)]
    assert training.dates_between(ends, D(2026, 10, 14), D(2027, 1, 1)) == []


def test_patterns_are_described_in_words():
    assert training.pattern_text(row()) == "Tue Oct 6, 16:30-17:30"
    assert training.pattern_text(row(recurrence="weekly", weekdays="1,3")) == "Every Tue and Thu, 16:30-17:30"
    assert training.pattern_text(row(recurrence="biweekly", until="2026-12-15")) == "Every other Tue, 16:30-17:30, until Dec 15"
    assert training.pattern_text(row(recurrence="monthly", start_date="2026-10-02", start_time="", end_time="")) == "Monthly on the 2nd, all day"
    assert training.minutes(row()) == 60 and training.minutes(row(start_time="", end_time="")) == 0


def make(client, **over):
    body = {"title": "Tactics class", "kind": "class", "start_date": "2026-10-06", "start_time": "16:30", "end_time": "17:30",
            "location": "Chess Club, Main St", "coach": "Coach Lee", "topic": "Tactics", "recurrence": "weekly", "weekdays": [1, 3],
            "until": "2026-11-30", **over}
    res = client.post("/api/training", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def test_creating_listing_editing_and_deleting_a_series(client):
    made = make(client)
    assert made["pattern"] == "Every Tue and Thu, 16:30-17:30, until Nov 30" and made["kind_label"] == "Class" and made["weekdays"] == [1, 3]
    listed = client.get(f"/api/players/{client.pid}/training").json()
    assert [s["title"] for s in listed["series"]] == ["Tactics class"] and "lesson" in listed["kinds"]
    edited = client.patch(f"/api/training/{made['id']}", json={**{k: made[k] for k in ("title", "kind", "start_date", "start_time", "end_time", "location", "coach", "topic", "notes", "recurrence", "until")},
                                                                "weekdays": [2], "title": "Endgame class"}).json()
    assert edited["title"] == "Endgame class" and edited["weekdays"] == [2]
    assert client.delete(f"/api/training/{made['id']}").status_code == 200
    assert client.get(f"/api/players/{client.pid}/training").json()["series"] == []


def test_input_is_checked(client):
    bad = lambda **o: client.post("/api/training", json={"title": "x", "start_date": "2026-10-06", **o}).status_code
    assert bad() == 200
    assert bad(start_date="tomorrow") == 400 and bad(start_date="2026-13-40") == 400
    assert bad(start_time="4pm") == 400 and bad(start_time="25:00") == 400
    assert bad(end_time="17:00") == 400                                            # an end without a start
    assert bad(start_time="17:00", end_time="16:00") == 400                        # ends before it starts
    assert bad(recurrence="weekly", until="2026-10-01") == 400 and bad(recurrence="weekly", until="soon") == 400
    assert bad(weekdays=[7]) == 400 and bad(kind="party") == 422 and bad(recurrence="daily") == 422
    assert client.post("/api/training", json={"title": "", "start_date": "2026-10-06"}).status_code == 422


def test_occurrences_in_a_range_with_cancelled_and_attended_sessions(client):
    made = make(client)
    url = f"/api/players/{client.pid}/training/occurrences"
    out = client.get(url, params={"start": "2026-10-05", "end": "2026-10-18"}).json()
    assert [(o["date"], o["start_time"]) for o in out["items"]] == [("2026-10-06", "16:30"), ("2026-10-08", "16:30"), ("2026-10-13", "16:30"), ("2026-10-15", "16:30")]
    assert out["summary"] == {"sessions": 4, "attended": 0, "minutes": 240}

    mark = lambda date, action: client.post(f"/api/training/{made['id']}/occurrence", json={"date": date, "action": action})
    assert mark("2026-10-06", "done").json()["done"] == ["2026-10-06"]
    assert mark("2026-10-08", "skip").json()["skips"] == ["2026-10-08"]
    assert mark("2026-10-08", "done").status_code == 400                             # a cancelled session cannot be attended
    out = client.get(url, params={"start": "2026-10-05", "end": "2026-10-18"}).json()
    flags = {o["date"]: (o["done"], o["skipped"]) for o in out["items"]}
    assert flags["2026-10-06"] == (True, False) and flags["2026-10-08"] == (False, True)
    assert out["summary"] == {"sessions": 3, "attended": 1, "minutes": 180}         # cancelled sessions are not counted
    assert mark("2026-10-08", "unskip").json()["skips"] == [] and mark("2026-10-06", "undone").json()["done"] == []
    assert mark("2026-10-07", "skip").status_code == 400 and mark("nonsense", "skip").status_code == 400          # not a meeting day
    assert mark("2026-10-06", "skip").json()["skips"] == ["2026-10-06"]
    assert client.get(url, params={"start": "2026-10-05", "end": "2027-12-31"}).status_code == 400              # too long a range
    assert client.get(url, params={"start": "x", "end": "y"}).status_code == 400


def test_the_next_session_is_reported(client):
    today = dt.date.today()
    made = make(client, start_date=(today - dt.timedelta(days=30)).isoformat(), weekdays=[today.weekday()], until="")
    assert made["next"] == today.isoformat()
    client.post(f"/api/training/{made['id']}/occurrence", json={"date": today.isoformat(), "action": "skip"})
    after = client.get(f"/api/players/{client.pid}/training").json()["series"][0]
    assert after["next"] == (today + dt.timedelta(days=7)).isoformat()             # a cancelled session is not "next"


def test_training_shows_on_the_calendar_with_its_details(client):
    make(client, recurrence="weekly", weekdays=[1], until="2026-10-27")
    cal = client.get(f"/api/players/{client.pid}/calendar", params={"start": "2026-10-01", "end": "2026-10-31"}).json()
    sessions = [i for i in cal["items"] if i["type"] == "training"]
    assert [i["start"] for i in sessions] == ["2026-10-06", "2026-10-13", "2026-10-20", "2026-10-27"]
    first = sessions[0]
    assert (first["title"], first["time"], first["end_time"], first["location"], first["coach"], first["kind"]) == \
        ("Tactics class", "16:30", "17:30", "Chess Club, Main St", "Coach Lee", "class")
    assert first["done"] is False and first["skipped"] is False and first["recurrence"] == "weekly"
    assert not [i for i in client.get(f"/api/players/{client.pid}/calendar", params={"start": "2026-11-01", "end": "2026-11-30"}).json()["items"] if i["type"] == "training"]
    assert client.get(f"/api/players/{client.pid}/calendar", params={"start": "2026-01-01", "end": "2027-12-31"}).status_code == 400
    assert client.get(f"/api/players/{client.pid}/calendar").status_code == 200                # the default window works too


def test_training_is_private(client):
    made = make(client)
    mine = client.pid
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "B"})
    assert client.patch(f"/api/training/{made['id']}", json={"title": "Hacked", "start_date": "2026-10-06"}).status_code == 404
    assert client.delete(f"/api/training/{made['id']}").status_code == 404
    assert client.post(f"/api/training/{made['id']}/occurrence", json={"date": "2026-10-06", "action": "done"}).status_code == 404
    assert client.get(f"/api/players/{mine}/training").status_code == 404
    assert client.get(f"/api/players/{mine}/training/occurrences", params={"start": "2026-10-01", "end": "2026-10-31"}).status_code == 404

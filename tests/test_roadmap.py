"""The Chess Development Roadmap: levels, priorities from games, topic progress."""

import pytest
from fastapi.testclient import TestClient

from chesscoach import roadmap
from chesscoach.api import create_app
from chesscoach.config import Settings


def test_rating_to_level_and_milestones():
    assert [roadmap.BANDS[roadmap.band_for(r)]["label"] for r in (0, 499, 500, 1278, 1400, 1999, 2600)] == \
        ["Under 500", "Under 500", "500–799", "1200–1399", "1400–1599", "1800–1999", "2000+"]
    d = roadmap.build(1278, "USCF", None, {"ready": False}, {}, 0)
    assert d["band"] == 4 and d["is_current"] and (d["next_milestone"], d["future_milestone"]) == (1400, 1600)
    assert len(d["categories"]) == 8 and len(d["priorities"]) == 3 and len(d["weekly_plan"]) == 7
    assert not d["personal"]  # no games: priorities come from what matters at this level


def test_every_level_has_topics_and_nothing_is_lost_between_levels():
    for band in range(len(roadmap.BANDS)):
        d = roadmap.build(None, "USCF", band, {"ready": False}, {}, 0)
        assert any(c["now"] for c in d["categories"]), band
    keys = [t["key"] for t in roadmap.TOPICS]
    assert len(keys) == len(set(keys))


def test_future_level_is_marked_and_progress_is_kept():
    statuses = {"t_fork": "mastered", "t_pin": "learning"}
    here = roadmap.build(1278, "USCF", None, {"ready": False}, statuses, 0)
    later = roadmap.build(1278, "USCF", 7, {"ready": False}, statuses, 0)
    assert later["is_future"] and not later["is_current"]
    tactics = next(c for c in later["categories"] if c["key"] == "tactics")
    assert {t["key"]: t["status"] for t in tactics["review"]}["t_fork"] == "mastered"
    assert next(c for c in here["categories"] if c["key"] == "tactics")["completed"] >= 1


def test_priorities_follow_the_games():
    habits = {"ready": True, "habits": [
        {"id": "tactics", "score": 90, "detail": "You found 9 of the 10 tactical chances.", "headline": "", "evidence": []},
        {"id": "threats", "score": 30, "detail": "You dealt with 3 of the 10 real threats.", "headline": "", "evidence": [{"game_id": 1, "ply": 10}]},
        {"id": "endgame", "score": 40, "detail": "You lose accuracy in endgames.", "headline": "", "evidence": []},
    ]}
    d = roadmap.build(1278, "USCF", None, habits, {}, 10)
    assert d["personal"] and d["priorities"][0]["category"] == "thinking" and d["priorities"][0]["priority"] == "High"
    assert "3 of the 10 real threats" in d["priorities"][0]["why"]
    assert "tactics" not in [p["category"] for p in d["priorities"][:2]]  # strong area, not a top priority
    assert d["weekly_plan"][0]["plan"].endswith("thinking process focus")


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mail_backend="memory"), engine_factory=lambda: None)
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "kid@example.com", "password": "long password", "display_name": "Duke"})
        yield c


def test_roadmap_api_and_topic_progress(client):
    me = client.get("/api/auth/me").json()
    pid = me["player"]["id"]
    d = client.get(f"/api/players/{pid}/roadmap").json()
    assert d["rating"] is None and d["current_band"] is None and d["band"] == 2  # no rating yet
    client.patch("/api/auth/me", json={"display_name": "Duke", "email": "kid@example.com", "rating": 1278, "rating_system": "USCF"})
    assert client.get(f"/api/players/{pid}/roadmap").json()["band"] == 4
    assert client.get(f"/api/players/{pid}/roadmap?band=6").json()["is_future"] is True
    assert client.put(f"/api/players/{pid}/roadmap/topics/t_fork", json={"status": "mastered"}).json() == {"topic": "t_fork", "status": "mastered"}
    client.put(f"/api/players/{pid}/roadmap/topics/t_pin", json={"status": "learning"})
    client.put(f"/api/players/{pid}/roadmap/topics/t_pin", json={"status": "practicing"})
    tactics = next(c for c in client.get(f"/api/players/{pid}/roadmap").json()["categories"] if c["key"] == "tactics")
    status = {t["key"]: t["status"] for t in tactics["review"]}
    assert status["t_fork"] == "mastered" and status["t_pin"] == "practicing" and tactics["progress"] > 0
    assert client.put(f"/api/players/{pid}/roadmap/topics/nope", json={"status": "learning"}).status_code == 404
    assert client.put(f"/api/players/{pid}/roadmap/topics/t_fork", json={"status": "done"}).status_code == 422
    other = TestClient(client.app)
    other.post("/api/auth/register", json={"email": "x@example.com", "password": "long password", "display_name": "X"})
    assert other.get(f"/api/players/{pid}/roadmap").status_code == 404


def test_topics_link_to_where_they_are_practised():
    d = roadmap.build(1300, "USCF", None, {}, {"t_fork": "mastered"}, 0)
    by = {c["key"]: c for c in d["categories"]}
    assert by["attack"]["practice"]["href"] == "#/academy/attack"
    assert by["repertoire"]["practice"]["href"].startswith("#/openings")
    assert by["endgame"]["practice"] is None
    topics = {t["key"]: t for c in d["categories"] for k in ("review", "now", "preview") for t in c[k]}
    assert topics["t_mate1"]["practice"]["href"] == "#/academy/mates"  # a topic can point somewhere more specific
    assert topics["t_fork"]["practice"]["href"] == "#/academy/tactics" and topics["t_fork"]["status"] == "mastered"
    valid = {"#/academy/tactics", "#/academy/attack", "#/academy/mates", "#/academy/traps", "#/openings/library",
             "#/openings/repertoire", "#/models", "#/think"}
    assert all(t["practice"] is None or t["practice"]["href"] in valid for t in topics.values())

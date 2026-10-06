"""Tournaments, rounds, and the USCF import. USCF itself is replaced by a fake, so no test uses the network."""

import json
import re
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from chesscoach import uscf
from chesscoach.api import create_app
from chesscoach.config import Settings

MEMBER = {"id": "12345678", "firstName": "DUKE", "lastName": "TESTER", "status": "Active", "expirationDate": "2027-01-01",
          "ratings": [{"rating": 1440, "ratingSystem": "R"}, {"ratingSystem": "Q"}, {"rating": 1310, "ratingSystem": "B"}]}
SECTIONS = [{"id": "s1", "sectionNumber": 1, "sectionName": "Under 1600", "ratingRecords": [{"preRating": 1400, "postRating": 1440}],
             "event": {"id": "E1", "name": "State Open", "startDate": "2026-09-05", "endDate": "2026-09-06", "stateCode": "CA"}}]


def game(opp_id, first, last, color, outcome, event="E1", section=1):
    return {"section": {"id": "s1", "number": section, "name": "Under 1600"},
            "event": {"id": event, "name": "State Open", "startDate": "2026-09-05", "endDate": "2026-09-06", "stateCode": "CA"},
            "ratingSystem": "R", "player": {"color": color, "outcome": outcome},
            "opponent": {"id": opp_id, "firstName": first, "lastName": last, "color": "Black" if color == "White" else "White"}}


class FakeUscf:
    """Answers the three USCF calls the app makes, with two pages of games."""

    def __init__(self):
        self.games = [game("111", "ANNA", "LEE", "White", "Win"), game("222", "BEN", "OKAFOR", "Black", "Loss"),
                      game("333", "CARA", "SMITH", "White", "Draw")]
        self.member_exists = True
        self.down = False
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if self.down:
            raise uscf.UscfError("Could not reach the USCF ratings service. Check your internet connection and try again.")
        path = urllib.parse.urlsplit(url).path
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if not self.member_exists:
            return 404, "{}"
        if re.fullmatch(r"/api/v1/members/\d{8}", path):
            return 200, json.dumps(MEMBER)
        if path.endswith("/sections"):
            return 200, json.dumps({"items": SECTIONS, "hasNextPage": False})
        if path.endswith("/games"):
            offset = int(query.get("Offset", ["0"])[0])
            page = self.games[offset // 100 * 2: offset // 100 * 2 + 2]      # two games per "page" to exercise paging
            return 200, json.dumps({"items": page, "hasNextPage": offset // 100 * 2 + 2 < len(self.games)})
        return 404, "{}"


@pytest.fixture()
def env(tmp_path, engine):
    fake = FakeUscf()
    factory = lambda: uscf.UscfClient(fetch=fake, sleep=lambda s: None, gap=0)
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False, uscf_factory=factory)
    with TestClient(app) as client:
        client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Duke"})
        yield client, fake


def pid(client):
    return client.get("/api/auth/me").json()["player"]["id"]


def test_the_uscf_id_can_be_looked_up_saved_and_cleared(env):
    client, fake = env
    assert client.get("/api/uscf/lookup", params={"id": "123"}).status_code == 400
    found = client.get("/api/uscf/lookup", params={"id": "12345678"}).json()
    assert found["name"] == "Duke Tester" and found["ratings"] == {"regular": 1440, "blitz": 1310}
    fake.member_exists = False
    missing = client.get("/api/uscf/lookup", params={"id": "12345678"})
    assert missing.status_code == 400 and "no member" in missing.json()["detail"]

    assert client.put("/api/uscf/id", json={"uscf_id": "1234"}).status_code == 400
    saved = client.put("/api/uscf/id", json={"uscf_id": "1234 5678"}).json()
    assert saved["uscf_id"] == "12345678"
    assert client.get("/api/auth/me").json()["player"]["uscf_id"] == "12345678"      # remembered
    assert client.put("/api/uscf/id", json={"uscf_id": ""}).json()["uscf_id"] == ""
    assert client.post("/api/uscf/sync").status_code == 400                            # nothing saved to sync


def test_importing_from_uscf_creates_tournaments_and_rounds_and_can_be_repeated(env):
    client, fake = env
    client.put("/api/uscf/id", json={"uscf_id": "12345678"})
    first = client.post("/api/uscf/sync").json()
    assert (first["events_added"], first["games_added"], first["games_seen"]) == (1, 3, 3)      # both pages were read
    assert first["status"]["name"] == "Duke Tester" and first["status"]["ratings"]["regular"] == 1440

    events = client.get(f"/api/players/{pid(client)}/events").json()
    assert len(events) == 1
    e = events[0]
    assert (e["name"], e["start_date"], e["location"], e["source"]) == ("State Open", "2026.09.05", "CA", "uscf")
    assert (e["rating_before"], e["rating_after"], e["rating_system"]) == (1400, 1440, "R")
    assert (e["wins"], e["draws"], e["losses"]) == (1, 1, 1)
    rounds = e["rounds"]
    assert [(r["opponent"], r["color"], r["result"]) for r in rounds] == [
        ("Anna Lee", "white", "win"), ("Ben Okafor", "black", "loss"), ("Cara Smith", "white", "draw")]
    assert all(r["game_id"] is None for r in rounds)          # USCF has results, not moves

    again = client.post("/api/uscf/sync").json()
    assert (again["events_added"], again["games_added"], again["games_updated"]) == (0, 0, 0)     # nothing duplicated
    fake.games[1] = game("222", "BEN", "OKAFOR", "Black", "Win")                                  # a corrected result
    assert client.post("/api/uscf/sync").json()["games_updated"] == 1
    assert client.get(f"/api/players/{pid(client)}/events").json()[0]["rounds"][1]["result"] == "win"
    # It only ever reads: the app makes no non-GET requests and sends no ID other than the saved one.
    assert all("12345678" in c or "/members/" in c for c in fake.calls)


def test_uscf_problems_are_explained_not_crashes(env):
    client, fake = env
    client.put("/api/uscf/id", json={"uscf_id": "12345678"})
    fake.down = True
    res = client.post("/api/uscf/sync")
    assert res.status_code == 502 and "internet connection" in res.json()["detail"]


def test_adding_a_game_to_a_round_links_it_and_fills_in_what_is_known(env):
    client, _ = env
    client.put("/api/uscf/id", json={"uscf_id": "12345678"})
    client.post("/api/uscf/sync")
    round_id = client.get(f"/api/players/{pid(client)}/events").json()[0]["rounds"][0]["id"]
    res = client.post("/api/games", json={"pgn": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5", "event_game_id": round_id})
    assert res.status_code == 200, res.text
    added = res.json()["games"][0]
    assert (added["event"], added["round"], added["opponent"], added["color"]) == ("State Open", "1", "Anna Lee", "white")
    assert added["result"] == "1-0" and added["date"] == "2026.09.??"        # a win as White, filed under the event's month
    assert client.app.state.worker.wait_idle(120)
    row = client.get(f"/api/players/{pid(client)}/events").json()[0]["rounds"][0]
    assert row["game_id"] == added["id"] and row["game"]["status"] == "done"
    assert client.post("/api/games", json={"pgn": "1. e4 e5", "color": "white", "event_game_id": 99999}).status_code == 404


def test_tournaments_and_rounds_can_be_entered_by_hand(env):
    client, _ = env
    made = client.post("/api/events", json={"name": "Club Championship", "start_date": "2026-11-14", "kind": "upcoming",
                                            "time_control": "G/60", "rounds": 4}).json()
    assert made["kind"] == "upcoming" and made["start_date"] == "2026.11.14" and len(made["rounds"]) == 4
    assert client.post("/api/events", json={"name": "Bad", "start_date": "tomorrow"}).status_code == 400

    fixed = client.patch(f"/api/rounds/{made['rounds'][0]['id']}", json={"opponent": "Sam", "color": "black", "result": "win"}).json()
    assert fixed["rounds"][0]["opponent"] == "Sam" and fixed["wins"] == 1
    extra = client.post(f"/api/events/{made['id']}/rounds", json={"opponent": "Kim"}).json()
    assert len(extra["rounds"]) == 5 and extra["rounds"][-1]["round"] == "5"
    client.delete(f"/api/rounds/{extra['rounds'][-1]['id']}")
    edited = client.patch(f"/api/events/{made['id']}", json={"name": "Club Champs", "kind": "past", "start_date": "2026-11-14"}).json()
    assert edited["name"] == "Club Champs" and edited["kind"] == "past" and len(edited["rounds"]) == 4

    # Deleting the tournament removes its round records but never a game with moves.
    gid = client.post("/api/games", json={"pgn": "1. e4 e5 2. Nf3 Nc6", "color": "white", "event_game_id": edited["rounds"][1]["id"]}).json()["games"][0]["id"]
    assert client.delete(f"/api/events/{made['id']}").status_code == 200
    assert client.get(f"/api/players/{pid(client)}/events").json() == []
    assert client.get(f"/api/games/{gid}").status_code == 200


def test_an_existing_game_can_be_linked_and_unlinked(env):
    client, _ = env
    event = client.post("/api/events", json={"name": "Open", "rounds": 2}).json()
    gid = client.post("/api/games", json={"pgn": "1. d4 d5 2. c4 e6", "color": "white"}).json()["games"][0]["id"]
    linked = client.post(f"/api/rounds/{event['rounds'][1]['id']}/link/{gid}").json()
    assert linked["rounds"][1]["game_id"] == gid and linked["games_with_moves"] == 1
    moved = client.post(f"/api/rounds/{event['rounds'][0]['id']}/link/{gid}").json()       # a game belongs to one round
    assert moved["rounds"][0]["game_id"] == gid and moved["rounds"][1]["game_id"] is None
    assert client.post(f"/api/rounds/{event['rounds'][0]['id']}/unlink").json()["rounds"][0]["game_id"] is None


def test_tournaments_are_private_to_their_owner(env):
    client, _ = env
    event = client.post("/api/events", json={"name": "Mine", "rounds": 1}).json()
    p = pid(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "Other"})
    assert client.get(f"/api/players/{p}/events").status_code == 404
    assert client.patch(f"/api/events/{event['id']}", json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/events/{event['id']}").status_code == 404
    assert client.patch(f"/api/rounds/{event['rounds'][0]['id']}", json={"opponent": "x"}).status_code == 404
    assert client.get("/api/uscf/lookup", params={"id": "12345678"}).status_code == 200      # signed in is enough to look up
    assert client.get("/api/uscf").json()["uscf_id"] == ""                                     # ...but not to see someone else's ID


def test_saving_the_uscf_id_brings_in_the_rating_for_the_roadmap(env):
    client, fake = env
    saved = client.put("/api/uscf/id", json={"uscf_id": "12345678"}).json()
    assert saved["name"] == "Duke Tester" and saved["player_rating"] == 1440 and saved["player_rating_system"] == "USCF"
    player = client.get("/api/auth/me").json()["player"]
    assert (player["rating"], player["rating_system"]) == (1440, "USCF")
    road = client.get(f"/api/players/{player['id']}/roadmap").json()
    assert road["rating"] == 1440 and road["bands"][road["current_band"]]["label"] == "1400–1599"


def test_a_saved_id_without_a_rating_is_filled_in_later_and_other_systems_are_kept(env):
    client, fake = env
    fake.down = True
    client.put("/api/uscf/id", json={"uscf_id": "12345678"})          # USCF unreachable: the ID is still saved
    assert client.get("/api/auth/me").json()["player"]["rating"] is None
    fake.down = False
    player = client.get("/api/auth/me").json()["player"]
    road = client.get(f"/api/players/{player['id']}/roadmap").json()   # the roadmap fetches the missing rating
    assert road["rating"] == 1440

    client.patch("/api/auth/me", json={"display_name": "Duke", "email": "a@example.com", "rating": 1900, "rating_system": "FIDE"})
    client.post("/api/uscf/sync")                                       # a chosen FIDE rating is not replaced
    assert client.get("/api/auth/me").json()["player"]["rating"] == 1900


def test_every_rating_an_event_changed_is_kept(env):
    client, fake = env
    SECTIONS[0]["ratingRecords"] = [{"preRating": 1278, "postRating": 1240, "ratingSource": "Q"},
                                    {"preRating": 1443, "postRating": 1405, "ratingSource": "R"}]
    try:
        client.put("/api/uscf/id", json={"uscf_id": "12345678"})
        client.post("/api/uscf/sync")
        e = client.get(f"/api/players/{pid(client)}/events").json()[0]
        assert e["ratings"] == [{"system": "R", "before": 1443, "after": 1405, "change": -38},
                                {"system": "Q", "before": 1278, "after": 1240, "change": -38}]     # regular first
        assert (e["rating_before"], e["rating_after"]) == (1443, 1405)
    finally:
        SECTIONS[0]["ratingRecords"] = [{"preRating": 1400, "postRating": 1440}]

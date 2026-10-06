"""The results table, goal sheet, tournament preparation and the thinking coach."""

import datetime as dt

import chess
import pytest
from fastapi.testclient import TestClient

from chesscoach import academy, prep, thinking
from chesscoach.api import create_app
from chesscoach.config import Settings

LOST_AS_BLACK = """[Event "Club Championship"]
[Round "2"]
[Date "2026.09.01"]
[White "Opponent"]
[Black "Ayaan"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
"""
WON_AS_WHITE = """[Event "Weekend Open"]
[Round "1"]
[Date "2026.09.08"]
[White "Ayaan"]
[Black "Rival"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d4 exd4 6. cxd4 Bb4+ 7. Nc3 1-0
"""
AUGUST_DRAW = """[Event "Summer Blitz"]
[Round "3"]
[Date "2026.08.15"]
[White "Ayaan"]
[Black "Kim"]
[Result "1/2-1/2"]

1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O 6. Nf3 Nbd7 1/2-1/2
"""


@pytest.fixture()
def client(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        me = c.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "display_name": "Ayaan"}).json()
        c.pid = c.get("/api/auth/me").json()["player"]["id"]
        yield c


def add(client, pgn, **extra):
    res = client.post("/api/games", json={"pgn": pgn, **extra})
    assert res.status_code == 200, res.text
    assert client.app.state.worker.wait_idle(120)
    return res.json()["games"][0]["id"]


def row(table, label):
    return next(r for r in table["months"] if r["label"] == label)


# -- the results table --------------------------------------------------------------------------


def test_the_results_table_counts_each_game_once_by_month_and_year(client):
    add(client, LOST_AS_BLACK)
    won = add(client, WON_AS_WHITE)
    add(client, AUGUST_DRAW)
    # A tournament in October whose rounds have results but no moves (like a USCF import).
    october = client.post("/api/events", json={"name": "Fall Open", "start_date": "2026-10-10", "rounds": 3}).json()
    for r, (color, result) in zip(october["rounds"], [("white", "win"), ("black", "draw"), ("white", "")]):
        client.patch(f"/api/rounds/{r['id']}", json={"color": color, "result": result})
    client.app.state.db.run("UPDATE events SET rating_before = 1400, rating_after = 1432, rating_system = 'R' WHERE id = ?", (october["id"],))
    # Attaching a game with moves to a round must not count it twice.
    september = client.post("/api/events", json={"name": "Weekend Open", "start_date": "2026-09-08", "rounds": 1}).json()
    client.post(f"/api/rounds/{september['rounds'][0]['id']}/link/{won}")

    table = client.get(f"/api/players/{client.pid}/stats").json()
    sep, aug, octo = row(table, "Sep 2026"), row(table, "Aug 2026"), row(table, "Oct 2026")
    assert (sep["games"], sep["wins"], sep["draws"], sep["losses"], sep["score"]) == (2, 1, 0, 1, 50)
    assert (sep["white"]["games"], sep["white"]["score"], sep["black"]["games"], sep["black"]["score"]) == (1, 100, 1, 0)
    assert sep["analysed"] == 2 and sep["accuracy"] is not None and sep["blunders_per_game"] is not None
    assert (aug["games"], aug["draws"], aug["score"]) == (1, 1, 50)
    assert (octo["games"], octo["wins"], octo["draws"], octo["score"]) == (2, 1, 1, 75)          # the round with no result yet is not counted
    assert octo["analysed"] == 0 and octo["accuracy"] is None                      # results only, nothing to analyse
    assert (octo["rating_start"], octo["rating_end"], octo["rating_change"]) == (1400, 1432, 32)
    assert [r["label"] for r in table["months"]] == ["Oct 2026", "Sep 2026", "Aug 2026"]      # newest first
    year = table["years"][0]
    assert (year["label"], year["games"], year["wins"], year["draws"], year["losses"]) == ("2026", 5, 2, 2, 1)
    assert table["total"]["games"] == 5 and table["total"]["events"] == 2

    csv = client.get(f"/api/players/{client.pid}/stats.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("Period,Games,Won,Drawn,Lost") and lines[1].startswith("Oct 2026,2,1,1,0,75")
    assert len(lines) == 1 + 3 + 1 + 1                                              # months, the year, the total


def test_practice_games_are_kept_out_of_the_real_record(client):
    add(client, WON_AS_WHITE.replace("Weekend Open", "Practice vs computer"))
    table = client.get(f"/api/players/{client.pid}/stats").json()
    assert table["total"]["games"] == 0 and table["months"] == []
    assert table["practice"]["games"] == 1 and table["practice"]["wins"] == 1


def test_an_empty_account_has_an_empty_table(client):
    table = client.get(f"/api/players/{client.pid}/stats").json()
    assert table["months"] == [] and table["years"] == [] and table["total"]["score"] is None


def test_the_results_table_is_private(client):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "B"})
    assert client.get(f"/api/players/{client.pid}/stats").status_code == 404
    assert client.get(f"/api/players/{client.pid}/stats.csv").status_code == 404
    assert client.get(f"/api/players/{client.pid}/goals").status_code == 404
    assert client.get(f"/api/players/{client.pid}/prep").status_code == 404


# -- goals --------------------------------------------------------------------------------------


def test_goals_track_a_measure_and_a_checklist(client):
    add(client, LOST_AS_BLACK)
    sheet = client.get(f"/api/players/{client.pid}/goals").json()
    assert sheet["goals"] == [] and sheet["suggested"]
    assert {"accuracy", "blunders", "habit_attack", "rating", "streak"} <= {m["id"] for m in sheet["metrics"]}
    assert all(s["horizon"] in ("short", "long") for s in sheet["suggested"])

    made = client.post("/api/goals", json={"horizon": "short", "title": "Play with fewer blunders", "metric": "accuracy",
                                          "target": 95, "due_date": "2026-12-01", "steps": ["Check threats", "  ", "Blunder check"]}).json()
    goal = made["goals"][0]
    assert goal["baseline"] is not None and goal["target"] == 95 and goal["due_date"] == "2026.12.01"
    assert goal["current"] == goal["baseline"] and goal["percent"] == 0 and goal["reached"] is False
    assert [s["text"] for s in goal["steps"]] == ["Check threats", "Blunder check"]

    manual = client.post("/api/goals", json={"horizon": "long", "title": "Learn the Italian"}).json()["goals"][1]
    assert manual["metric"] == "" and manual["percent"] is None and manual["horizon"] == "long"

    step = goal["steps"][0]["id"]
    after = client.patch(f"/api/steps/{step}", json={"done": True}).json()["goals"][0]
    assert after["steps_done"] == 1
    added = client.post(f"/api/goals/{goal['id']}/steps", json={"text": "Play a slow game"}).json()["goals"][0]
    assert len(added["steps"]) == 3
    client.delete(f"/api/steps/{step}")

    done = client.patch(f"/api/goals/{goal['id']}", json={"status": "done"}).json()["goals"][0]
    assert done["status"] == "done" and len(done["steps"]) == 2
    assert client.patch(f"/api/goals/{goal['id']}", json={"status": "bogus"}).status_code == 422
    assert client.delete(f"/api/goals/{manual['id']}").json()["goals"][0]["id"] == goal["id"]


def test_goal_input_is_checked(client):
    assert client.post("/api/goals", json={"title": "x", "metric": "made-up", "target": 5}).status_code == 400
    assert client.post("/api/goals", json={"title": "x", "metric": "accuracy"}).status_code == 400          # a measure needs a target
    assert client.post("/api/goals", json={"title": "", "horizon": "short"}).status_code == 422
    assert client.post("/api/goals", json={"title": "x", "due_date": "soon"}).status_code == 400
    gid = client.post("/api/goals", json={"title": "Keep going"}).json()["goals"][0]["id"]
    for n in range(12):
        client.post(f"/api/goals/{gid}/steps", json={"text": f"step {n}"})
    assert client.post(f"/api/goals/{gid}/steps", json={"text": "one too many"}).status_code == 400


def test_goals_belong_to_their_owner(client):
    gid = client.post("/api/goals", json={"title": "Mine"}).json()["goals"][0]["id"]
    step = client.post(f"/api/goals/{gid}/steps", json={"text": "a step"}).json()["goals"][0]["steps"][0]["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "correct horse", "display_name": "B"})
    assert client.patch(f"/api/goals/{gid}", json={"title": "Hacked"}).status_code == 404
    assert client.delete(f"/api/goals/{gid}").status_code == 404
    assert client.post(f"/api/goals/{gid}/steps", json={"text": "x"}).status_code == 404
    assert client.patch(f"/api/steps/{step}", json={"done": True}).status_code == 404
    assert client.delete(f"/api/steps/{step}").status_code == 404


def test_progress_is_measured_toward_the_target_in_the_right_direction():
    from chesscoach import goals

    assert goals.progress("up", 70, 90, 80) == {"percent": 50, "reached": False}
    assert goals.progress("up", 70, 90, 95) == {"percent": 100, "reached": True}
    assert goals.progress("up", 70, 90, 60) == {"percent": 0, "reached": False}
    assert goals.progress("down", 3, 1, 2) == {"percent": 50, "reached": False}        # fewer blunders is better
    assert goals.progress("down", 3, 1, 0.5) == {"percent": 100, "reached": True}
    assert goals.progress("up", 70, 90, None) == {"percent": None, "reached": False}


# -- tournament preparation ----------------------------------------------------------------------------


def test_every_target_position_is_a_legal_line_and_its_arrows_start_on_the_right_pieces():
    entries = {e["id"]: e for e in academy.repertoire()}
    assert set(prep.PLAYBOOK) == set(entries)                       # every repertoire opening has a position to aim for
    for opening_id, play in prep.PLAYBOOK.items():
        entry = entries[opening_id]
        board = chess.Board()
        for san in play["moves"]:
            board.push_san(san)                                     # raises if a move is illegal
        assert play["moves"][: len(entry["moves"])] == entry["moves"], opening_id     # it grows out of the opening itself
        colour = chess.WHITE if entry["side"] == "white" else chess.BLACK
        starts = [r["squares"][0] for r in play["routes"]] + [a["from"] for a in play["attacks"]]
        assert starts, opening_id
        for square in starts:
            piece = board.piece_at(chess.parse_square(square))
            assert piece is not None and piece.color == colour, f"{opening_id}: nothing of yours on {square}"
        for route in play["routes"]:
            assert len(route["squares"]) >= 2 and route["note"]
            for square in route["squares"]:
                chess.parse_square(square)
        for attack in play["attacks"]:
            chess.parse_square(attack["to"])
        assert play["aims"] and play["watch"]
        shown = prep.target_position(opening_id)
        assert shown["fen"] == board.fen() and shown["arrows"]
        assert [s["san"] for s in shown["steps"]] == play["moves"] and shown["steps"][-1]["fen"] == board.fen()


def test_the_countdown_and_days_until():
    today = dt.date(2026, 11, 1)
    assert prep.days_until("2026.11.14", today) == 13
    assert prep.days_until("2026.11.??", today) is None and prep.days_until("", today) is None
    assert prep.days_until("2026.02.31", today) is None                                 # not a real date
    plan = prep.schedule(4)
    assert [p["past"] for p in plan] == [True, True, False, False, False]             # "a week before" and "5 days before" are gone
    assert all("past" not in p for p in prep.schedule(None))


def test_the_prep_page_picks_the_next_tournament_and_suggests_openings(client):
    empty = client.get(f"/api/players/{client.pid}/prep").json()
    assert empty["event"] is None and empty["upcoming"] == [] and empty["days_until"] is None
    assert len(empty["white"]) == 3 and len(empty["black"]) == 3                       # openings even with no games yet
    assert all(o["target"]["fen"] and o["why"] for o in empty["white"] + empty["black"])
    assert {o["side"] for o in empty["white"]} == {"white"} and {o["side"] for o in empty["black"]} == {"black"}

    soon = (dt.date.today() + dt.timedelta(days=9)).isoformat()
    later = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    client.post("/api/events", json={"name": "Later Open", "start_date": later, "kind": "upcoming"})
    client.post("/api/events", json={"name": "State Open", "start_date": soon, "kind": "upcoming", "time_control": "G/30;d5"})
    got = client.get(f"/api/players/{client.pid}/prep").json()
    assert got["event"]["name"] == "State Open" and got["days_until"] == 9
    assert "quick time control" in got["time_tip"] and len(got["upcoming"]) == 2
    other = client.get(f"/api/players/{client.pid}/prep", params={"event_id": got["upcoming"][1]["id"]}).json()
    assert other["event"]["name"] == "Later Open" and other["days_until"] == 60
    assert client.get(f"/api/players/{client.pid}/prep", params={"event_id": 99999}).status_code == 404
    assert got["checklist"]["before"] and got["checklist"]["during"] and got["checklist"]["after"]


def test_the_openings_you_already_score_well_with_are_recommended_first():
    habits = {"habits": [{"id": "attack", "level": "work"}]}
    record = {"families": [{"family": "Italian Game", "color": "white", "games": 4, "score": 75}]}
    top = prep.recommend("white", habits, record)[0]
    assert top["id"] == "italian" and top["record"] == {"games": 4, "score": 75}
    assert any("scored 75%" in why for why in top["why"])
    cold = prep.recommend("white", habits, {"families": [{"family": "Italian Game", "color": "white", "games": 4, "score": 10}]})
    assert cold[0]["id"] != "italian"                                                   # one that is not working gives way


# -- thinking coach ---------------------------------------------------------------------------------


AFTER_QH5 = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"


def test_the_thinking_coach_asks_the_questions_and_describes_but_never_names_a_best_move(client):
    res = client.post("/api/think", json={"fen": AFTER_QH5, "last_uci": "d1h5"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["side"] == "black" and [s["id"] for s in out["steps"]] == ["change", "threats", "loose", "forcing", "king", "plan", "check"]
    assert all(s["title"] and s["question"] and s["facts"] for s in out["steps"])
    steps = {s["id"]: " ".join(s["facts"]) for s in out["steps"]}
    assert "queen to h5" in steps["change"] and "f7" in steps["change"]
    assert "Checkmate threat" in steps["threats"] and "Qxf7#" in steps["threats"]
    assert "loose" in steps["loose"].lower() or "None of your pieces is loose" in steps["loose"]
    assert "castle" in steps["king"].lower()
    assert "best move" not in " ".join(steps.values()).lower()
    assert "verdict" in out["balance"] and set(out["balance"]["scores"]) == set(thinking.balance.DIMENSIONS)


def test_the_thinking_coach_copes_with_odd_input(client):
    start = chess.STARTING_FEN
    assert client.post("/api/think", json={"fen": start}).json()["steps"][0]["facts"] == thinking.NO_LAST_MOVE
    assert client.post("/api/think", json={"fen": start, "last_uci": "zzzz"}).status_code == 200
    assert client.post("/api/think", json={"fen": start, "last_uci": "e2e4"}).status_code == 200      # nothing on e4: ignored
    assert client.post("/api/think", json={"fen": "nonsense"}).status_code == 400
    assert client.post("/api/think", json={"fen": "8/8/8/8/8/8/8/8 w - - 0 1"}).status_code == 400
    check = client.post("/api/think", json={"fen": "4k3/8/8/8/8/8/4r3/4K3 w - - 0 1"}).json()        # in check
    assert "in check" in " ".join(check["steps"][1]["facts"])
    assert client.post("/api/think", json={"fen": start, "color": "black"}).json()["side"] == "black"
    client.post("/api/auth/logout")
    assert client.post("/api/think", json={"fen": start}).status_code == 401


def test_the_guide_and_practice_positions(client):
    guide = client.get("/api/think/guide").json()
    assert len(guide["loop"]["steps"]) == 7 and len(guide["traps"]) >= 6 and guide["principles"] and guide["phases"]
    assert client.get(f"/api/players/{client.pid}/think/positions").json() == []                   # no games yet
    add(client, LOST_AS_BLACK)
    positions = client.get(f"/api/players/{client.pid}/think/positions").json()
    assert positions and positions[0]["fen"] and positions[0]["side"] == "black"
    assert not ({"best", "played", "lesson"} & set(positions[0]))                                   # the answer stays hidden
    chess.Board(positions[0]["fen"])

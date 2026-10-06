import time

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

SCHOLAR = """[Event "Club Championship"]
[Round "2"]
[Date "2026.09.01"]
[White "Opponent"]
[Black "Ayaan"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
"""

TWO_GAMES = SCHOLAR + """
[Event "Weekend Open"]
[Round "1"]
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
        yield c


def register(client, email="parent@example.com", password="correct horse", name="Parent"):
    return client.post("/api/auth/register", json={"email": email, "password": password, "display_name": name})


def add_player(client, name="Ayaan"):
    """The account's own student profile (created at sign-up); set its name so PGNs can be matched."""
    me = client.get("/api/auth/me").json()
    res = client.patch("/api/auth/me", json={"display_name": name, "email": me["user"]["email"], "rating": 1440})
    assert res.status_code == 200, res.text
    return me["player"]["id"]


def add_games(client, player_id, pgn, **extra):
    res = client.post("/api/games", json={"pgn": pgn, **extra})
    assert res.status_code == 200, res.text
    assert client.app.state.worker.wait_idle(120)
    return res.json()


# -- accounts -------------------------------------------------------------------


def test_register_sign_in_and_out(client):
    assert client.get("/api/auth/me").status_code == 401
    res = register(client)
    assert res.status_code == 200 and "cc_session" in res.cookies
    assert "httponly" in res.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["user"]["email"] == "parent@example.com"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    good = client.post("/api/auth/login", json={"email": "PARENT@example.com", "password": "correct horse"})
    assert good.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_registration_rules(client):
    assert register(client, password="short").status_code == 400
    assert register(client, email="not-an-email").status_code == 400
    assert register(client).status_code == 200
    assert register(client).status_code == 409


def test_wrong_password_is_rejected_and_throttled(client):
    register(client)
    client.post("/api/auth/logout")
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": "parent@example.com", "password": "nope nope"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "parent@example.com", "password": "correct horse"})
    assert blocked.status_code == 429


def test_password_change_and_account_delete(client):
    register(client)
    bad = client.post("/api/auth/password", json={"current": "wrong wrong", "new": "another long one"})
    assert bad.status_code == 403
    ok = client.post("/api/auth/password", json={"current": "correct horse", "new": "another long one"})
    assert ok.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "parent@example.com", "password": "correct horse"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "parent@example.com", "password": "another long one"}).status_code == 200
    pid = add_player(client)
    assert client.post("/api/auth/delete", json={"password": "another long one"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.app.state.db.one("SELECT COUNT(*) n FROM players")["n"] == 0


def test_signup_can_be_closed(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path, allow_signup=False), engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        assert register(c).status_code == 403


def test_cross_site_writes_are_blocked(client):
    register(client)
    body = {"display_name": "Evil", "email": "parent@example.com"}
    hostile = client.patch("/api/auth/me", json=body, headers={"Origin": "https://evil.example"})
    assert hostile.status_code == 403
    assert client.get("/api/auth/me").json()["user"]["display_name"] == "Parent"
    same = client.patch("/api/auth/me", json={**body, "display_name": "Fine"}, headers={"Origin": "http://testserver"})
    assert same.status_code == 200


def test_account_creation_is_limited_per_address(client):
    for i in range(10):
        assert register(client, email=f"user{i}@example.com").status_code == 200
        client.post("/api/auth/logout")
    assert register(client, email="one-too-many@example.com").status_code == 429


def test_download_filename_is_sanitised(client):
    register(client)
    pid = add_player(client, 'Ay"aan\r\nX-Evil: 1')
    res = client.get(f"/api/players/{pid}/export.pgn")
    assert res.status_code == 200
    disposition = res.headers["content-disposition"]
    assert "\n" not in disposition and '"aan' not in disposition and "X-Evil" in disposition.replace("_", "")


def test_security_headers_and_health(client):
    res = client.get("/api/health")
    assert res.json() == {"status": "ok"}
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["cache-control"] == "no-store"


# -- players & isolation ---------------------------------------------------------


def test_each_account_is_one_student_with_a_personal_profile(client):
    res = register(client, name="Duke")
    me = client.get("/api/auth/me").json()
    assert me["player"]["name"] == "Duke" and me["player"]["rating"] is None
    pid = me["player"]["id"]
    edited = client.patch("/api/auth/me", json={"display_name": "Duke N", "email": "parent@example.com",
                                                "rating": 1500, "rating_system": "FIDE"})
    assert edited.json()["player"]["rating"] == 1500 and edited.json()["player"]["name"] == "Duke N"
    assert client.get("/api/auth/me").json()["player"]["id"] == pid  # still one profile
    bad = client.patch("/api/auth/me", json={"display_name": "x", "email": "parent@example.com", "rating_system": "Nope"})
    assert bad.status_code == 400
    assert client.get("/api/players").status_code == 404  # there is no list of players

    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    other = client.get("/api/auth/me").json()["player"]["id"]
    assert other != pid
    assert client.get(f"/api/players/{pid}/library").status_code == 404
    assert client.get(f"/api/players/{pid}/dashboard").status_code == 404


def test_one_account_cannot_read_anothers_games(client):
    register(client)
    pid = add_player(client)
    gid = add_games(client, pid, SCHOLAR)["games"][0]["id"]
    assert client.get(f"/api/games/{gid}").status_code == 200
    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    assert client.get(f"/api/games/{gid}").status_code == 404
    assert client.patch(f"/api/games/{gid}", json={"event": "x"}).status_code == 404
    assert client.delete(f"/api/games/{gid}").status_code == 404
    # A new account's own list is empty.
    mine = client.get("/api/auth/me").json()["player"]["id"]
    assert client.get(f"/api/players/{mine}/library").json() == []


# -- games -----------------------------------------------------------------------


def test_adding_a_game_queues_and_analyses_it(client):
    register(client)
    pid = add_player(client)
    added = add_games(client, pid, SCHOLAR)
    game = added["games"][0]
    assert game["color"] == "black" and game["outcome"] == "loss"
    assert game["event"] == "Club Championship" and game["round"] == "2"
    assert game["opening_name"]
    full = client.get(f"/api/games/{game['id']}").json()
    assert full["status"] == "done"
    analysis = full["analysis"]
    assert analysis["moments"][0]["category"] == "missed_threat"
    assert len(analysis["timeline"]) == 8 and len(analysis["moves"]) == 7
    assert analysis["moments"][0]["balance"]["before"]["verdict"]["text"]


def test_games_are_filed_by_month_with_tournaments_inside(client):
    register(client)
    pid = add_player(client)
    added = add_games(client, pid, TWO_GAMES)
    assert len(added["games"]) == 2
    sections = client.get(f"/api/players/{pid}/library").json()
    assert [s["label"] for s in sections] == ["September 2026"]
    september = sections[0]
    assert [t["event"] for t in september["tournaments"]] == ["Weekend Open", "Club Championship"]  # newest first
    assert september["loose"] == [] and (september["wins"], september["losses"]) == (1, 1)
    assert september["tournaments"][0]["games"][0]["status"] == "done"


def test_sections_default_to_the_current_month_and_can_be_chosen(client):
    register(client)
    pid = add_player(client)
    moves = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"
    now = time.localtime()
    add_games(client, pid, moves, color="white")                       # nothing given: this month
    add_games(client, pid, moves + " 4. c3", color="white", year=2025, month=12, event="Winter Open", round="4")
    add_games(client, pid, moves + " 4. b4", color="white", year=2025, month=12, opponent="Sam")
    sections = client.get(f"/api/players/{pid}/library").json()
    assert [s["key"] for s in sections] == [f"{now.tm_year:04d}-{now.tm_mon:02d}", "2025-12"]
    this_month, december = sections
    assert len(this_month["loose"]) == 1 and this_month["tournaments"] == []   # no "casual games" bucket
    assert this_month["loose"][0]["event"] == ""
    assert december["label"] == "December 2025"
    assert december["tournaments"][0]["event"] == "Winter Open" and december["tournaments"][0]["games"][0]["round"] == "4"
    assert december["loose"][0]["opponent"] == "Sam"


def test_a_games_own_date_wins_unless_you_untick_it(client):
    register(client)
    pid = add_player(client)
    kept = add_games(client, pid, SCHOLAR, year=2024, month=3)["games"][0]           # the PGN says 2026.09.01
    assert kept["date"] == "2026.09.01"
    other = SCHOLAR.replace("3. Qh5 Nf6 4. Qxf7#", "3. Qh5 g6 4. Qf3 Nf6")          # a different game, same headers
    ignored = add_games(client, pid, other, year=2024, month=3, prefer_pgn_date=False)["games"][0]
    assert ignored["date"] == "2024.03.??"

    same_month = client.patch(f"/api/games/{kept['id']}", json={"year": 2026, "month": 9}).json()
    assert same_month["date"] == "2026.09.01"                                       # exact day kept
    moved = client.patch(f"/api/games/{kept['id']}", json={"month": 10}).json()
    assert moved["date"] == "2026.10.??"
    sections = client.get(f"/api/players/{pid}/library").json()
    assert [s["key"] for s in sections] == ["2026-10", "2024-03"]


def test_duplicates_are_skipped_and_details_can_be_edited(client):
    register(client)
    pid = add_player(client)
    gid = add_games(client, pid, SCHOLAR)["games"][0]["id"]
    again = client.post("/api/games", json={"player_id": pid, "pgn": SCHOLAR}).json()
    assert again["games"] == [] and "already added" in again["skipped"][0]
    edited = client.patch(f"/api/games/{gid}", json={"event": "Spring Open", "round": "5", "opponent": "Sam"})
    assert edited.json()["event"] == "Spring Open" and edited.json()["opponent"] == "Sam"
    assert client.patch(f"/api/games/{gid}", json={"result": "banana"}).status_code == 400
    assert client.delete(f"/api/games/{gid}").status_code == 200
    assert client.get(f"/api/games/{gid}").status_code == 404


def test_a_bare_move_list_needs_a_side_and_can_be_labelled(client):
    register(client)
    pid = add_player(client)
    moves = "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"
    unclear = client.post("/api/games", json={"player_id": pid, "pgn": moves})
    assert unclear.status_code == 400 and "Choose White or Black" in unclear.json()["detail"]
    added = add_games(client, pid, moves, color="black", event="Home blitz", opponent="Dad", year=2026, month=10)
    game = added["games"][0]
    assert (game["event"], game["opponent"], game["black"], game["white"]) == ("Home blitz", "Dad", "Ayaan", "Dad")
    assert game["result"] == "1-0" and game["date"] == "2026.10.??"


def test_mistyped_moves_get_a_clear_message(client):
    register(client)
    pid = add_player(client)
    res = client.post("/api/games", json={"player_id": pid, "pgn": "1. e4 e5 2. Qxe5", "color": "white"})
    assert res.status_code == 400 and "Could not read the moves after move 2" in res.json()["detail"]


def test_legal_moves_endpoint_supports_board_entry(client):
    assert client.get("/api/legal").status_code == 401
    register(client)
    start = client.get("/api/legal").json()
    assert start["turn"] == "white" and len(start["moves"]) == 20
    e4 = next(m for m in start["moves"] if m["uci"] == "e2e4")
    assert e4["san"] == "e4" and " b " in e4["fen"]
    assert client.get("/api/legal", params={"fen": "nonsense"}).status_code == 400


def test_interrupted_analysis_is_resumed_on_restart(tmp_path, engine):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        register(c)
        pid = add_player(c)
        add_games(c, pid, SCHOLAR)
        c.app.state.db.run("UPDATE games SET status = 'analyzing', analysis = NULL")
    app2 = create_app(settings, engine_factory=lambda: engine, close_engine=False)
    with TestClient(app2) as c2:
        assert app2.state.worker.wait_idle(120)
        assert app2.state.db.one("SELECT status FROM games")["status"] == "done"


def test_insight_endpoints_for_a_player_with_one_game(client):
    register(client)
    pid = add_player(client)
    gid = add_games(client, pid, SCHOLAR)["games"][0]["id"]
    dash = client.get(f"/api/players/{pid}/dashboard").json()
    assert dash["games"] == 1 and dash["pending"] == 0 and dash["record"]["losses"] == 1
    habits = client.get(f"/api/players/{pid}/habits").json()
    assert habits["ready"] is False and habits["habits"] == []
    wins = client.get(f"/api/players/{pid}/wins").json()
    assert len(wins) == 1 and wins[0]["kind"] == "turning_point" and wins[0]["played"]["san"] == "Nf6"
    assert wins[0]["line_text"] and wins[0]["opponent"] == "Opponent"
    fams = client.get(f"/api/players/{pid}/openings").json()["families"]
    assert len(fams) == 1 and fams[0]["color"] == "black"
    work = client.get(f"/api/players/{pid}/workbook").json()
    assert work and work[0]["puzzle"]["good_moves"] and work[0]["id"].startswith(f"g{gid}-")

    assert client.get(f"/api/players/{pid}/progress").json() == {"solved": []}
    for _ in range(2):  # marking twice is harmless
        assert client.post(f"/api/players/{pid}/puzzles/{work[0]['id']}/solved").status_code == 200
    assert client.get(f"/api/players/{pid}/progress").json() == {"solved": [work[0]["id"]]}

    bal = client.get(f"/api/games/{gid}/balance", params={"ply": 5}).json()
    assert set(bal["scores"]) == {"material", "king_safety", "activity", "space", "structure", "initiative"}
    assert bal["scores"]["king_safety"] < 0  # Black's king after 3.Qh5
    assert client.get(f"/api/games/{gid}/balance", params={"ply": 99}).status_code == 400


def test_insights_are_private_to_the_owner(client):
    register(client)
    pid = add_player(client)
    add_games(client, pid, SCHOLAR)
    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    for path in ("dashboard", "habits", "wins", "openings", "workbook", "progress"):
        assert client.get(f"/api/players/{pid}/{path}").status_code == 404, path
    assert client.post(f"/api/players/{pid}/puzzles/x/solved").status_code == 404


def test_library_requires_sign_in_and_serves_content(client):
    assert client.get("/api/library/repertoire").status_code == 401
    register(client)
    fams = client.get("/api/library/openings/families").json()
    assert fams[0]["name"] == "Sicilian Defense"
    tree = client.get("/api/library/openings/browse", params={"moves": "e4,e5"}).json()
    assert tree["opening"]["name"] == "King's Pawn Game" and tree["next"][0]["san"] == "Nf3"
    assert client.get("/api/library/openings/browse", params={"moves": "e4,Qh5,Qh5"}).status_code == 404
    assert client.get("/api/library/openings/search", params={"q": "evans"}).json()[0]["name"].startswith("Italian Game: Evans")
    assert len(client.get("/api/library/repertoire").json()) >= 8
    themes = {t["id"]: t["count"] for t in client.get("/api/library/academy/themes").json()}
    assert themes["mates"] >= 8 and themes["traps"] >= 3
    puzzles = client.get("/api/library/academy/puzzles", params={"theme": "traps"}).json()
    assert puzzles and all(p["theme"] == "traps" and p["line"] for p in puzzles)
    page = client.get("/api/library/model-games").json()
    assert page["total"] >= 5 and {g["id"] for g in page["games"]} >= {"opera", "immortal"}
    bands = {b["key"]: b["count"] for b in client.get("/api/library/model-games/bands").json()}
    assert bands["historic"] >= 5
    only = client.get("/api/library/model-games", params={"band": "historic", "q": "opera"}).json()
    assert [g["id"] for g in only["games"]] == ["opera"]
    assert client.get("/api/library/model-games", params={"limit": 2, "offset": 1}).json()["games"][0]["id"] != page["games"][0]["id"]
    opera = client.get("/api/library/model-games/opera").json()
    assert opera["moves"][-1]["san"] == "Rd8#" and opera["notes"]
    assert client.get("/api/library/model-games/none").status_code == 404


def test_folders_can_be_created_used_moved_and_deleted(client):
    register(client)
    pid = add_player(client)
    fid = client.post("/api/folders", json={"name": "Best attacks"}).json()["id"]
    assert client.post("/api/folders", json={"name": "best ATTACKS"}).status_code == 409   # names are unique
    other = client.post("/api/folders", json={"name": "Vs Sam"}).json()["id"]

    g1 = add_games(client, pid, SCHOLAR, folder_id=fid)["games"][0]
    assert g1["folder_id"] == fid
    g2 = add_games(client, pid, "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5", color="white")["games"][0]
    assert g2["folder_id"] is None

    listing = client.get(f"/api/players/{pid}/folders").json()
    assert [(f["name"], len(f["games"])) for f in listing["folders"]] == [("Best attacks", 1), ("Vs Sam", 0)]
    assert [g["id"] for g in listing["unfiled"]] == [g2["id"]]

    moved = client.patch(f"/api/games/{g2['id']}", json={"folder_id": other}).json()
    assert moved["folder_id"] == other
    assert client.patch(f"/api/games/{g2['id']}", json={"folder_id": 0}).json()["folder_id"] is None   # 0 = no folder
    assert client.patch(f"/api/games/{g2['id']}", json={"folder_id": 99999}).status_code == 404
    assert client.patch(f"/api/folders/{other}", json={"name": "Games vs Sam"}).json()["name"] == "Games vs Sam"

    # Deleting a folder keeps its games unless asked otherwise.
    assert client.delete(f"/api/folders/{fid}").json()["games_deleted"] == 0
    assert client.get(f"/api/games/{g1['id']}").json()["folder_id"] is None
    kept = add_games(client, pid, "1. d4 d5 2. c4 e6 3. Nc3 Nf6", color="white", folder_id=other)["games"][0]
    assert client.delete(f"/api/folders/{other}?games=delete").json()["games_deleted"] == 1
    assert client.get(f"/api/games/{kept['id']}").status_code == 404


def test_folders_are_private_and_games_can_be_deleted_in_bulk(client):
    register(client)
    pid = add_player(client)
    fid = client.post("/api/folders", json={"name": "Mine"}).json()["id"]
    ids = [add_games(client, pid, pgn, color="white")["games"][0]["id"] for pgn in (
        "1. e4 e5 2. Nf3 Nc6", "1. d4 d5 2. c4 e6", "1. c4 e5 2. Nc3 Nf6")]
    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    assert client.patch(f"/api/folders/{fid}", json={"name": "Stolen"}).status_code == 404
    assert client.delete(f"/api/folders/{fid}").status_code == 404
    assert client.post("/api/games", json={"pgn": "1. e4 e5", "color": "white", "folder_id": fid}).status_code == 404
    assert client.post("/api/games/delete", json={"ids": ids}).json()["deleted"] == 0     # not theirs
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "parent@example.com", "password": "correct horse"})
    assert client.post("/api/games/delete", json={"ids": ids[:2]}).json()["deleted"] == 2
    remaining = [g["id"] for s in client.get(f"/api/players/{pid}/library").json() for g in s["games"]]
    assert remaining == [ids[2]]


def test_analysis_carries_commentary_for_every_move_and_workbook_shows_the_source(client):
    register(client)
    pid = add_player(client)
    gid = add_games(client, pid, SCHOLAR, opponent="Rival")["games"][0]["id"]
    analysis = client.get(f"/api/games/{gid}").json()["analysis"]
    commentary = analysis["commentary"]
    assert [c["ply"] for c in commentary] == list(range(1, 8))
    assert commentary[0]["text"].startswith("Your opponent ")            # White moved first; the player is Black
    assert "Checkmate!" in commentary[-1]["text"] and "mate" in commentary[-1]["tags"]
    item = client.get(f"/api/players/{pid}/workbook").json()[0]
    source = item["game"]
    assert (source["opponent"], source["event"], source["match"], source["color"]) == ("Rival", "Club Championship", "2", "black")
    assert source["played"] == "Nf6" and source["date"] == "2026.09.01" and source["opening"]


def test_playing_the_computer(client):
    assert client.post("/api/play/reply", json={"fen": chess_start(), "level": 3}).status_code == 401
    register(client)
    levels = client.get("/api/play/levels").json()
    assert [lv["id"] for lv in levels] == list(range(1, 9)) and levels[0]["label"] == "Beginner"
    reply = client.post("/api/play/reply", json={"fen": chess_start(), "level": 1}).json()
    assert len(reply["move"]["uci"]) >= 4 and reply["over"] is False and " b " in reply["fen"]
    hint = client.post("/api/play/hint", json={"fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"}).json()
    assert hint["san"] in ("g6", "Qe7", "Qf6", "Nh6") and hint["text"]
    over = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    scholar = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
    best = client.post("/api/play/suggest", json={"fen": scholar}).json()
    assert best["over"] is False and len(best["moves"]) == 2
    assert best["moves"][0]["uci"] != best["moves"][1]["uci"] and all(m["text"] and m["san"] for m in best["moves"])
    assert best["moves"][0]["wp"] >= best["moves"][1]["wp"]                      # the first is the better of the two
    three = client.post("/api/play/suggest", json={"fen": chess_start(), "n": 3}).json()["moves"]
    assert len(three) == 3 and len({m["uci"] for m in three}) == 3
    assert three[0]["wp"] >= three[1]["wp"] >= three[2]["wp"]                    # best first
    assert len(client.post("/api/play/suggest", json={"fen": chess_start(), "n": 1}).json()["moves"]) == 1
    assert client.post("/api/play/suggest", json={"fen": chess_start(), "n": 4}).status_code == 422
    assert client.post("/api/play/suggest", json={"fen": over}).json() == {"moves": [], "context": None, "over": True}
    assert client.post("/api/play/suggest", json={"fen": "nonsense"}).status_code == 400
    client.post("/api/auth/logout")
    assert client.post("/api/play/suggest", json={"fen": scholar}).status_code == 401
    client.post("/api/auth/login", json={"email": "parent@example.com", "password": "correct horse"})
    assert client.post("/api/play/reply", json={"fen": over, "level": 3}).status_code == 400
    assert client.post("/api/play/reply", json={"fen": "nonsense", "level": 3}).status_code == 400
    assert client.post("/api/play/reply", json={"fen": "8/8/8/8/8/8/8/8 w - - 0 1", "level": 3}).status_code == 400   # no kings


def chess_start():
    return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_journey_and_daily_puzzle_endpoints(client):
    register(client)
    pid = add_player(client)
    empty = client.get(f"/api/players/{pid}/journey").json()
    assert empty["xp"] == 0 and empty["rank"]["name"] == "Pawn" and empty["earned"] == 0
    add_games(client, pid, SCHOLAR)
    assert client.post(f"/api/players/{pid}/puzzles/mate-scholar/solved").status_code == 200
    out = client.get(f"/api/players/{pid}/journey").json()
    assert out["xp"] == 28 and out["stats"] == {"games": 1, "puzzles": 1}
    assert out["streak"]["today_done"] is True and out["streak"]["current"] == 1
    assert {b["id"] for b in out["badges"] if b["earned"]} >= {"first-game", "first-puzzle"}
    daily = client.get("/api/library/academy/daily").json()
    assert daily["fens"] and daily["line"]
    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    assert client.get(f"/api/players/{pid}/journey").status_code == 404


def test_games_analysed_before_commentary_existed_are_redone_on_start(tmp_path, engine):
    import json
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, engine_factory=lambda: engine, close_engine=False)
    with TestClient(app) as c:
        register(c)
        pid = add_player(c)
        gid = add_games(c, pid, SCHOLAR)["games"][0]["id"]
        old = json.loads(app.state.db.one("SELECT analysis FROM games WHERE id = ?", (gid,))["analysis"])
        old.pop("commentary")          # what an analysis made by an earlier version looks like
        app.state.db.run("UPDATE games SET analysis = ? WHERE id = ?", (json.dumps(old), gid))
    app2 = create_app(settings, engine_factory=lambda: engine, close_engine=False)
    with TestClient(app2):
        assert app2.state.worker.wait_idle(120)
        row = app2.state.db.one("SELECT status, analysis FROM games WHERE id = ?", (gid,))
        assert row["status"] == "done" and len(json.loads(row["analysis"])["commentary"]) == 7


def test_export_returns_the_players_games(client):
    register(client)
    pid = add_player(client)
    add_games(client, pid, TWO_GAMES)
    text = client.get(f"/api/players/{pid}/export.pgn").text
    assert text.count("[Event ") == 2 and "Qxf7#" in text

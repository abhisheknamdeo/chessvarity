"""Scoresheet photos, managing admins, read-only 'view as', and the community."""

import re
import time

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

PW = "correct horse"
OWNER = "owner@dukesmate.test"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 500
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
SCHOLAR = "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0"


@pytest.fixture()
def env(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mail_backend="memory", public_url="https://dm.test", feedback_to=OWNER,
                              admin_emails=(OWNER,), google_client_id="g", google_client_secret="s"),
                     engine_factory=lambda: None)
    with TestClient(app) as c:
        yield app, c


def user(app, email, name="Someone", confirm=False):
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": email, "password": PW, "display_name": name}).status_code == 200
    if confirm:
        c.post("/api/auth/send-verification")
        token = re.search(r"token=([\w-]+)", app.state.mailer.outbox[-1].text).group(1)
        assert c.post("/api/auth/verify", json={"token": token}).status_code == 200
    return c


def a_round(c):
    ev = c.post("/api/events", json={"name": "Spring Open", "start_date": "2026-04-01", "kind": "past", "rounds": 2}).json()
    return ev["id"], ev["rounds"][0]["id"]


def a_game(app, c, color="white", opponent="Real Kid Name", event="Secret Local Open"):
    player = c.get("/api/auth/me").json()["player"]["id"]
    res = c.post("/api/games", json={"pgn": SCHOLAR, "color": color, "opponent": opponent, "event": event})
    assert res.status_code == 200, res.text
    gid = res.json()["games"][0]["id"]
    # No engine in these tests: let the analysis thread give up on the game first, then fill in a finished analysis.
    assert app.state.worker.wait_idle(30)
    app.state.db.run("UPDATE games SET status = 'done', accuracy = 90, analysis = ? WHERE id = ?",
                     ('{"start_fen": "x", "moves": [{"san": "e4", "uci": "e2e4", "fen": "f"}], "timeline": [], '
                      '"commentary": [], "moments": [], "counts": {}, "summary": {"headline": "Quick win"}}', gid))
    return gid


# --- scoresheets -------------------------------------------------------------------------------------------------

def test_scoresheet_upload_view_and_delete(env, tmp_path):
    app, _ = env
    c = user(app, "kid@example.com")
    ev_id, rd = a_round(c)
    res = c.post(f"/api/rounds/{rd}/scoresheets", content=JPEG, headers={"Content-Type": "image/jpeg"})
    assert res.status_code == 200, res.text
    sid = res.json()["sheets"][0]["id"]
    assert c.get(f"/api/scoresheets/{sid}").content == JPEG
    assert c.get(f"/api/scoresheets/{sid}").headers["content-type"] == "image/jpeg"
    rounds = c.get(f"/api/players/{c.get('/api/auth/me').json()['player']['id']}/events").json()
    listed = [r for e in (rounds if isinstance(rounds, list) else rounds["events"]) for r in e["rounds"] if r["id"] == rd][0]
    assert [s["id"] for s in listed["scoresheets"]] == [sid]

    stranger = user(app, "other@example.com")
    assert stranger.get(f"/api/scoresheets/{sid}").status_code == 404  # only the owner sees it
    assert stranger.post(f"/api/rounds/{rd}/scoresheets", content=JPEG).status_code == 404

    stored = list((tmp_path / "uploads").rglob("*.jpg"))
    assert len(stored) == 1
    assert c.delete(f"/api/scoresheets/{sid}").json()["sheets"] == []
    assert not list((tmp_path / "uploads").rglob("*.jpg"))


def test_scoresheet_rejects_non_images_big_files_and_too_many(env):
    app, _ = env
    c = user(app, "kid@example.com")
    _, rd = a_round(c)
    assert c.post(f"/api/rounds/{rd}/scoresheets", content=b"<html>not a photo</html>").status_code == 400
    assert c.post(f"/api/rounds/{rd}/scoresheets", content=b"\xff\xd8\xff" + b"0" * (8 * 1024 * 1024)).status_code == 413
    for _ in range(6):
        assert c.post(f"/api/rounds/{rd}/scoresheets", content=PNG).status_code == 200
    assert c.post(f"/api/rounds/{rd}/scoresheets", content=PNG).status_code == 400


def test_deleting_round_event_or_account_removes_stored_photos(env, tmp_path):
    app, _ = env
    c = user(app, "kid@example.com")
    ev_id, rd = a_round(c)
    c.post(f"/api/rounds/{rd}/scoresheets", content=JPEG)
    c.delete(f"/api/rounds/{rd}")
    assert not list((tmp_path / "uploads").rglob("*.*"))
    ev_id, rd = a_round(c)
    c.post(f"/api/rounds/{rd}/scoresheets", content=JPEG)
    c.delete(f"/api/events/{ev_id}")
    assert not list((tmp_path / "uploads").rglob("*.*"))
    _, rd = a_round(c)
    c.post(f"/api/rounds/{rd}/scoresheets", content=JPEG)
    assert c.post("/api/auth/delete", json={"password": PW}).status_code == 200
    assert not list((tmp_path / "uploads").rglob("*.*"))


# --- admins and view-as ----------------------------------------------------------------------------------------

def test_admins_can_add_and_remove_admins_but_not_the_permanent_one(env):
    app, _ = env
    owner = user(app, OWNER, "Owner", confirm=True)
    helper = user(app, "helper@example.com", "Helper", confirm=True)
    assert helper.get("/api/admin/stats").status_code == 404
    admins = owner.post("/api/admin/admins", json={"email": "Helper@Example.com"}).json()["admins"]
    assert [(a["email"], a["permanent"]) for a in admins] == [(OWNER, True), ("helper@example.com", False)]
    assert helper.get("/api/admin/stats").status_code == 200
    assert helper.delete(f"/api/admin/admins/{OWNER}").status_code == 400
    owner.delete("/api/admin/admins/helper@example.com")
    assert helper.get("/api/admin/stats").status_code == 404


def test_added_admin_still_needs_a_confirmed_email(env):
    app, _ = env
    owner = user(app, OWNER, "Owner", confirm=True)
    owner.post("/api/admin/admins", json={"email": "new@example.com"})
    squatter = user(app, "new@example.com", "Squatter")  # signed up with the address but never confirmed it
    assert squatter.get("/api/admin/stats").status_code == 404


def test_view_as_is_read_only_and_returns_to_the_admin(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Kid")
    kid.patch("/api/auth/me", json={"display_name": "Kid", "email": "kid@example.com", "rating": 1234, "rating_system": "USCF"})
    kid_id = kid.get("/api/auth/me").json()["user"]["id"]
    owner = user(app, OWNER, "Owner", confirm=True)
    row = [a for a in owner.get("/api/admin/stats").json()["accounts"] if a["id"] == kid_id][0]
    assert row["rating"] == 1234 and row["rating_system"] == "USCF"

    assert owner.post(f"/api/admin/view-as/{kid_id}").status_code == 200
    me = owner.get("/api/auth/me").json()["user"]
    assert me["email"] == "kid@example.com" and me["viewed_by"] == "Owner" and me["is_admin"] is False
    res = owner.patch("/api/auth/me", json={"display_name": "Hacked", "email": "kid@example.com"})
    assert res.status_code == 403
    assert owner.post("/api/feedback", json={"message": "x"}).status_code == 403
    assert owner.get("/api/auth/oauth/google/start?link=1", follow_redirects=False).status_code == 403
    assert owner.get("/api/admin/stats").status_code == 404  # no admin powers while viewing

    assert owner.post("/api/auth/stop-viewing").status_code == 200
    me = owner.get("/api/auth/me").json()["user"]
    assert me["email"] == OWNER and me["is_admin"] is True and me["viewed_by"] is None
    # Viewing didn't count as the kid signing in.
    row = [a for a in owner.get("/api/admin/stats").json()["accounts"] if a["id"] == kid_id][0]
    assert kid.get("/api/auth/me").json()["user"]["display_name"] == "Kid"
    assert row["last_sign_in"] is not None


def test_only_admins_can_view_as(env):
    app, _ = env
    kid = user(app, "kid@example.com")
    other = user(app, "other@example.com")
    assert other.post(f"/api/admin/view-as/{kid.get('/api/auth/me').json()['user']['id']}").status_code == 404


# --- community -------------------------------------------------------------------------------------------------

def test_share_a_game_with_a_question_and_hide_private_details(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    gid = a_game(app, kid)
    assert kid.get(f"/api/games/{gid}/share").json() == {"share": None}
    s = kid.put(f"/api/games/{gid}/share", json={"question": "Was  4.Qxf7 really best?"}).json()["share"]
    assert s["question"] == "Was 4.Qxf7 really best?" and s["status"] == "public"

    other = user(app, "other@example.com", "Pal")
    feed = other.get("/api/community").json()["items"]
    assert len(feed) == 1 and feed[0]["author"] == "Duke" and feed[0]["white"] == "Duke" and feed[0]["black"] == "Opponent"
    assert feed[0]["event"] == "" and "kid@example.com" not in str(feed)
    assert other.get("/api/community?filter=questions").json()["items"] and other.get("/api/community?filter=mine").json()["items"] == []

    kid.put(f"/api/games/{gid}/share", json={"question": "", "show_opponent": True})
    card = other.get("/api/community").json()["items"][0]
    assert card["black"] == "Real Kid Name" and card["event"] == "Secret Local Open"
    assert other.get("/api/community?filter=questions").json()["items"] == []


def test_comments_likes_and_unanswered_filter(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    gid = a_game(app, kid)
    share = kid.put(f"/api/games/{gid}/share", json={"question": "Help?"}).json()["share"]["id"]
    other = user(app, "other@example.com", "Pal")
    assert len(other.get("/api/community?filter=unanswered").json()["items"]) == 1
    d = other.post(f"/api/community/{share}/comments", json={"body": "Nice mate on move 4!", "ply": 7}).json()
    assert d["comments"][0]["author"] == "Pal" and d["comments"][0]["ply"] == 7 and d["comments"][0]["mine"] is True
    assert other.get("/api/community?filter=unanswered").json()["items"] == []
    assert other.post(f"/api/community/{share}/comments", json={"body": "x", "ply": 99}).status_code == 400
    assert other.post(f"/api/community/{share}/like").json() == {"likes": 1, "liked": True}
    assert other.post(f"/api/community/{share}/like").json() == {"likes": 0, "liked": False}
    detail = kid.get(f"/api/community/{share}").json()
    assert detail["headline"] == "Quick win" and detail["moves"][0]["san"] == "e4"
    assert detail["comments"][0]["can_delete"] is True  # the sharer can tidy their thread
    assert kid.delete(f"/api/community/comments/{detail['comments'][0]['id']}").json() == {"ok": True}


def test_stop_sharing_and_unfinished_games(env):
    app, _ = env
    kid = user(app, "kid@example.com")
    gid = a_game(app, kid)
    app.state.db.run("UPDATE games SET status = 'queued' WHERE id = ?", (gid,))
    assert kid.put(f"/api/games/{gid}/share", json={}).status_code == 400
    app.state.db.run("UPDATE games SET status = 'done' WHERE id = ?", (gid,))
    share = kid.put(f"/api/games/{gid}/share", json={}).json()["share"]["id"]
    assert kid.delete(f"/api/games/{gid}/share").json() == {"share": None}
    assert user(app, "other@example.com").get(f"/api/community/{share}").status_code == 404
    stranger = user(app, "third@example.com")
    assert stranger.put(f"/api/games/{gid}/share", json={}).status_code == 404


def test_report_and_moderate(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    share = kid.put(f"/api/games/{a_game(app, kid)}/share", json={"question": "Q"}).json()["share"]["id"]
    rude = user(app, "rude@example.com", "Rude")
    comment = rude.post(f"/api/community/{share}/comments", json={"body": "something unkind"}).json()["comments"][0]["id"]
    assert kid.post("/api/community/report", json={"kind": "comment", "target_id": comment, "reason": "unkind"}).json() == {"ok": True}
    assert app.state.mailer.outbox[-1].to == OWNER and "reported" in app.state.mailer.outbox[-1].subject

    owner = user(app, OWNER, "Owner", confirm=True)
    reports = owner.get("/api/admin/reports").json()["reports"]
    assert reports[0]["target"]["text"] == "something unkind"
    assert rude.get("/api/admin/reports").status_code == 404
    owner.post("/api/admin/moderate", json={"kind": "comment", "target_id": comment, "action": "hide"})
    assert kid.get(f"/api/community/{share}").json()["comments"] == []
    assert owner.get("/api/admin/reports").json()["reports"] == []
    owner.post("/api/admin/moderate", json={"kind": "share", "target_id": share, "action": "hide"})
    assert rude.get("/api/community").json()["items"] == []
    assert kid.get("/api/community?filter=mine").json()["items"][0]["status"] == "hidden"  # the sharer still sees it, marked


def test_community_needs_sign_in(env):
    app, c = env
    assert c.get("/api/community").status_code == 401


# --- community points and levels ---------------------------------------------------------------------------------

def standing(c):
    return c.get("/api/community/me").json()


def test_points_for_sharing_asking_answering_and_likes(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    assert standing(kid)["points"] == 0 and standing(kid)["name"] == "Newcomer" and standing(kid)["rank"] is None
    share = kid.put(f"/api/games/{a_game(app, kid)}/share", json={"question": "Help?"}).json()["share"]["id"]
    assert standing(kid)["points"] == 15  # share 10 + question 5

    pal = user(app, "pal@example.com", "Pal")
    first = pal.post(f"/api/community/{share}/comments", json={"body": "Try 3.Nf3"}).json()["comments"][0]["id"]
    pal.post(f"/api/community/{share}/comments", json={"body": "and castle early"})
    assert standing(pal)["points"] == 3 + 3 + 5  # two comments, and the first answer
    assert standing(pal)["breakdown"] == {"comment": 6, "first_answer": 5}

    kid.post(f"/api/community/{share}/comments", json={"body": "thanks!"})  # own game: no points
    assert standing(kid)["points"] == 15
    assert kid.post(f"/api/community/comments/{first}/helpful").json() == {"helpful": 1, "marked": True}
    pal.post(f"/api/community/{share}/like")
    assert standing(pal)["points"] == 11 + 3
    assert standing(kid)["points"] == 15 + 2
    assert kid.post(f"/api/community/comments/{first}/helpful").json() == {"helpful": 0, "marked": False}
    assert standing(pal)["points"] == 11


def test_no_points_for_liking_yourself_or_for_hidden_content(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    share = kid.put(f"/api/games/{a_game(app, kid)}/share", json={}).json()["share"]["id"]
    kid.post(f"/api/community/{share}/like")
    assert standing(kid)["points"] == 10
    mine = kid.post(f"/api/community/{share}/comments", json={"body": "note"}).json()["comments"][0]["id"]
    assert kid.post(f"/api/community/comments/{mine}/helpful").status_code == 400
    owner = user(app, OWNER, "Owner", confirm=True)
    owner.post("/api/admin/moderate", json={"kind": "share", "target_id": share, "action": "hide"})
    assert standing(kid)["points"] == 0


def test_daily_cap_on_comment_points(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    share = kid.put(f"/api/games/{a_game(app, kid)}/share", json={}).json()["share"]["id"]
    pal = user(app, "pal@example.com", "Pal")
    for i in range(14):
        assert pal.post(f"/api/community/{share}/comments", json={"body": f"c{i}"}).status_code == 200
    assert standing(pal)["breakdown"]["comment"] == 10 * 3


def test_levels_and_leaderboard(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    gid = a_game(app, kid)
    kid.put(f"/api/games/{gid}/share", json={"question": "Q"})
    likers = [user(app, f"l{i}@example.com", f"L{i}") for i in range(3)]
    share = kid.get("/api/community?filter=mine").json()["items"][0]["id"]
    for c in likers:
        c.post(f"/api/community/{share}/like")
    s = standing(kid)
    assert s["points"] == 21 and s["name"] == "Helper" and s["next_name"] == "Contributor" and s["rank"] == 1
    board = likers[0].get("/api/community/leaderboard").json()["leaders"]
    assert board[0] == {"rank": 1, "name": "Duke", "points": 21, "me": False, "level": "Helper"}
    assert likers[0].get("/api/community/leaderboard?period=month").json()["leaders"][0]["points"] == 21
    card = likers[0].get("/api/community").json()["items"][0]
    assert card["author_level"] == {"level": 2, "name": "Helper"}
    owner = user(app, OWNER, "Owner", confirm=True)
    row = [a for a in owner.get("/api/admin/stats").json()["accounts"] if a["email"] == "kid@example.com"][0]
    assert (row["points"], row["level"]) == (21, "Helper")


def test_games_to_ask_about_lists_unshared_finished_games(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    gid = a_game(app, kid)
    games = kid.get("/api/community/my-games").json()["games"]
    assert [g["id"] for g in games] == [gid] and "vs" in games[0]["label"]
    kid.put(f"/api/games/{gid}/share", json={"question": "?"})
    assert kid.get("/api/community/my-games").json()["games"] == []


# --- scoresheet photos on games (the Add games page and the game page) --------------------------------------------

def test_game_photos_include_its_rounds_and_go_when_the_game_goes(env, tmp_path):
    app, _ = env
    kid = user(app, "kid@example.com")
    gid = a_game(app, kid)
    res = kid.post(f"/api/games/{gid}/scoresheets", content=JPEG, headers={"Content-Type": "image/jpeg"})
    assert res.status_code == 200 and len(res.json()["sheets"]) == 1
    _, rd = a_round(kid)
    kid.post(f"/api/rounds/{rd}/link/{gid}")
    kid.post(f"/api/rounds/{rd}/scoresheets", content=PNG)
    assert len(kid.get(f"/api/games/{gid}/scoresheets").json()["sheets"]) == 2  # its own and its round's
    first = kid.get(f"/api/games/{gid}/scoresheets").json()["sheets"][0]["id"]
    assert len(kid.delete(f"/api/scoresheets/{first}?game={gid}").json()["sheets"]) == 1

    assert user(app, "x@example.com").get(f"/api/games/{gid}/scoresheets").status_code == 404
    kid.post(f"/api/games/{gid}/scoresheets", content=JPEG)
    assert len(list((tmp_path / "uploads").rglob("*.*"))) == 2
    kid.delete(f"/api/games/{gid}")
    assert len(list((tmp_path / "uploads").rglob("*.*"))) == 1  # the round's photo stays with the round


def test_bulk_game_delete_removes_photos(env, tmp_path):
    app, _ = env
    kid = user(app, "kid@example.com")
    gid = a_game(app, kid)
    kid.post(f"/api/games/{gid}/scoresheets", content=JPEG)
    kid.post("/api/games/delete", json={"ids": [gid]})
    assert not list((tmp_path / "uploads").rglob("*.*"))


def test_game_photo_limit(env):
    app, _ = env
    kid = user(app, "kid@example.com")
    gid = a_game(app, kid)
    for _ in range(6):
        assert kid.post(f"/api/games/{gid}/scoresheets", content=PNG).status_code == 200
    assert kid.post(f"/api/games/{gid}/scoresheets", content=PNG).status_code == 400


def test_admin_can_delete_an_account_after_typing_its_email(env, tmp_path):
    app, _ = env
    kid = user(app, "kid@example.com", "Kid")
    kid_id = kid.get("/api/auth/me").json()["user"]["id"]
    _, rd = a_round(kid)
    kid.post(f"/api/rounds/{rd}/scoresheets", content=JPEG)
    owner = user(app, OWNER, "Owner", confirm=True)
    owner_id = owner.get("/api/auth/me").json()["user"]["id"]
    assert owner.post(f"/api/admin/accounts/{kid_id}/delete", json={"confirm_email": "wrong@example.com"}).status_code == 400
    assert owner.post(f"/api/admin/accounts/{owner_id}/delete", json={"confirm_email": OWNER}).status_code == 400
    assert kid.post(f"/api/admin/accounts/{owner_id}/delete", json={"confirm_email": OWNER}).status_code == 404
    assert owner.post(f"/api/admin/accounts/{kid_id}/delete", json={"confirm_email": "Kid@Example.com"}).json() == {"ok": True}
    assert kid.get("/api/auth/me").status_code == 401
    assert not list((tmp_path / "uploads").rglob("*.*"))


# --- share links, profile phone/state, replying to messages ------------------------------------------------------

def test_share_link_works_without_an_account_and_can_be_turned_off(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    gid = a_game(app, kid)
    assert kid.get(f"/api/games/{gid}/link").json() == {"link": None}
    link = kid.post(f"/api/games/{gid}/link", json={}).json()["link"]
    assert link["path"] == f"/#/g/{link['token']}" and len(link["token"]) >= 16
    assert kid.post(f"/api/games/{gid}/link", json={}).json()["link"]["token"] == link["token"]  # the same link is kept

    anyone = TestClient(app)
    res = anyone.get(f"/api/public/games/{link['token']}")
    assert res.status_code == 200 and res.headers["x-robots-tag"].startswith("noindex")
    body = res.json()
    assert body["author"] == "Duke" and body["black"] == "Opponent" and body["event"] == "" and body["moves"][0]["san"] == "e4"
    assert "kid@example.com" not in res.text
    kid.post(f"/api/games/{gid}/link", json={"show_opponent": True})
    assert anyone.get(f"/api/public/games/{link['token']}").json()["black"] == "Real Kid Name"
    assert kid.get(f"/api/games/{gid}/link").json()["link"]["views"] == 2

    assert user(app, "x@example.com").post(f"/api/games/{gid}/link", json={}).status_code == 404
    kid.delete(f"/api/games/{gid}/link")
    assert anyone.get(f"/api/public/games/{link['token']}").status_code == 404
    assert anyone.get("/api/public/games/not-a-real-token").status_code == 404


def test_profile_phone_and_state(env):
    app, _ = env
    kid = user(app, "kid@example.com", "Duke")
    base = {"display_name": "Duke", "email": "kid@example.com"}
    me = kid.get("/api/auth/me").json()
    assert me["user"]["phone"] == "" and me["user"]["state"] == "" and {"code": "CA", "name": "California"} in me["states"]
    res = kid.patch("/api/auth/me", json={**base, "phone": " +1 (555) 123-4567 ", "state": "ca"})
    assert res.status_code == 200 and res.json()["user"]["phone"] == "+1 (555) 123-4567" and res.json()["user"]["state"] == "CA"
    assert kid.patch("/api/auth/me", json={**base, "phone": "call me"}).status_code == 400
    assert kid.patch("/api/auth/me", json={**base, "state": "ZZ"}).status_code == 400
    kid.patch("/api/auth/me", json=base)  # leaving them out keeps them
    assert kid.get("/api/auth/me").json()["user"]["state"] == "CA"
    owner = user(app, OWNER, "Owner", confirm=True)
    row = [a for a in owner.get("/api/admin/stats").json()["accounts"] if a["email"] == "kid@example.com"][0]
    assert (row["phone"], row["state"]) == ("+1 (555) 123-4567", "CA")


def test_admin_replies_to_and_deletes_messages(env):
    app, _ = env
    TestClient(app).post("/api/contact", json={"name": "A Parent", "email": "parent@example.com", "message": "Is there a family plan?"})
    owner = user(app, OWNER, "Owner", confirm=True)
    msg = owner.get("/api/admin/stats").json()["messages"][0]
    res = owner.post(f"/api/admin/messages/{msg['id']}/reply", json={"body": "Not yet, but it's free for now!"})
    assert res.status_code == 200 and res.json()["replied_by"] == "Owner"
    mail = app.state.mailer.outbox[-1]
    assert mail.to == "parent@example.com" and mail.reply_to == OWNER and "Re:" in mail.subject
    assert "Not yet, but it's free" in mail.text and "> Is there a family plan?" in mail.text
    again = owner.get("/api/admin/stats").json()["messages"][0]
    assert again["reply"] == "Not yet, but it's free for now!" and again["replied_at"]
    assert user(app, "kid@example.com").post(f"/api/admin/messages/{msg['id']}/reply", json={"body": "x"}).status_code == 404
    assert owner.delete(f"/api/admin/messages/{msg['id']}").json() == {"ok": True}
    assert owner.get("/api/admin/stats").json()["messages"] == []
    assert owner.delete(f"/api/admin/messages/{msg['id']}").status_code == 404

"""The community: games people make public (often with a question), comments, likes, reports and moderation.

Only signed-in users can see it. Shared games show the sharer's display name, never an email; the opponent's name
and the tournament stay hidden unless the sharer chooses to show them. Admins can hide anything that is reported.
"""

from __future__ import annotations

import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import gamify
from .deps import get_db, is_admin, require_admin, require_user
from .mailer import Message
from .security import Throttle

router = APIRouter(prefix="/api")
PAGE = 20


class ShareIn(BaseModel):
    question: str = Field(default="", max_length=500)
    show_opponent: bool = False


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    ply: int | None = Field(default=None, ge=0, le=1000)


class ReportIn(BaseModel):
    kind: Literal["share", "comment"]
    target_id: int
    reason: str = Field(default="", max_length=500)


class ModerateIn(BaseModel):
    kind: Literal["share", "comment"]
    target_id: int
    action: Literal["hide", "show", "dismiss"]


def _owned_game(request: Request, user: dict, game_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Game not found.")
    return row


def _share_out(s: dict) -> dict:
    return {"id": s["id"], "game_id": s["game_id"], "question": s["question"], "show_opponent": bool(s["show_opponent"]),
            "status": s["status"], "created_at": s["created_at"], "updated_at": s["updated_at"]}


@router.get("/games/{game_id}/share")
def get_share(game_id: int, request: Request) -> dict:
    user = require_user(request)
    _owned_game(request, user, game_id)
    s = get_db(request).one("SELECT * FROM shares WHERE game_id = ?", (game_id,))
    return {"share": _share_out(s) if s else None}


@router.put("/games/{game_id}/share")
def put_share(game_id: int, body: ShareIn, request: Request) -> dict:
    """Make a game public (or update its question). A game hidden by an admin stays hidden."""
    user = require_user(request)
    game = _owned_game(request, user, game_id)
    if game["status"] != "done":
        raise HTTPException(400, "The game can be shared once its analysis has finished.")
    db = get_db(request)
    now, question = time.time(), " ".join(body.question.split())
    existing = db.one("SELECT * FROM shares WHERE game_id = ?", (game_id,))
    if existing:
        db.run("UPDATE shares SET question = ?, show_opponent = ?, updated_at = ? WHERE id = ?",
               (question, int(body.show_opponent), now, existing["id"]))
    else:
        db.run("INSERT INTO shares(user_id, game_id, question, show_opponent, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
               (user["id"], game_id, question, int(body.show_opponent), "public", now, now))
    return {"share": _share_out(db.one("SELECT * FROM shares WHERE game_id = ?", (game_id,)))}


@router.delete("/games/{game_id}/share")
def stop_sharing(game_id: int, request: Request) -> dict:
    """Make the game private again. Its comments go with it."""
    user = require_user(request)
    _owned_game(request, user, game_id)
    get_db(request).run("DELETE FROM shares WHERE game_id = ? AND user_id = ?", (game_id, user["id"]))
    return {"share": None}


def _names(s: dict, g: dict) -> tuple[str, str]:
    """White and Black as shown to others: the sharer's display name, and the opponent only if they chose to show it."""
    me = s["author"]
    other = (g["opponent"] or (g["black"] if g["color"] == "white" else g["white"])) if s["show_opponent"] else "Opponent"
    return (me, other) if g["color"] == "white" else (other, me)


def _card(s: dict, me: dict, levels: dict | None = None) -> dict:
    white, black = _names(s, s)
    lv = (levels or {}).get(s["user_id"])
    return {
        "author_level": {"level": lv["level"], "name": lv["name"]} if lv else None,
        "id": s["id"], "author": s["author"], "mine": s["user_id"] == me["id"], "question": s["question"],
        "white": white, "black": black, "color": s["color"], "result": s["result"],
        "opening": s["opening_name"], "eco": s["opening_eco"], "accuracy": s["accuracy"], "plies": s["plies"],
        "event": s["event"] if s["show_opponent"] else "", "comments": s["comments"], "likes": s["likes"],
        "liked": bool(s["liked"]), "status": s["status"], "created_at": s["created_at"], "updated_at": s["updated_at"],
    }


FEED_SQL = (
    "SELECT s.*, u.display_name AS author, g.color, g.result, g.opening_name, g.opening_eco, g.accuracy, g.plies, "
    "g.white, g.black, g.opponent, g.event, "
    "(SELECT COUNT(*) FROM share_comments c WHERE c.share_id = s.id AND c.status = 'visible') AS comments, "
    "(SELECT COUNT(*) FROM share_likes l WHERE l.share_id = s.id) AS likes, "
    "(SELECT COUNT(*) FROM share_likes l WHERE l.share_id = s.id AND l.user_id = ?) AS liked "
    "FROM shares s JOIN users u ON u.id = s.user_id JOIN games g ON g.id = s.game_id "
)


@router.get("/community")
def feed(request: Request, filter: Literal["all", "questions", "unanswered", "mine"] = "all", page: int = 0) -> dict:
    me = require_user(request)
    where, params = ["(s.status = 'public' OR s.user_id = ?)"], [me["id"]]
    if filter == "questions":
        where.append("s.question != ''")
    elif filter == "unanswered":
        where.append("s.question != '' AND NOT EXISTS (SELECT 1 FROM share_comments c WHERE c.share_id = s.id "
                     "AND c.status = 'visible' AND c.user_id != s.user_id)")
    elif filter == "mine":
        where.append("s.user_id = ?")
        params.append(me["id"])
    page = max(0, min(page, 500))
    rows = get_db(request).all(
        FEED_SQL + f"WHERE {' AND '.join(where)} ORDER BY s.updated_at DESC, s.id DESC LIMIT ? OFFSET ?",
        (me["id"], *params, PAGE + 1, page * PAGE))
    levels = gamify.levels_for_users(get_db(request), [r["user_id"] for r in rows])
    return {"items": [_card(r, me, levels) for r in rows[:PAGE]], "more": len(rows) > PAGE, "page": page}


@router.get("/community/my-games")
def games_to_ask_about(request: Request) -> dict:
    """My analyzed games that aren't shared yet: what I can ask the community about."""
    me = require_user(request)
    rows = get_db(request).all(
        "SELECT g.id, g.white, g.black, g.result, g.date, g.event, g.opening_name, g.color, g.created_at FROM games g "
        "WHERE g.user_id = ? AND g.status = 'done' AND NOT EXISTS (SELECT 1 FROM shares s WHERE s.game_id = g.id) "
        "ORDER BY g.created_at DESC LIMIT 100", (me["id"],))
    return {"games": [{"id": r["id"], "label": f"{r['white']} vs {r['black']} ({r['result']})",
                       "detail": " · ".join(x for x in (r["date"].replace("??", "").strip(". ") if r["date"] else "", r["event"], r["opening_name"]) if x)}
                      for r in rows]}


@router.get("/community/me")
def my_standing(request: Request) -> dict:
    me = require_user(request)
    everyone = gamify.points(get_db(request))
    mine = everyone.get(me["id"], {"total": 0, "breakdown": {}})
    ahead = sum(1 for p in everyone.values() if p["total"] > mine["total"])
    return {**gamify.level_for(mine["total"]), "breakdown": mine["breakdown"], "rank": ahead + 1 if mine["total"] else None,
            "levels": [{"level": i + 1, "name": n, "at": f} for i, (f, n) in enumerate(gamify.LEVELS)],
            "how_to_earn": [{"what": w, "points": p} for w, p in gamify.HOW_TO_EARN]}


@router.get("/community/leaderboard")
def leaderboard(request: Request, period: Literal["all", "month"] = "all") -> dict:
    me = require_user(request)
    db = get_db(request)
    scores = gamify.points(db, since=_month_start() if period == "month" else 0.0)
    top = sorted(((uid, p["total"]) for uid, p in scores.items() if p["total"] > 0), key=lambda x: (-x[1], x[0]))[:20]
    names = {r["id"]: r["display_name"] for r in db.all(
        f"SELECT id, display_name FROM users WHERE id IN ({','.join('?' * len(top)) or 'NULL'})", tuple(u for u, _ in top))}
    overall = gamify.points(db) if period == "month" else scores
    return {"period": period, "leaders": [
        {"rank": i + 1, "name": names.get(uid, "Someone"), "points": pts, "me": uid == me["id"],
         "level": gamify.level_for(overall.get(uid, {}).get("total", 0))["name"]} for i, (uid, pts) in enumerate(top)]}


def _load_share(request: Request, me: dict, share_id: int) -> dict:
    s = get_db(request).one(FEED_SQL + "WHERE s.id = ?", (me["id"], share_id))
    if s is None or (s["status"] != "public" and s["user_id"] != me["id"] and not is_admin(request, me)):
        raise HTTPException(404, "That game isn't shared, or was removed.")
    return s


@router.get("/community/{share_id}")
def detail(share_id: int, request: Request) -> dict:
    me = require_user(request)
    s = _load_share(request, me, share_id)
    db = get_db(request)
    game = db.one("SELECT analysis FROM games WHERE id = ?", (s["game_id"],))
    analysis = json.loads(game["analysis"] or "{}")
    admin = is_admin(request, me)
    comments = db.all(
        "SELECT c.id, c.user_id, c.ply, c.body, c.status, c.created_at, u.display_name AS author, "
        "(SELECT COUNT(*) FROM comment_likes l WHERE l.comment_id = c.id) AS helpful, "
        "(SELECT COUNT(*) FROM comment_likes l WHERE l.comment_id = c.id AND l.user_id = ?) AS marked FROM share_comments c "
        "JOIN users u ON u.id = c.user_id WHERE c.share_id = ? AND (c.status = 'visible' OR ? = 1) ORDER BY c.id",
        (me["id"], share_id, 1 if admin else 0))
    levels = gamify.levels_for_users(db, [s["user_id"], *[c["user_id"] for c in comments]])
    badge = lambda uid: {"level": levels[uid]["level"], "name": levels[uid]["name"]}
    return {
        **_card(s, me, levels),
        "start_fen": analysis.get("start_fen"),
        "moves": [{"san": m["san"], "uci": m["uci"], "fen": m["fen"]} for m in analysis.get("moves", [])],
        "timeline": analysis.get("timeline", []),
        "commentary": analysis.get("commentary", []),
        "moments": analysis.get("moments", []),
        "counts": analysis.get("counts", {}),
        "headline": (analysis.get("summary") or {}).get("headline", ""),
        "comments": [{"id": c["id"], "author": c["author"], "by_sharer": c["user_id"] == s["user_id"], "mine": c["user_id"] == me["id"],
                      "ply": c["ply"], "body": c["body"], "hidden": c["status"] != "visible", "created_at": c["created_at"],
                      "helpful": c["helpful"], "marked": bool(c["marked"]), "author_level": badge(c["user_id"]),
                      "can_delete": c["user_id"] == me["id"] or s["user_id"] == me["id"] or admin} for c in comments],
        "can_moderate": admin,
    }


@router.post("/community/{share_id}/comments")
def add_comment(share_id: int, body: CommentIn, request: Request) -> dict:
    me = require_user(request)
    s = _load_share(request, me, share_id)
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Write a comment first.")
    throttle: Throttle = request.app.state.community_throttle
    if throttle.blocked(str(me["id"])):
        raise HTTPException(429, "You've written a lot of comments. Please take a break and try again later.")
    throttle.fail(str(me["id"]))
    if body.ply is not None and body.ply > (s["plies"] or 0):
        raise HTTPException(400, "That move is not in this game.")
    db = get_db(request)
    now = time.time()
    db.run("INSERT INTO share_comments(share_id, user_id, ply, body, status, created_at) VALUES (?,?,?,?,?,?)",
           (share_id, me["id"], body.ply, text, "visible", now))
    db.run("UPDATE shares SET updated_at = ? WHERE id = ?", (now, share_id))  # active threads rise to the top
    return detail(share_id, request)


@router.delete("/community/comments/{comment_id}")
def delete_comment(comment_id: int, request: Request) -> dict:
    me = require_user(request)
    db = get_db(request)
    c = db.one("SELECT c.*, s.user_id AS sharer FROM share_comments c JOIN shares s ON s.id = c.share_id WHERE c.id = ?", (comment_id,))
    if c is None or not (c["user_id"] == me["id"] or c["sharer"] == me["id"] or is_admin(request, me)):
        raise HTTPException(404, "Comment not found.")
    db.run("DELETE FROM share_comments WHERE id = ?", (comment_id,))
    return {"ok": True}


@router.post("/community/{share_id}/like")
def like(share_id: int, request: Request) -> dict:
    me = require_user(request)
    _load_share(request, me, share_id)
    db = get_db(request)
    if db.run("DELETE FROM share_likes WHERE share_id = ? AND user_id = ?", (share_id, me["id"])) == 0:
        db.run("INSERT OR IGNORE INTO share_likes(share_id, user_id, created_at) VALUES (?,?,?)", (share_id, me["id"], time.time()))
    likes = db.one("SELECT COUNT(*) n FROM share_likes WHERE share_id = ?", (share_id,))["n"]
    liked = db.one("SELECT 1 FROM share_likes WHERE share_id = ? AND user_id = ?", (share_id, me["id"])) is not None
    return {"likes": likes, "liked": liked}


@router.post("/community/comments/{comment_id}/helpful")
def mark_helpful(comment_id: int, request: Request) -> dict:
    """Toggle a "helpful" mark on someone else's comment."""
    me = require_user(request)
    db = get_db(request)
    c = db.one("SELECT c.*, s.status AS share_status, s.user_id AS sharer FROM share_comments c JOIN shares s ON s.id = c.share_id "
               "WHERE c.id = ? AND c.status = 'visible'", (comment_id,))
    if c is None or (c["share_status"] != "public" and c["sharer"] != me["id"]):
        raise HTTPException(404, "Comment not found.")
    if c["user_id"] == me["id"]:
        raise HTTPException(400, "You can't mark your own comment as helpful.")
    if db.run("DELETE FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, me["id"])) == 0:
        db.run("INSERT OR IGNORE INTO comment_likes(comment_id, user_id, created_at) VALUES (?,?,?)", (comment_id, me["id"], time.time()))
    n = db.one("SELECT COUNT(*) n FROM comment_likes WHERE comment_id = ?", (comment_id,))["n"]
    marked = db.one("SELECT 1 FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, me["id"])) is not None
    return {"helpful": n, "marked": marked}


def _month_start() -> float:
    now = time.gmtime()
    return time.mktime((now.tm_year, now.tm_mon, 1, 0, 0, 0, 0, 0, 0)) - time.timezone


@router.post("/community/report")
def report(body: ReportIn, request: Request) -> dict:
    me = require_user(request)
    db = get_db(request)
    table = "shares" if body.kind == "share" else "share_comments"
    if not db.one(f"SELECT 1 FROM {table} WHERE id = ?", (body.target_id,)):
        raise HTTPException(404, "Not found.")
    if db.one("SELECT 1 FROM reports WHERE kind = ? AND target_id = ? AND user_id = ? AND resolved_at IS NULL",
              (body.kind, body.target_id, me["id"])):
        return {"ok": True}
    reason = " ".join(body.reason.split())
    db.run("INSERT INTO reports(kind, target_id, user_id, reason, created_at) VALUES (?,?,?,?,?)",
           (body.kind, body.target_id, me["id"], reason, time.time()))
    owner = request.app.state.settings.feedback_to
    if owner:
        request.app.state.mailer.send(Message(owner, f"Chess Varsity: a {body.kind} was reported", (
            f"{me['display_name']} (account #{me['id']}) reported {body.kind} #{body.target_id}.\n"
            f"Reason: {reason or '(none given)'}\n\nReview it on the admin dashboard.")))
    return {"ok": True}


@router.get("/admin/reports")
def open_reports(request: Request) -> dict:
    require_admin(request)
    db = get_db(request)
    rows = db.all("SELECT r.*, u.display_name AS reporter FROM reports r LEFT JOIN users u ON u.id = r.user_id "
                  "WHERE r.resolved_at IS NULL ORDER BY r.id DESC LIMIT 100")
    out = []
    for r in rows:
        if r["kind"] == "share":
            t = db.one("SELECT s.id, s.question AS text, s.status, u.display_name AS author, s.id AS share_id FROM shares s "
                       "JOIN users u ON u.id = s.user_id WHERE s.id = ?", (r["target_id"],))
        else:
            t = db.one("SELECT c.id, c.body AS text, c.status, u.display_name AS author, c.share_id FROM share_comments c "
                       "JOIN users u ON u.id = c.user_id WHERE c.id = ?", (r["target_id"],))
        out.append({"id": r["id"], "kind": r["kind"], "target_id": r["target_id"], "reason": r["reason"], "reporter": r["reporter"],
                    "created_at": r["created_at"], "target": t})
    return {"reports": out}


@router.post("/admin/moderate")
def moderate(body: ModerateIn, request: Request) -> dict:
    require_admin(request)
    db = get_db(request)
    table, visible = ("shares", "public") if body.kind == "share" else ("share_comments", "visible")
    if body.action != "dismiss":
        db.run(f"UPDATE {table} SET status = ? WHERE id = ?", (visible if body.action == "show" else "hidden", body.target_id))
    db.run("UPDATE reports SET resolved_at = ? WHERE kind = ? AND target_id = ? AND resolved_at IS NULL",
           (time.time(), body.kind, body.target_id))
    return {"ok": True}

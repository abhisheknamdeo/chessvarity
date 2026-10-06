"""The owner's dashboard: registration numbers, recent accounts and messages. Only for admins (see deps.is_admin)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import gamify
from .deps import get_db, require_admin
from .mailer import Message
from .routes_account import EMAIL
from .security import COOKIE, create_session

log = logging.getLogger("chesscoach.admin")
VIEW_COOKIE = "cc_admin_session"  # the admin's own session, kept while they view as someone else
VIEW_HOURS = 1

router = APIRouter(prefix="/api/admin")

DAY = 86400


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


@router.get("/stats")
def stats(request: Request) -> dict:
    require_admin(request)
    db = get_db(request)
    now = time.time()
    users = db.all(
        "SELECT u.id, u.email, u.display_name, u.created_at, u.email_verified_at, u.phone, u.state, "
        "(SELECT COUNT(*) FROM games g WHERE g.user_id = u.id) AS games, "
        "(SELECT MAX(s.created_at) FROM sessions s WHERE s.user_id = u.id AND s.impersonator_id IS NULL) AS last_sign_in, "
        "(SELECT p.rating FROM players p WHERE p.user_id = u.id ORDER BY p.id LIMIT 1) AS rating, "
        "(SELECT p.rating_system FROM players p WHERE p.user_id = u.id ORDER BY p.id LIMIT 1) AS rating_system, "
        "(SELECT p.uscf_id FROM players p WHERE p.user_id = u.id ORDER BY p.id LIMIT 1) AS uscf_id, "
        "(SELECT COUNT(*) FROM shares sh WHERE sh.user_id = u.id) AS shared "
        "FROM users u ORDER BY u.created_at DESC"
    )
    since = lambda days: sum(1 for u in users if u["created_at"] >= now - days * DAY)
    community = gamify.points(db)

    # Sign-ups per day for the last 30 days (UTC), oldest first, including days with none.
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    per_day = dict.fromkeys(days, 0)
    for u in users:
        d = _day(u["created_at"])
        if d in per_day:
            per_day[d] += 1

    games = db.one("SELECT COUNT(*) AS n, SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done FROM games")
    messages = db.all(
        "SELECT id, category, name, email, message, page, created_at, reply, replied_at, replied_by FROM feedback ORDER BY id DESC LIMIT 25")
    by_kind = db.all("SELECT category, COUNT(*) AS n FROM feedback GROUP BY category")

    return {
        "generated_at": now,
        "totals": {
            "accounts": len(users),
            "confirmed": sum(1 for u in users if u["email_verified_at"]),
            "today": sum(1 for u in users if _day(u["created_at"]) == today.isoformat()),
            "last_7_days": since(7),
            "last_30_days": since(30),
            "active_7_days": sum(1 for u in users if u["last_sign_in"] and u["last_sign_in"] >= now - 7 * DAY),
            "with_games": sum(1 for u in users if u["games"]),
            "games": games["n"] or 0,
            "games_analysed": games["done"] or 0,
            "messages": {r["category"]: r["n"] for r in by_kind},
        },
        "per_day": [{"day": d, "n": per_day[d]} for d in days],
        "accounts": [
            {"id": u["id"], "name": u["display_name"], "email": u["email"], "joined": u["created_at"],
             "phone": u["phone"], "state": u["state"],
             "confirmed": bool(u["email_verified_at"]), "games": u["games"], "last_sign_in": u["last_sign_in"],
             "rating": u["rating"], "rating_system": u["rating_system"], "uscf_id": u["uscf_id"] or "", "shared": u["shared"],
             "points": community.get(u["id"], {}).get("total", 0),
             "level": gamify.level_for(community.get(u["id"], {}).get("total", 0))["name"]}
            for u in users[:200]
        ],
        "messages": messages,
        "open_reports": db.one("SELECT COUNT(*) n FROM reports WHERE resolved_at IS NULL")["n"],
        "shared_games": db.one("SELECT COUNT(*) n FROM shares")["n"],
    }


class AdminIn(BaseModel):
    email: str = Field(max_length=254)


def _admin_list(request: Request) -> list[dict]:
    db = get_db(request)
    permanent = request.app.state.settings.admin_emails
    added = db.all("SELECT a.email, a.created_at, u.display_name AS added_by FROM admins a "
                   "LEFT JOIN users u ON u.id = a.added_by ORDER BY a.created_at")
    rows = [{"email": e, "permanent": True, "added_at": None, "added_by": None} for e in permanent]
    rows += [{"email": a["email"], "permanent": False, "added_at": a["created_at"], "added_by": a["added_by"]}
             for a in added if a["email"] not in permanent]
    for r in rows:
        acct = db.one("SELECT display_name, email_verified_at FROM users WHERE email = ?", (r["email"],))
        r["has_account"], r["confirmed"] = acct is not None, bool(acct and acct["email_verified_at"])
        r["name"] = acct["display_name"] if acct else ""
    return rows


@router.get("/admins")
def list_admins(request: Request) -> dict:
    require_admin(request)
    return {"admins": _admin_list(request)}


@router.post("/admins")
def add_admin(body: AdminIn, request: Request) -> dict:
    me = require_admin(request)
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(400, "That email address doesn't look right.")
    db = get_db(request)
    if email not in request.app.state.settings.admin_emails and not db.one("SELECT 1 FROM admins WHERE email = ?", (email,)):
        db.run("INSERT INTO admins(email, added_by, created_at) VALUES (?,?,?)", (email, me["id"], time.time()))
        log.warning("admin %s added admin %s", me["email"], email)
    return {"admins": _admin_list(request)}


@router.delete("/admins/{email}")
def remove_admin(email: str, request: Request) -> dict:
    me = require_admin(request)
    email = email.strip().lower()
    if email in request.app.state.settings.admin_emails:
        raise HTTPException(400, "That admin is set on the server (CHESSCOACH_ADMIN_EMAILS) and can't be removed here.")
    get_db(request).run("DELETE FROM admins WHERE email = ?", (email,))
    log.warning("admin %s removed admin %s", me["email"], email)
    return {"admins": _admin_list(request)}


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.post("/messages/{message_id}/reply")
def reply_to_message(message_id: int, body: ReplyIn, request: Request) -> dict:
    """Email an answer to someone who sent feedback or a contact message, and keep it with the message."""
    me = require_admin(request)
    db = get_db(request)
    msg = db.one("SELECT * FROM feedback WHERE id = ?", (message_id,))
    if msg is None:
        raise HTTPException(404, "Message not found.")
    if not msg["email"]:
        raise HTTPException(400, "That message has no email address to reply to.")
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Write a reply first.")
    settings = request.app.state.settings
    quoted = "\n".join(f"> {line}" for line in msg["message"].splitlines())
    greeting = f"Hi {msg['name']}," if msg["name"] else "Hi,"
    request.app.state.mailer.send(Message(msg["email"], "Re: your message to Chess Varsity", (
        f"{greeting}\n\n{text}\n\n{me['display_name']}\nChess Varsity\n\n"
        f"You wrote on {time.strftime('%d %b %Y', time.gmtime(msg['created_at']))}:\n{quoted}"),
        reply_to=settings.feedback_to or None))
    db.run("UPDATE feedback SET reply = ?, replied_at = ?, replied_by = ? WHERE id = ?",
           (text, time.time(), me["display_name"], message_id))
    log.warning("admin %s replied to message #%s", me["email"], message_id)
    return {"ok": True, "replied_at": time.time(), "replied_by": me["display_name"]}


@router.delete("/messages/{message_id}")
def delete_message(message_id: int, request: Request) -> dict:
    me = require_admin(request)
    if get_db(request).run("DELETE FROM feedback WHERE id = ?", (message_id,)) == 0:
        raise HTTPException(404, "Message not found.")
    log.warning("admin %s deleted message #%s", me["email"], message_id)
    return {"ok": True}


class DeleteAccountIn(BaseModel):
    confirm_email: str = Field(max_length=254)


@router.post("/accounts/{user_id}/delete")
def delete_account(user_id: int, body: DeleteAccountIn, request: Request) -> dict:
    """Remove someone's account and everything in it (games, photos, shares, comments). Typing their email confirms it."""
    me = require_admin(request)
    db = get_db(request)
    target = db.one("SELECT id, email FROM users WHERE id = ?", (user_id,))
    if target is None:
        raise HTTPException(404, "Account not found.")
    if target["id"] == me["id"]:
        raise HTTPException(400, "To delete your own account, use your profile page.")
    if target["email"] in request.app.state.settings.admin_emails:
        raise HTTPException(400, "That account is a permanent admin and can't be deleted here.")
    if body.confirm_email.strip().lower() != target["email"].lower():
        raise HTTPException(400, "Type the account's email address exactly to confirm.")
    from .routes_scoresheets import delete_stored  # photos live outside the database
    delete_stored(request, "user_id = ?", (user_id,))
    db.run("DELETE FROM users WHERE id = ?", (user_id,))
    log.warning("admin %s deleted account #%s (%s)", me["email"], user_id, target["email"])
    return {"ok": True}


@router.post("/view-as/{user_id}")
def view_as(user_id: int, request: Request, response: Response) -> dict:
    """See the app exactly as this user does, read-only, for an hour at most. The admin's own session is kept aside."""
    me = require_admin(request)
    db = get_db(request)
    target = db.one("SELECT id, display_name, email FROM users WHERE id = ?", (user_id,))
    if target is None:
        raise HTTPException(404, "Account not found.")
    if target["id"] == me["id"]:
        raise HTTPException(400, "That's your own account.")
    settings = request.app.state.settings
    token = create_session(db, target["id"], VIEW_HOURS / 24, impersonator_id=me["id"])
    kw = dict(httponly=True, samesite="lax", secure=settings.cookie_secure, path="/")
    response.set_cookie(VIEW_COOKIE, request.cookies.get(COOKIE, ""), max_age=VIEW_HOURS * 3600, **kw)
    response.set_cookie(COOKIE, token, max_age=VIEW_HOURS * 3600, **kw)
    log.warning("admin %s (#%s) is viewing as #%s", me["email"], me["id"], target["id"])
    return {"ok": True, "user": {"id": target["id"], "name": target["display_name"]}}

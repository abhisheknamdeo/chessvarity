"""Request helpers shared by the route modules."""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

from .db import Database
from .security import COOKIE, user_for_session


def get_db(request: Request) -> Database:
    return request.app.state.db


def require_user(request: Request) -> dict:
    user = user_for_session(request.app.state.db, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Please sign in.")
    if request.app.state.settings.verify_email and not user["email_verified_at"]:
        raise HTTPException(401, "Please confirm your email, then sign in.")
    # An admin viewing the app as this user may look but never change anything.
    if user.get("impersonator_id") and request.method not in ("GET", "HEAD") and request.url.path not in VIEWING_ALLOWED:
        raise HTTPException(403, "You're viewing as another user, so changes are switched off. Stop viewing to make changes.")
    return user


VIEWING_ALLOWED = {"/api/auth/stop-viewing", "/api/auth/logout"}


def is_admin(request: Request, user: dict) -> bool:
    """Listed in CHESSCOACH_ADMIN_EMAILS *and* has confirmed that address, so nobody can sign up as the admin."""
    if not user.get("email_verified_at") or user.get("impersonator_id"):
        return False
    email = user["email"].lower()
    if email in request.app.state.settings.admin_emails:
        return True
    return request.app.state.db.one("SELECT 1 FROM admins WHERE email = ?", (email,)) is not None


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if not is_admin(request, user):
        raise HTTPException(404, "Not found.")  # don't advertise that an admin area exists
    return user


def my_player(request: Request, user: dict) -> dict:
    """The student this account belongs to (one per account), created on first use."""
    db = get_db(request)
    row = db.one("SELECT * FROM players WHERE user_id = ? ORDER BY id LIMIT 1", (user["id"],))
    if row is None:
        pid = db.run(
            "INSERT INTO players(user_id, name, rating_system, created_at) VALUES (?,?,?,?)",
            (user["id"], user["display_name"], "USCF", time.time()),
        )
        row = db.one("SELECT * FROM players WHERE id = ?", (pid,))
    return row


def owned_player(request: Request, user: dict, player_id: int) -> dict:
    """The player if it belongs to this account, else 404 (never reveal other accounts' data)."""
    row = get_db(request).one("SELECT * FROM players WHERE id = ? AND user_id = ?", (player_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Player not found.")
    return row


def owned_game(request: Request, user: dict, game_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Game not found.")
    return row

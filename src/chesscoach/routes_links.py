"""Private share links: a game anyone with the link can replay, without an account. The owner can turn a link off."""

from __future__ import annotations

import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .deps import get_db, require_user

router = APIRouter(prefix="/api")


class LinkIn(BaseModel):
    show_opponent: bool = False


def _owned_game(request: Request, user: dict, game_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Game not found.")
    return row


def _out(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {"token": row["token"], "path": f"/#/g/{row['token']}", "show_opponent": bool(row["show_opponent"]),
            "views": row["views"], "created_at": row["created_at"]}


@router.get("/games/{game_id}/link")
def get_link(game_id: int, request: Request) -> dict:
    user = require_user(request)
    _owned_game(request, user, game_id)
    return {"link": _out(get_db(request).one("SELECT * FROM game_links WHERE game_id = ?", (game_id,)))}


@router.post("/games/{game_id}/link")
def make_link(game_id: int, body: LinkIn, request: Request) -> dict:
    """Create the game's link (or update whether it shows the opponent). The same link is kept until it's turned off."""
    user = require_user(request)
    game = _owned_game(request, user, game_id)
    if game["status"] != "done":
        raise HTTPException(400, "The game can be shared once its analysis has finished.")
    db = get_db(request)
    if db.one("SELECT 1 FROM game_links WHERE game_id = ?", (game_id,)):
        db.run("UPDATE game_links SET show_opponent = ? WHERE game_id = ?", (int(body.show_opponent), game_id))
    else:
        db.run("INSERT INTO game_links(token, user_id, game_id, show_opponent, views, created_at) VALUES (?,?,?,?,?,?)",
               (secrets.token_urlsafe(12), user["id"], game_id, int(body.show_opponent), 0, time.time()))
    return {"link": _out(db.one("SELECT * FROM game_links WHERE game_id = ?", (game_id,)))}


@router.delete("/games/{game_id}/link")
def remove_link(game_id: int, request: Request) -> dict:
    """Turn the link off: anyone who has it sees "not available" from now on."""
    user = require_user(request)
    _owned_game(request, user, game_id)
    get_db(request).run("DELETE FROM game_links WHERE game_id = ? AND user_id = ?", (game_id, user["id"]))
    return {"link": None}


@router.get("/public/games/{token}")
def public_game(token: str, request: Request) -> JSONResponse:
    """The shared game for anyone with the link: moves, analysis and the coach's notes. No sign-in, no emails."""
    db = get_db(request)
    link = db.one("SELECT * FROM game_links WHERE token = ?", (token[:40],))
    game = db.one("SELECT * FROM games WHERE id = ?", (link["game_id"],)) if link else None
    if game is None:
        raise HTTPException(404, "This link isn't available. The owner may have turned it off.")
    owner = db.one("SELECT display_name FROM users WHERE id = ?", (link["user_id"],))
    db.run("UPDATE game_links SET views = views + 1 WHERE token = ?", (link["token"],))
    analysis = json.loads(game["analysis"] or "{}")
    me = owner["display_name"] if owner else "A player"
    other = (game["opponent"] or (game["black"] if game["color"] == "white" else game["white"])) if link["show_opponent"] else "Opponent"
    white, black = (me, other) if game["color"] == "white" else (other, me)
    body = {
        "author": me, "white": white, "black": black, "color": game["color"], "result": game["result"],
        "event": game["event"] if link["show_opponent"] else "", "opening": game["opening_name"], "eco": game["opening_eco"],
        "accuracy": game["accuracy"], "plies": game["plies"],
        "start_fen": analysis.get("start_fen"),
        "moves": [{"san": m["san"], "uci": m["uci"], "fen": m["fen"]} for m in analysis.get("moves", [])],
        "timeline": analysis.get("timeline", []), "commentary": analysis.get("commentary", []),
        "counts": analysis.get("counts", {}), "headline": (analysis.get("summary") or {}).get("headline", ""),
    }
    return JSONResponse(body, headers={"X-Robots-Tag": "noindex, nofollow"})

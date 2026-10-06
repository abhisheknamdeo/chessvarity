"""Learning content: opening library, repertoire, attack academy and model games."""

from __future__ import annotations

import datetime
import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import academy
from .deps import get_db, my_player, require_user
from .openings import book

router = APIRouter(prefix="/api/library")


@router.get("/openings/families")
def families(request: Request) -> list[dict]:
    require_user(request)
    return book().families()


@router.get("/openings/browse")
def browse(request: Request, moves: str = "") -> dict:
    """Walk the opening tree. `moves` is a comma-separated SAN list, e.g. e4,e5,Nf3."""
    require_user(request)
    sans = [m for m in moves.split(",") if m]
    if len(sans) > 40:
        raise HTTPException(400, "That line is too long.")
    result = book().browse(sans)
    if result is None:
        raise HTTPException(404, "That line is not in the opening library.")
    return result


@router.get("/openings/search")
def search(request: Request, q: str = "") -> list[dict]:
    require_user(request)
    return book().search(q)


@router.get("/repertoire")
def repertoire(request: Request) -> list[dict]:
    require_user(request)
    return academy.repertoire()


@router.get("/academy/themes")
def themes(request: Request) -> list[dict]:
    require_user(request)
    return [
        {"id": tid, **info, "count": len(academy.puzzles(tid))}
        for tid, info in academy.THEMES.items()
    ]


@router.get("/academy/daily")
def daily(request: Request) -> dict:
    require_user(request)
    return academy.daily_puzzle(datetime.date.today().isoformat())


@router.get("/academy/puzzles")
def puzzles(request: Request, theme: str = "") -> list[dict]:
    require_user(request)
    return academy.puzzles(theme or None)


@router.get("/model-games/bands")
def model_bands(request: Request) -> list[dict]:
    require_user(request)
    return academy.model_bands()


def _plies_by_id() -> dict[str, int]:
    return {g["id"]: g["plies"] for g in academy.model_index()}


def review_state(seen: list[int], total: int) -> dict:
    """How much of a model game has been stepped through, one move at a time."""
    count = len({p for p in seen if 1 <= p <= total})
    status = "completed" if total and count >= total else "in_progress" if count else "new"
    return {"seen": count, "total": total, "percent": round(100 * count / total) if total else 0, "status": status}


def _progress(request: Request, user: dict) -> dict[str, dict]:
    """Review progress for every model game this student has opened."""
    player = my_player(request, user)
    totals = _plies_by_id()
    rows = get_db(request).all("SELECT game_id, seen FROM model_progress WHERE player_id = ?", (player["id"],))
    return {r["game_id"]: review_state(json.loads(r["seen"]), totals.get(r["game_id"], 0)) for r in rows if r["game_id"] in totals}


@router.get("/model-games")
def model_games(request: Request, band: str = "", q: str = "", status: str = "", limit: int = Query(24, ge=1, le=100),
                offset: int = Query(0, ge=0)) -> dict:
    """The model-games library, filtered by rating band, text and review status, one page at a time."""
    user = require_user(request)
    progress = _progress(request, user)
    untouched = {"seen": 0, "percent": 0, "status": "new"}
    items = [{**g, "review": progress.get(g["id"], {**untouched, "total": g["plies"]})} for g in academy.model_index()]
    if band:
        items = [g for g in items if g["band"] == band]
    if status in ("new", "in_progress", "completed"):
        items = [g for g in items if g["review"]["status"] == status]
    needle = q.strip().lower()
    if needle:
        items = [g for g in items if needle in " ".join([g["title"], g["opening"], g["white"], g["black"], " ".join(g["themes"])]).lower()]
    everyone = progress.values()
    return {"total": len(items), "games": items[offset: offset + limit],
            "summary": {"completed": sum(1 for p in everyone if p["status"] == "completed"),
                        "in_progress": sum(1 for p in everyone if p["status"] == "in_progress")}}


class Seen(BaseModel):
    plies: list[int] = Field(default_factory=list, max_length=400)


@router.get("/model-games/{game_id}/review")
def model_review(game_id: str, request: Request) -> dict:
    """Which moves of this game the student has stepped through so far."""
    user = require_user(request)
    total = _plies_by_id().get(game_id)
    if total is None:
        raise HTTPException(404, "Game not found.")
    row = get_db(request).one("SELECT seen FROM model_progress WHERE player_id = ? AND game_id = ?", (my_player(request, user)["id"], game_id))
    seen = sorted({p for p in json.loads(row["seen"]) if 1 <= p <= total}) if row else []
    return {**review_state(seen, total), "plies": seen}


@router.post("/model-games/{game_id}/review")
def mark_reviewed(game_id: str, body: Seen, request: Request) -> dict:
    """Record moves the student has looked at. Moves are only ever added, and only real move numbers count."""
    user = require_user(request)
    total = _plies_by_id().get(game_id)
    if total is None:
        raise HTTPException(404, "Game not found.")
    db, player = get_db(request), my_player(request, user)
    row = db.one("SELECT seen FROM model_progress WHERE player_id = ? AND game_id = ?", (player["id"], game_id))
    seen = sorted({p for p in (json.loads(row["seen"]) if row else []) + body.plies if 1 <= p <= total})
    db.run("INSERT INTO model_progress(player_id, game_id, seen, updated_at) VALUES (?,?,?,?) "
           "ON CONFLICT(player_id, game_id) DO UPDATE SET seen = excluded.seen, updated_at = excluded.updated_at",
           (player["id"], game_id, json.dumps(seen), time.time()))
    return {**review_state(seen, total), "plies": seen}


@router.delete("/model-games/{game_id}/review")
def reset_review(game_id: str, request: Request) -> dict:
    user = require_user(request)
    if game_id not in _plies_by_id():
        raise HTTPException(404, "Game not found.")
    get_db(request).run("DELETE FROM model_progress WHERE player_id = ? AND game_id = ?", (my_player(request, user)["id"], game_id))
    return {**review_state([], _plies_by_id()[game_id]), "plies": []}


@router.get("/model-games/{game_id}")
def model_game(game_id: str, request: Request) -> dict:
    require_user(request)
    game = academy.model_detail(game_id)
    if game is None:
        raise HTTPException(404, "Game not found.")
    return game

"""The Chess Development Roadmap: the player's level, priorities from their games, and topic progress."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import insights, roadmap, uscf
from .deps import get_db, owned_player, require_user

router = APIRouter(prefix="/api")


class StatusIn(BaseModel):
    status: Literal["not_started", "learning", "practicing", "developing", "mastered"]


@router.get("/players/{player_id}/roadmap")
def get_roadmap(player_id: int, request: Request, band: int | None = None) -> dict:
    """The roadmap at the player's own level, or at `band` (0-8) to look at another level."""
    user = require_user(request)
    player = owned_player(request, user, player_id)
    db = get_db(request)
    player = uscf.ensure_member(db, player, request.app.state.uscf_factory)     # a saved USCF ID supplies the rating
    games = insights.analysed_games(db, user["id"], player_id)
    statuses = {r["topic"]: r["status"] for r in db.all("SELECT topic, status FROM roadmap_progress WHERE player_id = ?", (player_id,))}
    return roadmap.build(player["rating"], player["rating_system"], band, insights.habits(games), statuses, len(games))


@router.put("/players/{player_id}/roadmap/topics/{topic}")
def set_topic(player_id: int, topic: str, body: StatusIn, request: Request) -> dict:
    """Mark a topic's progress. Progress is kept when the player moves to another level."""
    user = require_user(request)
    owned_player(request, user, player_id)
    if topic not in roadmap.TOPIC:
        raise HTTPException(404, "Unknown topic.")
    db = get_db(request)
    if body.status == "not_started":
        db.run("DELETE FROM roadmap_progress WHERE player_id = ? AND topic = ?", (player_id, topic))
    elif db.run("UPDATE roadmap_progress SET status = ?, updated_at = ? WHERE player_id = ? AND topic = ?",
                (body.status, time.time(), player_id, topic)) == 0:
        db.run("INSERT INTO roadmap_progress(player_id, topic, status, updated_at) VALUES (?,?,?,?)",
               (player_id, topic, body.status, time.time()))
    return {"topic": topic, "status": body.status}

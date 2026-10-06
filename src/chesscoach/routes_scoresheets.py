"""Photos of paper scoresheets (the notation sheet), kept with a tournament round or a game so the paper can't get lost."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from pydantic import BaseModel, Field

from .deps import get_db, my_player, require_user

log = logging.getLogger("chesscoach.scoresheets")
router = APIRouter(prefix="/api")

MAX_BYTES = 8 * 1024 * 1024
PER_ITEM = 6
# Sniff the file itself rather than trusting the name or the browser's label.
KINDS = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG\r\n\x1a\n": ("image/png", "png")}


def _kind(data: bytes) -> tuple[str, str] | None:
    for magic, kind in KINDS.items():
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def _out(rows) -> list[dict]:
    return [{"id": r["id"], "bytes": r["bytes"], "created_at": r["created_at"]} for r in rows]


def sheets_for_rounds(db, round_ids: list[int]) -> dict[int, list[dict]]:
    """{round id: [{id, bytes}]}, for showing counts and thumbnails next to each round."""
    out: dict[int, list[dict]] = {}
    if round_ids:
        marks = ",".join("?" * len(round_ids))
        for r in db.all(f"SELECT id, round_id, bytes, created_at FROM scoresheets WHERE round_id IN ({marks}) ORDER BY id", tuple(round_ids)):
            out.setdefault(r["round_id"], []).append({"id": r["id"], "bytes": r["bytes"], "created_at": r["created_at"]})
    return out


def sheets_for_game(db, game_id: int) -> list[dict]:
    """The game's own photos, and those of the tournament round it belongs to."""
    return _out(db.all(
        "SELECT id, bytes, created_at FROM scoresheets WHERE game_id = ? "
        "OR round_id IN (SELECT id FROM event_games WHERE game_id = ?) ORDER BY id", (game_id, game_id)))


def sheets_for_notation(db, notation_id: int) -> list[dict]:
    return _out(db.all("SELECT id, bytes, created_at FROM scoresheets WHERE notation_id = ? ORDER BY id", (notation_id,)))


def delete_stored(request: Request, where: str, params: tuple) -> None:
    """Remove the stored images for the scoresheet rows matching `where` (before the rows themselves go)."""
    storage = request.app.state.storage
    for row in get_db(request).all(f"SELECT storage_key FROM scoresheets WHERE {where}", params):
        try:
            storage.delete(row["storage_key"])
        except Exception:  # a missing object must not block deleting the round, game or account
            log.exception("could not delete %s", row["storage_key"])


def _store(request: Request, user: dict, data: bytes, column: str, target_id: int) -> None:
    db = get_db(request)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "That photo is too big (the limit is 8 MB).")
    kind = _kind(data)
    if not kind:
        raise HTTPException(400, "Please upload a photo (JPEG, PNG or WebP).")
    if db.one(f"SELECT COUNT(*) n FROM scoresheets WHERE {column} = ?", (target_id,))["n"] >= PER_ITEM:
        raise HTTPException(400, f"Up to {PER_ITEM} photos can be kept here. Delete one to add another.")
    content_type, ext = kind
    key = f"scoresheets/{user['id']}/{uuid.uuid4().hex}.{ext}"
    request.app.state.storage.put(key, data, content_type)
    db.run(f"INSERT INTO scoresheets(user_id, {column}, storage_key, content_type, bytes, created_at) VALUES (?,?,?,?,?,?)",
           (user["id"], target_id, key, content_type, len(data), time.time()))


@router.post("/rounds/{round_id}/scoresheets")
async def upload_for_round(round_id: int, request: Request) -> dict:
    body = await request.body()

    def save() -> dict:
        user = require_user(request)
        db = get_db(request)
        if not db.one("SELECT 1 FROM event_games WHERE id = ? AND user_id = ?", (round_id, user["id"])):
            raise HTTPException(404, "Round not found.")
        _store(request, user, body, "round_id", round_id)
        return {"sheets": sheets_for_rounds(db, [round_id]).get(round_id, [])}

    return await run_in_threadpool(save)


@router.post("/games/{game_id}/scoresheets")
async def upload_for_game(game_id: int, request: Request) -> dict:
    body = await request.body()

    def save() -> dict:
        user = require_user(request)
        db = get_db(request)
        if not db.one("SELECT 1 FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"])):
            raise HTTPException(404, "Game not found.")
        _store(request, user, body, "game_id", game_id)
        return {"sheets": sheets_for_game(db, game_id)}

    return await run_in_threadpool(save)


class NotationIn(BaseModel):
    title: str = Field(default="", max_length=100)
    played_on: str = Field(default="", max_length=10)


def _notation_out(db, row: dict) -> dict:
    return {"id": row["id"], "title": row["title"], "played_on": row["played_on"], "created_at": row["created_at"],
            "sheets": sheets_for_notation(db, row["id"])}


def owned_notation(request: Request, user: dict, notation_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM notations WHERE id = ? AND user_id = ?", (notation_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Saved notation not found.")
    return row


@router.get("/notations")
def list_notations(request: Request) -> list[dict]:
    """Scoresheets saved for later: photos waiting for their moves to be entered."""
    user = require_user(request)
    db = get_db(request)
    player = my_player(request, user)
    return [_notation_out(db, r) for r in db.all("SELECT * FROM notations WHERE player_id = ? ORDER BY created_at DESC, id DESC", (player["id"],))]


@router.post("/notations")
def create_notation(body: NotationIn, request: Request) -> dict:
    user = require_user(request)
    db = get_db(request)
    player = my_player(request, user)
    if db.one("SELECT COUNT(*) n FROM notations WHERE player_id = ?", (player["id"],))["n"] >= 50:
        raise HTTPException(400, "You have 50 scoresheets waiting. Enter the moves for some of them first.")
    nid = db.run("INSERT INTO notations(user_id, player_id, title, played_on, created_at) VALUES (?,?,?,?,?)",
                 (user["id"], player["id"], body.title.strip(), body.played_on.strip(), time.time()))
    return _notation_out(db, db.one("SELECT * FROM notations WHERE id = ?", (nid,)))


@router.patch("/notations/{notation_id}")
def edit_notation(notation_id: int, body: NotationIn, request: Request) -> dict:
    user = require_user(request)
    owned_notation(request, user, notation_id)
    db = get_db(request)
    db.run("UPDATE notations SET title = ?, played_on = ? WHERE id = ?", (body.title.strip(), body.played_on.strip(), notation_id))
    return _notation_out(db, db.one("SELECT * FROM notations WHERE id = ?", (notation_id,)))


@router.delete("/notations/{notation_id}")
def delete_notation(notation_id: int, request: Request) -> dict:
    """Throw away a saved scoresheet and its photos."""
    user = require_user(request)
    owned_notation(request, user, notation_id)
    db = get_db(request)
    delete_stored(request, "notation_id = ?", (notation_id,))
    db.run("DELETE FROM scoresheets WHERE notation_id = ?", (notation_id,))
    db.run("DELETE FROM notations WHERE id = ?", (notation_id,))
    return {"ok": True}


@router.post("/notations/{notation_id}/scoresheets")
async def upload_for_notation(notation_id: int, request: Request) -> dict:
    body = await request.body()

    def save() -> dict:
        user = require_user(request)
        owned_notation(request, user, notation_id)
        _store(request, user, body, "notation_id", notation_id)
        return {"sheets": sheets_for_notation(get_db(request), notation_id)}

    return await run_in_threadpool(save)


def attach_notation(db, user_id: int, notation_id: int, game_id: int) -> int:
    """The game for a saved scoresheet was added: its photos move to the game. Returns how many moved."""
    if not db.one("SELECT 1 FROM notations WHERE id = ? AND user_id = ?", (notation_id, user_id)):
        return 0
    moved = db.run("UPDATE scoresheets SET game_id = ?, notation_id = NULL WHERE notation_id = ? AND user_id = ?",
                   (game_id, notation_id, user_id))
    db.run("DELETE FROM notations WHERE id = ?", (notation_id,))
    return moved


@router.get("/games/{game_id}/scoresheets")
def list_for_game(game_id: int, request: Request) -> dict:
    user = require_user(request)
    db = get_db(request)
    if not db.one("SELECT 1 FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"])):
        raise HTTPException(404, "Game not found.")
    return {"sheets": sheets_for_game(db, game_id)}


@router.get("/scoresheets/{sheet_id}")
def view(sheet_id: int, request: Request) -> Response:
    user = require_user(request)
    row = get_db(request).one("SELECT * FROM scoresheets WHERE id = ? AND user_id = ?", (sheet_id, user["id"]))
    data = request.app.state.storage.get(row["storage_key"]) if row else None
    if data is None:
        raise HTTPException(404, "Photo not found.")
    return Response(data, media_type=row["content_type"], headers={
        "Cache-Control": "private, max-age=86400", "Content-Disposition": f'inline; filename="scoresheet-{sheet_id}.{row["storage_key"].rsplit(".", 1)[-1]}"'})


@router.delete("/scoresheets/{sheet_id}")
def remove(sheet_id: int, request: Request, game: int | None = None) -> dict:
    """Delete one photo. With ?game=<id> the answer lists that game's photos (the game page), else the photo's round's."""
    user = require_user(request)
    db = get_db(request)
    row = db.one("SELECT * FROM scoresheets WHERE id = ? AND user_id = ?", (sheet_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Photo not found.")
    delete_stored(request, "id = ?", (sheet_id,))
    db.run("DELETE FROM scoresheets WHERE id = ?", (sheet_id,))
    if game is not None:
        return {"ok": True, "sheets": sheets_for_game(db, game)}
    if row.get("notation_id"):
        return {"ok": True, "sheets": sheets_for_notation(db, row["notation_id"])}
    if row["round_id"]:
        return {"ok": True, "sheets": sheets_for_rounds(db, [row["round_id"]]).get(row["round_id"], [])}
    return {"ok": True, "sheets": sheets_for_game(db, row["game_id"])}

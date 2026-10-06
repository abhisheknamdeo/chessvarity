"""Adding games, organizing them (months, tournaments, folders), editing and deleting them."""

from __future__ import annotations

import json
import re
import time
from typing import Literal

import chess
import chess.pgn
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import pgnio
from .routes_scoresheets import attach_notation, delete_stored
from .deps import get_db, my_player, owned_game, owned_player, require_user

router = APIRouter(prefix="/api")

SUMMARY = (
    "id, player_id, color, white, black, white_elo, black_elo, result, event, round, date, opponent, "
    "opening_eco, opening_name, opening_plies, plies, status, progress, error, accuracy, folder_id, created_at"
)


class GameIn(BaseModel):
    pgn: str = Field(min_length=1, max_length=3_000_000)
    color: Literal["white", "black", "auto"] = "auto"
    event: str = Field(default="", max_length=100)  # the tournament, if any
    round: str = Field(default="", max_length=20)  # the match number
    year: int | None = Field(default=None, ge=1900, le=2200)
    month: int | None = Field(default=None, ge=1, le=12)
    # If the PGN carries its own date, use it. Untick to file the game under the chosen year and month instead.
    prefer_pgn_date: bool = True
    opponent: str = Field(default="", max_length=60)
    result: str = Field(default="", max_length=8)
    folder_id: int | None = None
    event_game_id: int | None = None   # a tournament round to attach this game to
    opponent_rating: int | None = Field(default=None, ge=0, le=3500)
    date: str = Field(default="", max_length=10)       # an exact day, YYYY-MM-DD (instead of year and month)
    analyze: bool = True                                # False: save now, analyze later from the game page
    sides: list[Literal["white", "black", "auto"]] | None = Field(default=None, max_length=500)  # per game, in PGN order
    include: list[int] | None = Field(default=None, max_length=500)   # which games of the PGN to add (0-based)
    notation_id: int | None = None      # a saved scoresheet whose photos move to this game


class PreviewIn(BaseModel):
    pgn: str = Field(min_length=1, max_length=3_000_000)


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class BulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class GameEdit(BaseModel):
    event: str | None = Field(default=None, max_length=100)
    round: str | None = Field(default=None, max_length=20)
    year: int | None = Field(default=None, ge=1900, le=2200)
    month: int | None = Field(default=None, ge=1, le=12)
    opponent: str | None = Field(default=None, max_length=60)
    result: str | None = Field(default=None, max_length=8)
    opponent_rating: int | None = Field(default=None, ge=0, le=3500)   # 0 clears it
    folder_id: int | None = None  # a folder's id to file the game there, or 0 to take it out of any folder


def summary(row: dict) -> dict:
    out = {k: row[k] for k in row if k not in ("pgn", "analysis", "fingerprint", "user_id")}
    out["outcome"] = pgnio.outcome(row["result"], row["color"])
    return out


def my_names(player: dict, user: dict) -> list[str]:
    """Names this player may appear under in a PGN, most specific first."""
    names = [player.get("uscf_name") or "", user.get("display_name") or "", player.get("name") or ""]
    return list(dict.fromkeys(n.strip() for n in names if n and n.strip()))


def _fill_from_round(body: GameIn, r: dict) -> GameIn:
    """A game added for a tournament round starts from what is already known about that round."""
    data = body.model_dump()
    data["event"] = data["event"] or r["event_name"]
    data["round"] = data["round"] or r["round"]
    data["opponent"] = data["opponent"] or r["opponent"]
    if data["color"] == "auto" and r["color"] in ("white", "black"):
        data["color"] = r["color"]
    if not data["result"] and r["result"] and r["color"] in ("white", "black"):
        mine_wins = "1-0" if r["color"] == "white" else "0-1"
        data["result"] = {"win": mine_wins, "loss": "0-1" if r["color"] == "white" else "1-0", "draw": "1/2-1/2"}[r["result"]]
    start = pgnio.parse_date(r["start_date"] or "")
    if start and data["year"] is None and data["month"] is None:
        data["year"], data["month"] = start[0], start[1]
    return GameIn(**data)


@router.post("/games")
def add_games(body: GameIn, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    settings = request.app.state.settings
    if len(body.pgn.encode("utf-8")) > settings.max_pgn_bytes:
        raise HTTPException(413, "That is too much text at once.")
    if body.result and body.result not in pgnio.RESULTS:
        raise HTTPException(400, "Result must be 1-0, 0-1, 1/2-1/2 or *.")
    if body.folder_id is not None and not get_db(request).one(
        "SELECT 1 FROM folders WHERE id = ? AND user_id = ?", (body.folder_id, user["id"])
    ):
        raise HTTPException(404, "Folder not found.")
    round_row = None
    if body.event_game_id is not None:
        round_row = get_db(request).one(
            "SELECT er.*, e.name AS event_name, e.start_date FROM event_games er JOIN events e ON e.id = er.event_id "
            "WHERE er.id = ? AND er.user_id = ?", (body.event_game_id, user["id"]))
        if round_row is None:
            raise HTTPException(404, "Tournament round not found.")
        body = _fill_from_round(body, round_row)
    day = None
    if body.date:
        parts = body.date.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts) or pgnio.parse_date(".".join(parts)) is None:
            raise HTTPException(400, "The date should look like 2026-09-27.")
        body = body.model_copy(update={"year": int(parts[0]), "month": int(parts[1])})
        day = int(parts[2])
    try:
        games = pgnio.split_games(body.pgn, settings.max_games_per_upload)
        sides = body.sides if body.sides and len(body.sides) == len(games) else [body.color] * len(games)
        picked = [i for i in range(len(games)) if body.include is None or i in body.include]
        if not picked:
            raise ValueError("Choose at least one game to add.")
        games, sides = [games[i] for i in picked], [sides[i] for i in picked]
        colors = [pgnio.resolve_color(g, my_names(player, user), side) for g, side in zip(games, sides)]
    except ValueError as err:
        raise HTTPException(400, str(err))

    db = get_db(request)
    added, skipped = [], []
    for game, color in zip(games, colors):
        pgnio.prepare(
            game, player_name=player["name"], color=color, event=body.event.strip(), round_=body.round.strip(),
            year=body.year, month=body.month, prefer_pgn_date=body.prefer_pgn_date,
            opponent=body.opponent.strip(), result=body.result, override=len(games) == 1,
            opponent_rating=body.opponent_rating, day=day,
        )
        fields = pgnio.describe(game, color)
        fp = pgnio.fingerprint(game, color)
        if db.one("SELECT 1 FROM games WHERE player_id = ? AND fingerprint = ?", (player["id"], fp)):
            skipped.append(f"{fields['white']} vs {fields['black']}: already added")
            continue
        columns = {
            "user_id": user["id"], "player_id": player["id"], "color": "white" if color == chess.WHITE else "black",
            "pgn": pgnio.export(game), "fingerprint": fp, "status": "queued" if body.analyze else "saved", "created_at": time.time(),
            "folder_id": body.folder_id, **fields,
        }
        gid = db.run(
            f"INSERT INTO games({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            tuple(columns.values()),
        )
        if round_row is not None and not added:
            db.run("UPDATE event_games SET game_id = NULL WHERE game_id = ?", (gid,))
            db.run("UPDATE event_games SET game_id = ? WHERE id = ?", (gid, round_row["id"]))
        if body.analyze:
            request.app.state.worker.submit(gid)
        added.append(summary(db.one(f"SELECT {SUMMARY} FROM games WHERE id = ?", (gid,))))
    if body.notation_id and len(added) == 1:
        attach_notation(db, user["id"], body.notation_id, added[0]["id"])
    return {"games": added, "skipped": skipped}


def _words(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 1}


def _event_match(name: str, events: list[dict]) -> dict | None:
    """The player's tournament that best matches a PGN's Event header, if any is close enough."""
    wanted = _words(name)
    if not wanted:
        return None
    best, best_score = None, 0.0
    for e in events:
        have = _words(e["name"])
        if not have:
            continue
        score = len(have & wanted) / len(have | wanted)
        if name.strip().lower() in e["name"].lower() or e["name"].lower() in name.strip().lower():
            score = max(score, 0.8)
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 0.5 else None


@router.post("/games/preview")
def preview_games(body: PreviewIn, request: Request) -> dict:
    """Read a PGN without saving anything: who played, the result, date, event and round, and which side is you.
    Also suggests the player's own tournament (and open round) the game seems to belong to."""
    user = require_user(request)
    player = my_player(request, user)
    settings = request.app.state.settings
    if len(body.pgn.encode("utf-8")) > settings.max_pgn_bytes:
        return {"ok": False, "error": "That is too much text at once.", "hint": "Try fewer games in one go."}
    try:
        games = pgnio.split_games(body.pgn, settings.max_games_per_upload)
    except ValueError as err:
        message = str(err)
        hint = ""
        if message.startswith("Could not read the moves after"):
            hint = message.split(":")[0].replace("Could not read the moves after", "The moves stop making sense after") + "."
        elif message.startswith("That is more than"):
            hint = message
        return {"ok": False, "error": "We couldn't read this game.", "hint": hint}
    db = get_db(request)
    names = my_names(player, user)
    events = db.all("SELECT id, name, start_date FROM events WHERE player_id = ?", (player["id"],))
    open_rounds = db.all("SELECT id, event_id, round, opponent FROM event_games WHERE player_id = ? AND game_id IS NULL",
                         (player["id"],))
    out = []
    for i, game in enumerate(games):
        h = game.headers
        side = pgnio.find_side(game, names)
        fields = pgnio.describe(game, side if side is not None else chess.WHITE)
        own = pgnio.parse_date(h.get("Date", ""))

        def known(key: str) -> str:
            return "" if h.get(key, "?") in pgnio.UNKNOWN else h.get(key, "")

        item = {
            "index": i, "white": known("White"), "black": known("Black"),
            "white_elo": fields["white_elo"] if fields["white_elo"].isdigit() else "",
            "black_elo": fields["black_elo"] if fields["black_elo"].isdigit() else "",
            "result": fields["result"], "event": fields["event"], "round": fields["round"], "site": known("Site"),
            "date": f"{own[0]:04d}-{own[1]:02d}-{own[2]:02d}" if own and own[2] else "",
            "month": f"{own[0]:04d}-{own[1]:02d}" if own else "",
            "opening_eco": fields["opening_eco"], "opening_name": fields["opening_name"],
            "plies": fields["plies"], "moves": (fields["plies"] + 1) // 2,
            "side": None if side is None else ("white" if side == chess.WHITE else "black"),
            "final_fen": game.end().board().fen(),
            "duplicate": side is not None and db.one("SELECT id FROM games WHERE player_id = ? AND fingerprint = ?",
                                                     (player["id"], pgnio.fingerprint(game, side))) is not None,
            "match": None,
        }
        event = _event_match(item["event"], events) if item["event"] else None
        if event:
            rounds = [r for r in open_rounds if r["event_id"] == event["id"]]
            digits = "".join(c for c in item["round"].split(".")[0] if c.isdigit())
            opp = (item["black"] if item["side"] == "white" else item["white"] if item["side"] == "black" else "").lower()
            pick = next((r for r in rounds if digits and r["round"] == digits), None) or next(
                (r for r in rounds if opp and r["opponent"] and _words(r["opponent"]) <= _words(opp)), None)
            item["match"] = {"event_id": event["id"], "name": event["name"], "start_date": event["start_date"],
                             "round_id": pick["id"] if pick else None, "round": pick["round"] if pick else ""}
        out.append(item)
    return {"ok": True, "games": out, "names": names}


def _tally(games: list[dict]) -> dict:
    accs = [g["accuracy"] for g in games if g["accuracy"] is not None]
    return {
        "wins": sum(g["outcome"] == "win" for g in games),
        "draws": sum(g["outcome"] == "draw" for g in games),
        "losses": sum(g["outcome"] == "loss" for g in games),
        "accuracy": round(sum(accs) / len(accs), 1) if accs else None,
    }


def _match_key(match_no: str):
    digits = "".join(ch for ch in match_no if ch.isdigit())
    return (0, int(digits)) if digits else (1, 0)


def build_sections(games: list[dict]) -> list[dict]:
    """Games grouped into monthly sections (newest first); inside a month, tournaments and single games."""
    buckets: dict[str, list[dict]] = {}
    for g in games:
        d = pgnio.parse_date(g["date"])
        buckets.setdefault(f"{d[0]:04d}-{d[1]:02d}" if d else "0000-00", []).append(g)
    out = []
    for key, items in buckets.items():
        year, month = int(key[:4]), int(key[5:])
        events: dict[str, list[dict]] = {}
        for g in sorted(items, key=lambda g: g["id"], reverse=True):
            if g["event"]:
                events.setdefault(g["event"], []).append(g)
        tournaments = [
            {"event": name, "games": sorted(gs, key=lambda g: (_match_key(g["round"]), g["id"])), **_tally(gs)}
            for name, gs in events.items()
        ]
        tournaments.sort(key=lambda t: max(g["id"] for g in t["games"]), reverse=True)
        out.append({
            "key": key, "year": year, "month": month,
            "label": f"{pgnio.MONTHS[month - 1]} {year}" if month else "No date",
            "tournaments": tournaments,
            "loose": sorted((g for g in items if not g["event"]), key=lambda g: (g["date"], g["id"]), reverse=True),
            "games": items, **_tally(items),
        })
    out.sort(key=lambda s: s["key"], reverse=True)
    return out


@router.get("/players/{player_id}/library")
def library(player_id: int, request: Request) -> list[dict]:
    """Every game, filed by month (newest first), with tournaments grouped inside each month."""
    user = require_user(request)
    owned_player(request, user, player_id)
    rows = get_db(request).all(f"SELECT {SUMMARY} FROM games WHERE player_id = ?", (player_id,))
    return build_sections([summary(r) for r in rows])


@router.get("/games/{game_id}")
def get_game(game_id: int, request: Request) -> dict:
    user = require_user(request)
    row = owned_game(request, user, game_id)
    out = summary(row)
    out["pgn"] = row["pgn"]
    out["analysis"] = json.loads(row["analysis"]) if row["analysis"] else None
    return out


@router.get("/games/{game_id}/status")
def game_status(game_id: int, request: Request) -> dict:
    user = require_user(request)
    row = owned_game(request, user, game_id)
    return {k: row[k] for k in ("id", "status", "progress", "error", "accuracy")}


@router.patch("/games/{game_id}")
def edit_game(game_id: int, body: GameEdit, request: Request) -> dict:
    user = require_user(request)
    owned_game(request, user, game_id)
    row = owned_game(request, user, game_id)
    data = body.model_dump()
    changes = {k: data[k].strip() for k in ("event", "round", "opponent", "result") if data[k] is not None}
    if "result" in changes and changes["result"] not in pgnio.RESULTS:
        raise HTTPException(400, "Result must be 1-0, 0-1, 1/2-1/2 or *.")
    if data["opponent_rating"] is not None:
        changes["black_elo" if row["color"] == "white" else "white_elo"] = str(data["opponent_rating"] or "")
    if data["year"] is not None or data["month"] is not None:
        current = pgnio.parse_date(row["date"])
        now = time.localtime()
        year = data["year"] or (current[0] if current else now.tm_year)
        month = data["month"] or (current[1] if current else now.tm_mon)
        if current is None or (year, month) != current[:2]:  # keep the exact day if the month did not change
            changes["date"] = pgnio.make_date(year, month)
    if data["folder_id"] is not None:
        if data["folder_id"] == 0:
            changes["folder_id"] = None
        elif get_db(request).one("SELECT 1 FROM folders WHERE id = ? AND user_id = ?", (data["folder_id"], user["id"])):
            changes["folder_id"] = data["folder_id"]
        else:
            raise HTTPException(404, "Folder not found.")
    if changes:
        get_db(request).run(
            f"UPDATE games SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), game_id)
        )
    return summary(get_db(request).one(f"SELECT {SUMMARY} FROM games WHERE id = ?", (game_id,)))


@router.delete("/games/{game_id}")
def delete_game(game_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_game(request, user, game_id)
    delete_stored(request, "game_id = ?", (game_id,))
    get_db(request).run("DELETE FROM games WHERE id = ?", (game_id,))
    return {"ok": True}


@router.post("/games/{game_id}/reanalyze")
def reanalyze(game_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_game(request, user, game_id)
    get_db(request).run(
        "UPDATE games SET status = 'queued', progress = 0, error = '', analysis = NULL, accuracy = NULL WHERE id = ?",
        (game_id,),
    )
    request.app.state.worker.submit(game_id)
    return {"ok": True}


def owned_folder(request: Request, user: dict, folder_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM folders WHERE id = ? AND user_id = ?", (folder_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Folder not found.")
    return row


@router.get("/players/{player_id}/folders")
def folders(player_id: int, request: Request) -> dict:
    """The player's own folders, each with its games, plus the games not in any folder."""
    user = require_user(request)
    owned_player(request, user, player_id)
    db = get_db(request)
    games = [summary(r) for r in db.all(f"SELECT {SUMMARY} FROM games WHERE player_id = ? ORDER BY id DESC", (player_id,))]
    out = []
    for f in db.all("SELECT id, name FROM folders WHERE player_id = ? ORDER BY name COLLATE NOCASE", (player_id,)):
        mine = [g for g in games if g["folder_id"] == f["id"]]
        out.append({**f, "games": mine, **_tally(mine)})
    return {"folders": out, "unfiled": [g for g in games if g["folder_id"] is None]}


@router.post("/folders")
def create_folder(body: FolderIn, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    name = body.name.strip()
    db = get_db(request)
    if db.one("SELECT 1 FROM folders WHERE player_id = ? AND lower(name) = lower(?)", (player["id"], name)):
        raise HTTPException(409, "You already have a folder with that name.")
    fid = db.run("INSERT INTO folders(user_id, player_id, name, created_at) VALUES (?,?,?,?)",
                 (user["id"], player["id"], name, time.time()))
    return {"id": fid, "name": name}


@router.patch("/folders/{folder_id}")
def rename_folder(folder_id: int, body: FolderIn, request: Request) -> dict:
    user = require_user(request)
    folder = owned_folder(request, user, folder_id)
    name = body.name.strip()
    db = get_db(request)
    if db.one("SELECT 1 FROM folders WHERE player_id = ? AND lower(name) = lower(?) AND id != ?", (folder["player_id"], name, folder_id)):
        raise HTTPException(409, "You already have a folder with that name.")
    db.run("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
    return {"id": folder_id, "name": name}


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, request: Request, games: Literal["keep", "delete"] = "keep") -> dict:
    """Delete a folder. Its games are kept (moved out of the folder) unless `games=delete`."""
    user = require_user(request)
    owned_folder(request, user, folder_id)
    db = get_db(request)
    removed = 0
    if games == "delete":
        delete_stored(request, "game_id IN (SELECT id FROM games WHERE folder_id = ? AND user_id = ?)", (folder_id, user["id"]))
        removed = db.run("DELETE FROM games WHERE folder_id = ? AND user_id = ?", (folder_id, user["id"]))
    db.run("DELETE FROM folders WHERE id = ?", (folder_id,))
    return {"ok": True, "games_deleted": removed}


@router.post("/games/delete")
def delete_games(body: BulkDelete, request: Request) -> dict:
    user = require_user(request)
    marks = ",".join("?" * len(body.ids))
    delete_stored(request, f"game_id IN (SELECT id FROM games WHERE user_id = ? AND id IN ({marks}))", (user["id"], *body.ids))
    removed = get_db(request).run(f"DELETE FROM games WHERE user_id = ? AND id IN ({marks})", (user["id"], *body.ids))
    return {"deleted": removed}


@router.get("/players/{player_id}/export.pgn", response_class=PlainTextResponse)
def export_pgn(player_id: int, request: Request) -> PlainTextResponse:
    user = require_user(request)
    player = owned_player(request, user, player_id)
    rows = get_db(request).all("SELECT pgn FROM games WHERE player_id = ? ORDER BY date, id", (player_id,))
    text = "\n\n".join(r["pgn"].strip() for r in rows) + "\n"
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", player["name"]).strip("_") or "player"
    return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{safe}-games.pgn"'})


@router.get("/legal")
def legal(request: Request, fen: str = chess.STARTING_FEN) -> dict:
    """Legal moves from a position with SAN and resulting FEN: lets the page's board enter games."""
    require_user(request)
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, "That position is not valid.")
    moves = []
    for move in list(board.legal_moves):
        san = board.san(move)
        board.push(move)
        moves.append({"uci": move.uci(), "san": san, "fen": board.fen()})
        board.pop()
    over = board.is_game_over()
    return {"turn": "white" if board.turn == chess.WHITE else "black", "moves": moves, "over": over,
            "result": board.result() if over else None}

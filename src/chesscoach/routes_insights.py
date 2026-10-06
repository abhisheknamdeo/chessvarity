"""Dashboard, habits, missed wins, openings and workbook for a player, plus per-position balance."""

from __future__ import annotations

import io
import json
import time

import chess
import chess.pgn
from fastapi import APIRouter, HTTPException, Query, Request

from . import academy, balance, insights, journey
from .deps import get_db, owned_game, owned_player, require_user

router = APIRouter(prefix="/api")

ATTACKING_REPERTOIRE = {"white": ["italian", "evans", "scotch"], "black": ["two-knights-def", "sicilian-dragon", "kings-indian"]}


def _games(request: Request, player_id: int) -> tuple[dict, list[dict]]:
    user = require_user(request)
    player = owned_player(request, user, player_id)
    return player, insights.analysed_games(get_db(request), user["id"], player_id)


def recommendations(habit_report: dict, opening_report: dict, color_counts: dict) -> list[dict]:
    if not habit_report["ready"]:
        return []
    weak = [h for h in habit_report["habits"] if h["level"] == "work"][:3]
    out = [
        {"kind": "habit", "habit": h["id"], "title": h["headline"], "why": h["detail"],
         "actions": h["advice"][:2], "train": h["train"]}
        for h in weak
    ]
    attack_weak = any(h["id"] in ("attack", "passive") and h["level"] != "strong" for h in habit_report["habits"])
    if attack_weak:
        side = "white" if color_counts.get("white", 0) >= color_counts.get("black", 0) else "black"
        out.append({
            "kind": "repertoire", "title": "Try openings that attack",
            "why": "Openings with open lines and quick development make attacking natural.",
            "actions": ["Play through the suggested lines in the Openings library and try one in your next games."],
            "suggested": ATTACKING_REPERTOIRE[side], "side": side,
        })
    for text in opening_report["advice"]:
        out.append({"kind": "opening", "title": "An opening that is not working", "why": text, "actions": []})
    if not weak:
        out.append({
            "kind": "keep-going", "title": "No big habit problems. Keep going!",
            "why": "Try harder opponents, study the model games, and solve a few Academy puzzles each day.",
            "actions": [],
        })
    return out


@router.get("/players/{player_id}/dashboard")
def dashboard(player_id: int, request: Request) -> dict:
    player, games = _games(request, player_id)
    out = insights.dashboard(games)
    pending = get_db(request).one(
        "SELECT COUNT(*) n FROM games WHERE player_id = ? AND status IN ('queued','analyzing')", (player_id,)
    )["n"]
    failed = get_db(request).one("SELECT COUNT(*) n FROM games WHERE player_id = ? AND status = 'error'", (player_id,))["n"]
    return {**out, "player": {k: player[k] for k in ("id", "name", "rating", "rating_system")},
            "pending": pending, "failed": failed}


@router.get("/players/{player_id}/habits")
def habits(player_id: int, request: Request) -> dict:
    _, games = _games(request, player_id)
    report = insights.habits(games)
    openings = insights.openings(games)
    colors: dict[str, int] = {}
    for g in games:
        colors[g["color"]] = colors.get(g["color"], 0) + 1
    return {**report, "recommendations": recommendations(report, openings, colors)}


@router.get("/players/{player_id}/wins")
def wins(player_id: int, request: Request) -> list[dict]:
    _, games = _games(request, player_id)
    return insights.wins(games)


@router.get("/players/{player_id}/openings")
def openings(player_id: int, request: Request) -> dict:
    _, games = _games(request, player_id)
    return insights.openings(games)


@router.get("/players/{player_id}/workbook")
def workbook(player_id: int, request: Request, skill: str = "") -> list[dict]:
    _, games = _games(request, player_id)
    return insights.workbook(games, skill or None)


@router.get("/players/{player_id}/journey")
def my_journey(player_id: int, request: Request) -> dict:
    """XP, rank, daily streak and badges, worked out from games analyzed and puzzles solved."""
    user = require_user(request)
    owned_player(request, user, player_id)
    db = get_db(request)
    games = []
    for row in db.all("SELECT created_at, status, accuracy, event, plies, analysis FROM games WHERE player_id = ?", (player_id,)):
        blunders = 1
        if row["analysis"]:
            blunders = json.loads(row["analysis"]).get("counts", {}).get("blunders", 1)
        games.append({"created_at": row["created_at"], "status": row["status"], "accuracy": row["accuracy"],
                      "event": row["event"], "plies": row["plies"], "blunders": blunders})
    solved = []
    for row in db.all("SELECT puzzle_id, solved_at FROM puzzle_progress WHERE player_id = ?", (player_id,)):
        puzzle = academy.puzzle_by_id(row["puzzle_id"])
        solved.append({"puzzle_id": row["puzzle_id"], "solved_at": row["solved_at"], "theme": puzzle["theme"] if puzzle else "workbook"})
    return journey.build(games, solved)


@router.get("/players/{player_id}/progress")
def progress(player_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_player(request, user, player_id)
    rows = get_db(request).all("SELECT puzzle_id FROM puzzle_progress WHERE player_id = ?", (player_id,))
    return {"solved": [r["puzzle_id"] for r in rows]}


@router.post("/players/{player_id}/puzzles/{puzzle_id}/solved")
def mark_solved(player_id: int, puzzle_id: str, request: Request) -> dict:
    user = require_user(request)
    owned_player(request, user, player_id)
    if len(puzzle_id) > 80:
        raise HTTPException(400, "Bad puzzle id.")
    get_db(request).run(
        "INSERT OR IGNORE INTO puzzle_progress(user_id, player_id, puzzle_id, solved_at) VALUES (?,?,?,?)",
        (user["id"], player_id, puzzle_id, time.time()),
    )
    return {"ok": True}


@router.get("/games/{game_id}/balance")
def game_balance(game_id: int, request: Request, ply: int = Query(ge=0, le=600)) -> dict:
    """Imbalance reading for the position after `ply` half-moves, from the coached side's view."""
    user = require_user(request)
    row = owned_game(request, user, game_id)
    game = chess.pgn.read_game(io.StringIO(row["pgn"]))
    board = game.board()
    moves = list(game.mainline_moves())
    if ply > len(moves):
        raise HTTPException(400, "That position is past the end of the game.")
    for move in moves[:ply]:
        board.push(move)
    color = chess.WHITE if row["color"] == "white" else chess.BLACK
    wp = None
    if row["analysis"]:
        timeline = json.loads(row["analysis"])["timeline"]
        white_wp = timeline[ply]["wp"]
        wp = white_wp if color == chess.WHITE else 100 - white_wp
    return {"ply": ply, **balance.describe(board, color, wp), "labels": balance.LABELS}

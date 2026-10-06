"""Looking back and planning ahead: the results table, the goal sheet, tournament preparation and the thinking coach."""

from __future__ import annotations

import json
import time
from typing import Literal

import chess
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import goals as goal_lib
from . import insights, prep, stats, thinking
from .deps import get_db, my_player, owned_player, require_user
from .routes_events import _events_for, _date
from .routes_insights import my_journey

router = APIRouter(prefix="/api")


# -- Results table ---------------------------------------------------------------------------------


def _table(request: Request, player_id: int) -> dict:
    db = get_db(request)
    games = db.all("SELECT date, result, color, event, status, accuracy, analysis FROM games WHERE player_id = ?", (player_id,))
    for g in games:
        g["analysis"] = json.loads(g["analysis"]) if g["analysis"] else None
    rounds = db.all(
        "SELECT r.result, r.color, e.start_date FROM event_games r JOIN events e ON e.id = r.event_id "
        "WHERE r.player_id = ? AND r.game_id IS NULL AND r.result != '' AND e.kind != 'upcoming'", (player_id,))
    events = db.all("SELECT kind, start_date, rating_before, rating_after, rating_system FROM events WHERE player_id = ?", (player_id,))
    return stats.build(games, rounds, events)


@router.get("/players/{player_id}/stats")
def results_table(player_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_player(request, user, player_id)
    return _table(request, player_id)


@router.get("/players/{player_id}/stats.csv")
def results_csv(player_id: int, request: Request) -> Response:
    user = require_user(request)
    owned_player(request, user, player_id)
    return Response(stats.to_csv(_table(request, player_id)), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="duke-results.csv"'})


# -- Goals ---------------------------------------------------------------------------------------------


class GoalIn(BaseModel):
    horizon: Literal["short", "long"] = "short"
    title: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=500)
    metric: str = Field(default="", max_length=40)
    target: float | None = Field(default=None, ge=0, le=100000)
    due_date: str = Field(default="", max_length=10)
    steps: list[str] = Field(default_factory=list, max_length=8)


class GoalEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    target: float | None = Field(default=None, ge=0, le=100000)
    due_date: str | None = Field(default=None, max_length=10)
    horizon: Literal["short", "long"] | None = None
    status: Literal["active", "done", "dropped"] | None = None


class StepIn(BaseModel):
    text: str = Field(min_length=1, max_length=160)


class StepEdit(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=160)
    done: bool | None = None


def _values(request: Request, user: dict, player: dict) -> tuple[dict, dict, dict]:
    """(metric values, habit report, opening report) for the goal sheet and its suggestions."""
    games = insights.analysed_games(get_db(request), user["id"], player["id"])
    habit_report = insights.habits(games)
    ratings = json.loads(player["uscf_ratings"]) if player.get("uscf_ratings") else {}
    values = goal_lib.current_values(games, habit_report, my_journey(player["id"], request), ratings, _table(request, player["id"]))
    return values, habit_report, insights.openings(games)


def _goal_out(row: dict, steps: list[dict], values: dict, catalog: dict) -> dict:
    info = catalog.get(row["metric"])
    current = values.get(row["metric"]) if info else None
    measured = goal_lib.progress(info["better"], row["baseline"], row["target"], current) if info else {"percent": None, "reached": False}
    return {
        "id": row["id"], "horizon": row["horizon"], "title": row["title"], "notes": row["notes"], "metric": row["metric"],
        "metric_label": info["label"] if info else "", "unit": info["unit"] if info else "", "better": info["better"] if info else "",
        "baseline": row["baseline"], "target": row["target"], "current": current, "due_date": row["due_date"], "status": row["status"],
        **measured, "steps": [{"id": s["id"], "text": s["text"], "done": bool(s["done"])} for s in steps],
        "steps_done": sum(1 for s in steps if s["done"]),
    }


def _goals_for(request: Request, user: dict, player: dict) -> dict:
    db = get_db(request)
    values, habit_report, _ = _values(request, user, player)
    catalog = goal_lib.metric_catalog()
    rows = db.all("SELECT * FROM goals WHERE player_id = ? ORDER BY created_at, id", (player["id"],))
    steps = db.all("SELECT s.* FROM goal_steps s JOIN goals g ON g.id = s.goal_id WHERE g.player_id = ? ORDER BY s.id", (player["id"],))
    out = [_goal_out(r, [s for s in steps if s["goal_id"] == r["id"]], values, catalog) for r in rows]
    active = {g["metric"] for g in out if g["status"] == "active" and g["metric"]}
    return {
        "goals": out,
        "metrics": [{"id": k, **v, "current": values.get(k)} for k, v in catalog.items()],
        "suggested": goal_lib.suggestions(values, habit_report, active, bool(player.get("uscf_id"))),
    }


def owned_goal(request: Request, user: dict, goal_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Goal not found.")
    return row


def owned_step(request: Request, user: dict, step_id: int) -> dict:
    row = get_db(request).one(
        "SELECT s.* FROM goal_steps s JOIN goals g ON g.id = s.goal_id WHERE s.id = ? AND g.user_id = ?", (step_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Step not found.")
    return row


@router.get("/players/{player_id}/goals")
def list_goals(player_id: int, request: Request) -> dict:
    user = require_user(request)
    return _goals_for(request, user, owned_player(request, user, player_id))


@router.post("/goals")
def create_goal(body: GoalIn, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    catalog = goal_lib.metric_catalog()
    if body.metric and body.metric not in catalog:
        raise HTTPException(400, "Unknown measure for this goal.")
    if body.metric and body.target is None:
        raise HTTPException(400, "Give the goal a target number to measure against.")
    baseline = None
    if body.metric:
        baseline = _values(request, user, player)[0].get(body.metric)
    db = get_db(request)
    gid = db.run(
        "INSERT INTO goals(user_id, player_id, horizon, title, notes, metric, baseline, target, due_date, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user["id"], player["id"], body.horizon, body.title.strip(), body.notes.strip(), body.metric, baseline, body.target,
         _date(body.due_date), "active", time.time()),
    )
    for text in body.steps:
        if text.strip():
            db.run("INSERT INTO goal_steps(goal_id, text) VALUES (?,?)", (gid, text.strip()[:160]))
    return _goals_for(request, user, player)


@router.patch("/goals/{goal_id}")
def edit_goal(goal_id: int, body: GoalEdit, request: Request) -> dict:
    user = require_user(request)
    row = owned_goal(request, user, goal_id)
    changes = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    if "due_date" in changes:
        changes["due_date"] = _date(changes["due_date"])
    if changes.get("status") == "done":
        changes["done_at"] = time.time()
    elif "status" in changes:
        changes["done_at"] = None
    if changes:
        get_db(request).run(f"UPDATE goals SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), goal_id))
    return _goals_for(request, user, owned_player(request, user, row["player_id"]))


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, request: Request) -> dict:
    user = require_user(request)
    row = owned_goal(request, user, goal_id)
    get_db(request).run("DELETE FROM goals WHERE id = ?", (goal_id,))
    return _goals_for(request, user, owned_player(request, user, row["player_id"]))


@router.post("/goals/{goal_id}/steps")
def add_step(goal_id: int, body: StepIn, request: Request) -> dict:
    user = require_user(request)
    row = owned_goal(request, user, goal_id)
    db = get_db(request)
    if db.one("SELECT COUNT(*) n FROM goal_steps WHERE goal_id = ?", (goal_id,))["n"] >= 12:
        raise HTTPException(400, "A goal can have up to 12 steps. Keep it small and doable.")
    db.run("INSERT INTO goal_steps(goal_id, text) VALUES (?,?)", (goal_id, body.text.strip()))
    return _goals_for(request, user, owned_player(request, user, row["player_id"]))


@router.patch("/steps/{step_id}")
def edit_step(step_id: int, body: StepEdit, request: Request) -> dict:
    user = require_user(request)
    step = owned_step(request, user, step_id)
    db = get_db(request)
    if body.text is not None:
        db.run("UPDATE goal_steps SET text = ? WHERE id = ?", (body.text.strip(), step_id))
    if body.done is not None:
        db.run("UPDATE goal_steps SET done = ? WHERE id = ?", (int(body.done), step_id))
    goal = owned_goal(request, user, step["goal_id"])
    return _goals_for(request, user, owned_player(request, user, goal["player_id"]))


@router.delete("/steps/{step_id}")
def delete_step(step_id: int, request: Request) -> dict:
    user = require_user(request)
    step = owned_step(request, user, step_id)
    goal = owned_goal(request, user, step["goal_id"])
    get_db(request).run("DELETE FROM goal_steps WHERE id = ?", (step_id,))
    return _goals_for(request, user, owned_player(request, user, goal["player_id"]))


# -- Tournament preparation ----------------------------------------------------------------------------


def _time_tip(time_control: str) -> str:
    digits = "".join(c if c.isdigit() else " " for c in time_control).split()
    minutes = int(digits[0]) if digits else 0
    if minutes >= 45:
        return f"This is a slow time control ({time_control}). You have time, so use it: run the seven questions on every move that matters."
    if 0 < minutes <= 30:
        return f"This is a quick time control ({time_control}). Play the opening from memory, save time for the sharp moments, and never move without a blunder check."
    return ""


@router.get("/players/{player_id}/prep")
def tournament_prep(player_id: int, request: Request, event_id: int | None = None) -> dict:
    user = require_user(request)
    player = owned_player(request, user, player_id)
    events = _events_for(request, player_id)
    upcoming = [e for e in events if e["kind"] == "upcoming"]
    event = next((e for e in events if e["id"] == event_id), None) if event_id else (upcoming[0] if upcoming else None)
    if event_id and event is None:
        raise HTTPException(404, "Tournament not found.")
    games = insights.analysed_games(get_db(request), user["id"], player_id)
    habit_report, opening_report = insights.habits(games), insights.openings(games)
    days = prep.days_until(event["start_date"]) if event else None
    focus = [{"id": h["id"], "title": h["title"], "headline": h["headline"], "advice": h["advice"][:2]}
             for h in habit_report.get("habits", []) if h["level"] == "work"][:2]
    return {
        "event": ({k: event[k] for k in ("id", "name", "start_date", "location", "time_control", "kind")} if event else None),
        "upcoming": [{"id": e["id"], "name": e["name"], "start_date": e["start_date"]} for e in upcoming],
        "days_until": days,
        "ready": bool(habit_report.get("ready")),
        "white": prep.recommend("white", habit_report, opening_report),
        "black": prep.recommend("black", habit_report, opening_report),
        "focus": focus,
        "time_tip": _time_tip(event["time_control"]) if event else "",
        "schedule": prep.schedule(days),
        "checklist": {"before": prep.BEFORE, "during": prep.DURING, "after": prep.AFTER},
    }


# -- Thinking coach ------------------------------------------------------------------------------------


class Think(BaseModel):
    fen: str = Field(max_length=120)
    last_uci: str | None = Field(default=None, max_length=5)
    color: Literal["white", "black"] | None = None


@router.post("/think")
def think(body: Think, request: Request) -> dict:
    """The seven-question routine answered for a position. It describes the position; it never names the best move."""
    require_user(request)
    try:
        board = chess.Board(body.fen)
    except ValueError:
        raise HTTPException(400, "That position is not valid.")
    if not board.is_valid():
        raise HTTPException(400, "That position is not legal (check the kings and pieces).")
    return thinking.examine(body.fen, body.last_uci, body.color)


@router.get("/think/guide")
def think_guide(request: Request) -> dict:
    require_user(request)
    return thinking.GUIDE


@router.get("/players/{player_id}/think/positions")
def think_positions(player_id: int, request: Request) -> list[dict]:
    """Positions from the student's own games where a mistake happened, to practice the routine on. The answer is not included."""
    user = require_user(request)
    owned_player(request, user, player_id)
    games = insights.analysed_games(get_db(request), user["id"], player_id)
    found = []
    for g in games:
        for m in g["analysis"]["moments"]:
            found.append({
                "id": f"g{g['id']}-{m['ply']}", "game_id": g["id"], "fen": m["fen"], "side": m["side"],
                "last_uci": m["opponent_last"]["uci"] if m.get("opponent_last") else None,
                "opponent": g["opponent"], "event": g["event"], "move_number": m["move_number"], "date": g["date"],
                "importance": m.get("importance", 0),
            })
    found.sort(key=lambda x: -x["importance"])
    return found[:12]

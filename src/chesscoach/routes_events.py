"""Tournaments and their rounds, the USCF connection, and linking games to rounds."""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import pgnio, prep, routes_training, training, uscf
from .deps import get_db, my_player, owned_player, require_user
from .routes_scoresheets import delete_stored, sheets_for_rounds

router = APIRouter(prefix="/api")
_sync_lock = threading.Lock()

Result = Literal["win", "loss", "draw", ""]
Color = Literal["white", "black", ""]


def _date(value: str) -> str:
    """'2026-09-14' (from a date box) or '2026.09.14' to PGN style; empty stays empty."""
    value = (value or "").strip().replace("-", ".")
    if value and not pgnio.parse_date(value):
        raise HTTPException(400, "Dates should look like 2026-09-14.")
    return value


State = Literal["todo", "done", "na"]


class PlanIn(BaseModel):
    """Planning details for a tournament. Every field is optional: only the ones sent are changed."""

    address: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=200)
    entry_fee: str | None = Field(default=None, max_length=30)
    reg_deadline: str | None = Field(default=None, max_length=10)
    attending: Literal["maybe", "going", "skip"] | None = None
    reg_status: State | None = None
    paid_status: State | None = None
    hotel_status: State | None = None
    travel_status: State | None = None
    reg_confirmation: str | None = Field(default=None, max_length=60)
    hotel_name: str | None = Field(default=None, max_length=100)
    hotel_checkin: str | None = Field(default=None, max_length=10)
    hotel_checkout: str | None = Field(default=None, max_length=10)
    hotel_confirmation: str | None = Field(default=None, max_length=60)


PLAN_FIELDS = tuple(PlanIn.model_fields)
PLAN_DATES = ("reg_deadline", "hotel_checkin", "hotel_checkout")


def _plan_changes(body: PlanIn) -> dict:
    """The planning columns to write, checked: dates must be real dates and the website must be an http(s) link."""
    changes = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None and k in PLAN_FIELDS}
    for key in PLAN_DATES:
        if key in changes:
            changes[key] = _date(changes[key])
    site = changes.get("website")
    if site and not site.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The website should start with http:// or https://")
    return changes


class EventIn(PlanIn):
    name: str = Field(min_length=1, max_length=100)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)
    location: str = Field(default="", max_length=60)
    kind: Literal["past", "upcoming"] = "past"
    time_control: str = Field(default="", max_length=30)
    notes: str = Field(default="", max_length=500)
    rounds: int = Field(default=0, ge=0, le=12)   # empty round rows to create, e.g. 5 for a five-round event


class RoundIn(BaseModel):
    round: str = Field(default="", max_length=10)
    opponent: str = Field(default="", max_length=60)
    color: Color = ""
    result: Result = ""


class RoundEdit(BaseModel):
    round: str | None = Field(default=None, max_length=10)
    opponent: str | None = Field(default=None, max_length=60)
    color: Color | None = None
    result: Result | None = None


class UscfId(BaseModel):
    uscf_id: str = Field(default="", max_length=20)


def owned_event(request: Request, user: dict, event_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM events WHERE id = ? AND user_id = ?", (event_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Tournament not found.")
    return row


def owned_round(request: Request, user: dict, round_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM event_games WHERE id = ? AND user_id = ?", (round_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Round not found.")
    return row


def _round_out(r: dict, games: dict[int, dict], sheets: dict[int, list[dict]]) -> dict:
    game = games.get(r["game_id"]) if r["game_id"] else None
    outcome = pgnio.outcome(game["result"], game["color"]) if game else None
    return {
        "id": r["id"], "seq": r["seq"], "round": r["round"], "opponent": r["opponent"], "opponent_uscf_id": r.get("opponent_uscf_id") or "",
        "color": r["color"],
        "result": r["result"] or (outcome or ""), "source": r["source"], "game_id": r["game_id"],
        "game": {"id": game["id"], "status": game["status"], "accuracy": game["accuracy"], "opening": game["opening_name"]} if game else None,
        "scoresheets": sheets.get(r["id"], []),
    }


def _rating_changes(e: dict) -> list[dict]:
    """Every rating this event changed, with the change. Older imports kept only one, so fall back to that."""
    try:
        changes = json.loads(e.get("ratings") or "[]")
    except ValueError:
        changes = []
    if not changes and e.get("rating_before") is not None and e.get("rating_after") is not None:
        system = e.get("rating_system") or ""
        changes = [{"system": "R" if system == "D" else system, "before": e["rating_before"], "after": e["rating_after"]}]   # dual: regular
    return [{**c, "change": c["after"] - c["before"]} for c in changes]


def _events_for(request: Request, player_id: int, event_id: int | None = None) -> list[dict]:
    db = get_db(request)
    where, params = ("player_id = ?", (player_id,)) if event_id is None else ("id = ?", (event_id,))
    events = db.all(f"SELECT * FROM events WHERE {where}", params)
    rounds = db.all("SELECT * FROM event_games WHERE player_id = ? ORDER BY seq, id", (player_id,))
    games = {g["id"]: g for g in db.all("SELECT id, status, accuracy, result, color, opening_name FROM games WHERE player_id = ?", (player_id,))}
    sheets = sheets_for_rounds(db, [r["id"] for r in rounds])
    out = []
    for e in events:
        mine = [_round_out(r, games, sheets) for r in rounds if r["event_id"] == e["id"]]
        results = [r["result"] for r in mine]
        plan = {k: e[k] for k in PLAN_FIELDS}
        wanted = e["kind"] == "upcoming" and plan["attending"] != "skip"
        needs = [label for key, label in (("reg_status", "registration"), ("paid_status", "payment"), ("hotel_status", "hotel"), ("travel_status", "travel"))
                 if wanted and plan[key] == "todo"]
        out.append({
            **{k: e[k] for k in ("id", "name", "start_date", "end_date", "location", "kind", "source", "uscf_event_id",
                                 "section", "rating_system", "rating_before", "rating_after", "time_control", "notes")},
            "plan": plan, "needs": needs, "days_until": prep.days_until(e["start_date"]), "deadline_in": prep.days_until(e["reg_deadline"]),
            "rounds": mine, "ratings": _rating_changes(e),
            "wins": results.count("win"), "draws": results.count("draw"), "losses": results.count("loss"),
            "games_with_moves": sum(1 for r in mine if r["game_id"]),
        })
    # Upcoming first (soonest first), then past events, newest first.
    upcoming = sorted((e for e in out if e["kind"] == "upcoming"), key=lambda e: e["start_date"] or "9999")
    past = sorted((e for e in out if e["kind"] != "upcoming"), key=lambda e: e["start_date"] or "0000", reverse=True)
    return upcoming + past


@router.get("/players/{player_id}/events")
def list_events(player_id: int, request: Request) -> list[dict]:
    user = require_user(request)
    owned_player(request, user, player_id)
    return _events_for(request, player_id)


@router.post("/events")
def create_event(body: EventIn, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    db = get_db(request)
    now = time.time()
    plan = _plan_changes(body)
    eid = db.run(
        "INSERT INTO events(user_id, player_id, name, start_date, end_date, location, kind, source, time_control, notes, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user["id"], player["id"], body.name.strip(), _date(body.start_date), _date(body.end_date), body.location.strip(),
         body.kind, "manual", body.time_control.strip(), body.notes.strip(), now),
    )
    if plan:
        db.run(f"UPDATE events SET {', '.join(f'{k} = ?' for k in plan)} WHERE id = ?", (*plan.values(), eid))
    for n in range(1, body.rounds + 1):
        db.run("INSERT INTO event_games(event_id, user_id, player_id, seq, round, source, created_at) VALUES (?,?,?,?,?,?,?)",
               (eid, user["id"], player["id"], n, str(n), "manual", now))
    return _events_for(request, player["id"], eid)[0]


@router.patch("/events/{event_id}")
def edit_event(event_id: int, body: EventIn, request: Request) -> dict:
    user = require_user(request)
    event = owned_event(request, user, event_id)
    plan = _plan_changes(body)
    get_db(request).run(
        "UPDATE events SET name=?, start_date=?, end_date=?, location=?, kind=?, time_control=?, notes=? WHERE id=?",
        (body.name.strip(), _date(body.start_date), _date(body.end_date), body.location.strip(), body.kind,
         body.time_control.strip(), body.notes.strip(), event_id),
    )
    if plan:
        get_db(request).run(f"UPDATE events SET {', '.join(f'{k} = ?' for k in plan)} WHERE id = ?", (*plan.values(), event_id))
    return _events_for(request, event["player_id"], event_id)[0]


# Getting ready for a tournament. "auto" steps tick themselves from what the player did; the others are ticked by hand.
PREP_STEPS = [
    {"key": "review", "label": "Review your recent games", "href": "#/patterns", "auto": True},
    {"key": "tactics", "label": "Tactical practice", "href": "#/academy", "auto": True},
    {"key": "endgame", "label": "Endgame practice", "href": "#/roadmap", "auto": False},
    {"key": "openings", "label": "Opening preparation", "href": "#/prep", "auto": False},
    {"key": "practice", "label": "Practice games", "href": "#/play", "auto": False},
]


class PrepIn(BaseModel):
    step: Literal["review", "tactics", "endgame", "openings", "practice"]
    done: bool


def _prep_for(db, player_id: int, event: dict) -> dict:
    """The preparation checklist for an upcoming tournament, with a percentage."""
    try:
        ticked = set(json.loads(event.get("prep_done") or "[]"))
    except ValueError:
        ticked = set()
    now = time.time()
    recent_game = db.one("SELECT 1 FROM games WHERE player_id = ? AND status = 'done' AND created_at > ?", (player_id, now - 14 * 86400))
    recent_puzzle = db.one("SELECT 1 FROM puzzle_progress WHERE player_id = ? AND solved_at > ?", (player_id, now - 7 * 86400))
    auto = {"review": bool(recent_game), "tactics": bool(recent_puzzle)}
    steps = []
    for s in PREP_STEPS:
        done = s["key"] in ticked or auto.get(s["key"], False)
        href = f"{s['href']}?event={event['id']}" if s["key"] == "openings" else s["href"]
        steps.append({**s, "href": href, "done": done, "by_hand": s["key"] in ticked})
    return {"steps": steps, "percent": round(100 * sum(s["done"] for s in steps) / len(steps))}


@router.patch("/events/{event_id}/prep")
def tick_prep(event_id: int, body: PrepIn, request: Request) -> dict:
    """Tick (or untick) a preparation step for a tournament."""
    user = require_user(request)
    event = owned_event(request, user, event_id)
    try:
        ticked = set(json.loads(event.get("prep_done") or "[]"))
    except ValueError:
        ticked = set()
    ticked = ticked | {body.step} if body.done else ticked - {body.step}
    db = get_db(request)
    db.run("UPDATE events SET prep_done = ? WHERE id = ?", (json.dumps(sorted(ticked)), event_id))
    return _prep_for(db, event["player_id"], {**event, "prep_done": json.dumps(sorted(ticked))})


@router.patch("/events/{event_id}/plan")
def edit_plan(event_id: int, body: PlanIn, request: Request) -> dict:
    """Update only the planning details (registration, payment, hotel, travel, deadline, where) of a tournament."""
    user = require_user(request)
    event = owned_event(request, user, event_id)
    plan = _plan_changes(body)
    if plan:
        get_db(request).run(f"UPDATE events SET {', '.join(f'{k} = ?' for k in plan)} WHERE id = ?", (*plan.values(), event_id))
    return _events_for(request, event["player_id"], event_id)[0]


def _iso(pgn_date: str) -> str | None:
    """'2026.10.03' -> '2026-10-03', or None when the date has no real day."""
    parsed = pgnio.parse_date(pgn_date or "")
    if not parsed or parsed[2] is None:
        return None
    try:
        return dt.date(*parsed).isoformat()
    except ValueError:
        return None


@router.get("/players/{player_id}/calendar")
def calendar(player_id: int, request: Request, start: str = "", end: str = "") -> dict:
    """Everything with a date: tournaments (over their days), registration deadlines, hotel stays, goal due dates and,
    for the dates asked for (default: the last month and the next four), training sessions."""
    user = require_user(request)
    owned_player(request, user, player_id)
    today = dt.date.today()
    first = training.parse_date(start) or today - dt.timedelta(days=31)
    last = training.parse_date(end) or today + dt.timedelta(days=124)
    if last < first or (last - first).days > training.MAX_RANGE_DAYS:
        raise HTTPException(400, f"Ask for a start and end date at most {training.MAX_RANGE_DAYS} days apart.")
    items, undated = [], 0
    db = get_db(request)
    raw = {r["id"]: r for r in db.all("SELECT id, prep_done FROM events WHERE player_id = ?", (player_id,))}
    for e in _events_for(request, player_id):
        start = _iso(e["start_date"])
        plan = e["plan"]
        if start is None:
            undated += 1
        else:
            end = _iso(e["end_date"]) or start
            items.append({"type": "tournament", "id": e["id"], "title": e["name"], "start": start, "end": max(start, end), "kind": e["kind"],
                          "location": e["location"], "attending": plan["attending"], "needs": e["needs"],
                          "registered": plan["reg_status"] == "done", "hotel": plan["hotel_status"],
                          # For the details drawer.
                          "section": e["section"], "time_control": e["time_control"], "source": e["source"],
                          "statuses": {k: plan[k] for k in ("reg_status", "paid_status", "hotel_status", "travel_status")},
                          "hotel_name": plan["hotel_name"], "reg_deadline": _iso(plan["reg_deadline"]),
                          "rounds": len(e["rounds"]), "games_with_moves": e["games_with_moves"],
                          "wins": e["wins"], "draws": e["draws"], "losses": e["losses"], "ratings": e["ratings"],
                          "prep": _prep_for(db, player_id, {"id": e["id"], "prep_done": raw.get(e["id"], {}).get("prep_done", "")})
                          if e["kind"] == "upcoming" else None})
        if e["kind"] == "upcoming" and plan["attending"] != "skip" and _iso(plan["reg_deadline"]):
            day = _iso(plan["reg_deadline"])
            items.append({"type": "deadline", "id": e["id"], "title": f"Register by: {e['name']}", "start": day, "end": day,
                          "done": plan["reg_status"] == "done", "event_name": e["name"], "event_start": start})
        if _iso(plan["hotel_checkin"]) and _iso(plan["hotel_checkout"]) and plan["hotel_status"] != "na":
            a, b = _iso(plan["hotel_checkin"]), _iso(plan["hotel_checkout"])
            items.append({"type": "hotel", "id": e["id"], "title": f"Hotel: {plan['hotel_name'] or e['name']}", "start": a, "end": max(a, b),
                          "done": plan["hotel_status"] == "done", "event_name": e["name"], "hotel_name": plan["hotel_name"],
                          "confirmation": plan["hotel_confirmation"]})
    goals = db.all("SELECT id, title, notes, due_date FROM goals WHERE player_id = ? AND status = 'active' AND due_date != ''", (player_id,))
    steps = db.all("SELECT s.goal_id, s.done FROM goal_steps s JOIN goals g ON g.id = s.goal_id WHERE g.player_id = ?", (player_id,))
    for g in goals:
        day = _iso(g["due_date"])
        if day:
            mine = [s for s in steps if s["goal_id"] == g["id"]]
            items.append({"type": "goal", "id": g["id"], "title": f"Goal: {g['title']}", "start": day, "end": day, "notes": g["notes"],
                          "steps": len(mine), "steps_done": sum(1 for s in mine if s["done"])})
    for o in routes_training.occurrences_for(request, player_id, first, last):
        items.append({"type": "training", "id": o["series_id"], "title": o["title"], "start": o["date"], "end": o["date"],
                      "time": o["start_time"], "end_time": o["end_time"], "kind": o["kind"], "location": o["location"], "coach": o["coach"],
                      "topic": o["topic"], "notes": o["notes"], "done": o["done"], "skipped": o["skipped"], "recurrence": o["recurrence"]})
    items.sort(key=lambda i: (i["start"], i.get("time") or "", i["type"]))
    return {"items": items, "undated": undated, "today": today.isoformat()}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, request: Request) -> dict:
    """Removes the tournament and its round records. Games with moves are kept."""
    user = require_user(request)
    owned_event(request, user, event_id)
    delete_stored(request, "round_id IN (SELECT id FROM event_games WHERE event_id = ?)", (event_id,))
    get_db(request).run("DELETE FROM events WHERE id = ?", (event_id,))
    return {"ok": True}


@router.post("/events/{event_id}/rounds")
def add_round(event_id: int, body: RoundIn, request: Request) -> dict:
    user = require_user(request)
    event = owned_event(request, user, event_id)
    db = get_db(request)
    seq = (db.one("SELECT COALESCE(MAX(seq), 0) n FROM event_games WHERE event_id = ?", (event_id,))["n"]) + 1
    db.run(
        "INSERT INTO event_games(event_id, user_id, player_id, seq, round, opponent, color, result, source, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_id, user["id"], event["player_id"], seq, body.round.strip() or str(seq), body.opponent.strip(), body.color,
         body.result, "manual", time.time()),
    )
    return _events_for(request, event["player_id"], event_id)[0]


@router.patch("/rounds/{round_id}")
def edit_round(round_id: int, body: RoundEdit, request: Request) -> dict:
    user = require_user(request)
    row = owned_round(request, user, round_id)
    changes = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    if changes:
        get_db(request).run(f"UPDATE event_games SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), round_id))
    return _events_for(request, row["player_id"], row["event_id"])[0]


@router.delete("/rounds/{round_id}")
def delete_round(round_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_round(request, user, round_id)
    delete_stored(request, "round_id = ?", (round_id,))
    get_db(request).run("DELETE FROM event_games WHERE id = ?", (round_id,))
    return {"ok": True}


@router.post("/rounds/{round_id}/link/{game_id}")
def link_game(round_id: int, game_id: int, request: Request) -> dict:
    """Attach a game you already added (with moves) to this round."""
    user = require_user(request)
    row = owned_round(request, user, round_id)
    db = get_db(request)
    if not db.one("SELECT 1 FROM games WHERE id = ? AND user_id = ?", (game_id, user["id"])):
        raise HTTPException(404, "Game not found.")
    db.run("UPDATE event_games SET game_id = NULL WHERE game_id = ? AND id != ?", (game_id, round_id))
    db.run("UPDATE event_games SET game_id = ? WHERE id = ?", (game_id, round_id))
    return _events_for(request, row["player_id"], row["event_id"])[0]


@router.post("/rounds/{round_id}/unlink")
def unlink_game(round_id: int, request: Request) -> dict:
    user = require_user(request)
    row = owned_round(request, user, round_id)
    get_db(request).run("UPDATE event_games SET game_id = NULL WHERE id = ?", (round_id,))
    return _events_for(request, row["player_id"], row["event_id"])[0]


# -- USCF -----------------------------------------------------------------------------------------


def _uscf(request: Request) -> uscf.UscfClient:
    return request.app.state.uscf_factory()


def _uscf_out(player: dict) -> dict:
    return {
        "uscf_id": player.get("uscf_id", ""), "name": player.get("uscf_name", ""),
        "ratings": json.loads(player["uscf_ratings"]) if player.get("uscf_ratings") else {},
        "synced_at": player.get("uscf_synced_at"),
        "player_rating": player.get("rating"), "player_rating_system": player.get("rating_system"),
    }


@router.get("/uscf")
def uscf_status(request: Request) -> dict:
    user = require_user(request)
    return _uscf_out(uscf.ensure_member(get_db(request), my_player(request, user), request.app.state.uscf_factory))


@router.get("/uscf/lookup")
def uscf_lookup(request: Request, id: str = "") -> dict:
    """Who does this USCF ID belong to? (So the right child is confirmed before importing.)"""
    require_user(request)
    valid = uscf.valid_id(id)
    if not valid:
        raise HTTPException(400, "A USCF ID is 8 digits.")
    try:
        return _uscf(request).member(valid)
    except uscf.UscfError as err:
        raise HTTPException(502 if "reach" in str(err) or "busy" in str(err) else 400, str(err))


@router.put("/uscf/id")
def save_uscf_id(body: UscfId, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    db = get_db(request)
    if not body.uscf_id.strip():
        db.run("UPDATE players SET uscf_id = '', uscf_name = '', uscf_ratings = '', uscf_synced_at = NULL WHERE id = ?", (player["id"],))
    else:
        valid = uscf.valid_id(body.uscf_id)
        if not valid:
            raise HTTPException(400, "A USCF ID is 8 digits.")
        if valid != player.get("uscf_id"):
            db.run("UPDATE players SET uscf_id = ?, uscf_name = '', uscf_ratings = '', uscf_synced_at = NULL WHERE id = ?", (valid, player["id"]))
        try:        # fetch the name and rating now, so the rating is used straight away; importing can come later
            uscf.apply_member(db, my_player(request, user), _uscf(request).member(valid))
        except uscf.UscfError:
            pass    # USCF unreachable or no such member: the ID is still saved, and importing will retry
    return _uscf_out(my_player(request, user))


@router.post("/uscf/sync")
def uscf_sync(request: Request) -> dict:
    """Import this player's USCF tournaments and game results (not moves: USCF does not keep them)."""
    user = require_user(request)
    player = my_player(request, user)
    if not _sync_lock.acquire(blocking=False):
        raise HTTPException(409, "An import is already running. Please wait a moment.")
    try:
        summary = uscf.sync(get_db(request), user["id"], player, _uscf(request))
    except uscf.UscfError as err:
        raise HTTPException(502 if "reach" in str(err) or "busy" in str(err) else 400, str(err))
    finally:
        _sync_lock.release()
    return {**summary, "status": _uscf_out(my_player(request, user))}

"""Training sessions: classes, lessons, club nights and practice, and marking each one attended or cancelled."""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import training
from .deps import get_db, my_player, owned_player, require_user

router = APIRouter(prefix="/api")

Kind = Literal["class", "lesson", "club", "practice", "study", "other"]


class TrainingIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    kind: Kind = "class"
    start_date: str = Field(max_length=10)
    start_time: str = Field(default="", max_length=5)
    end_time: str = Field(default="", max_length=5)
    location: str = Field(default="", max_length=120)
    coach: str = Field(default="", max_length=60)
    topic: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)
    recurrence: Literal["none", "weekly", "biweekly", "monthly"] = "none"
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    until: str = Field(default="", max_length=10)


class OccurrenceMark(BaseModel):
    date: str = Field(max_length=10)
    action: Literal["skip", "unskip", "done", "undone"]


def _checked(body: TrainingIn) -> dict:
    """The row to store, after checking dates, times and how it repeats."""
    if training.parse_date(body.start_date) is None:
        raise HTTPException(400, "Give the first date as year-month-day, for example 2026-10-13.")
    for label, value in (("start", body.start_time), ("end", body.end_time)):
        if value and not training.TIME.match(value):
            raise HTTPException(400, f"The {label} time should look like 16:30.")
    if body.end_time and not body.start_time:
        raise HTTPException(400, "Give a start time as well as an end time.")
    if body.start_time and body.end_time and body.end_time <= body.start_time:
        raise HTTPException(400, "The session should end after it starts.")
    if body.until:
        until = training.parse_date(body.until)
        if until is None:
            raise HTTPException(400, "The last date should look like 2026-12-20.")
        if until < training.parse_date(body.start_date):
            raise HTTPException(400, "The repeat should end on or after the first date.")
    if any(d < 0 or d > 6 for d in body.weekdays):
        raise HTTPException(400, "Weekdays are 0 (Monday) to 6 (Sunday).")
    return {
        "title": body.title.strip(), "kind": body.kind, "start_date": body.start_date, "start_time": body.start_time,
        "end_time": body.end_time, "location": body.location.strip(), "coach": body.coach.strip(), "topic": body.topic.strip(),
        "notes": body.notes.strip(), "recurrence": body.recurrence,
        "weekdays": ",".join(str(d) for d in sorted(set(body.weekdays))) if body.recurrence in ("weekly", "biweekly") else "",
        "until": body.until if body.recurrence != "none" else "",
    }


def owned_series(request: Request, user: dict, series_id: int) -> dict:
    row = get_db(request).one("SELECT * FROM training WHERE id = ? AND user_id = ?", (series_id, user["id"]))
    if row is None:
        raise HTTPException(404, "Training session not found.")
    return row


def _window(start: str, end: str) -> tuple[dt.date, dt.date]:
    a, b = training.parse_date(start), training.parse_date(end)
    if a is None or b is None or b < a:
        raise HTTPException(400, "Give a start and end date as year-month-day.")
    if (b - a).days > training.MAX_RANGE_DAYS:
        raise HTTPException(400, f"Ask for at most {training.MAX_RANGE_DAYS} days at a time.")
    return a, b


def occurrences_for(request: Request, player_id: int, start: dt.date, end: dt.date) -> list[dict]:
    rows = get_db(request).all("SELECT * FROM training WHERE player_id = ?", (player_id,))
    items = [o for row in rows for o in training.occurrences(row, start, end)]
    items.sort(key=lambda o: (o["date"], o["start_time"] or "99:99", o["title"]))
    return items


@router.get("/players/{player_id}/training")
def list_training(player_id: int, request: Request) -> dict:
    """Every training series, with how it repeats in words and when it next meets."""
    user = require_user(request)
    owned_player(request, user, player_id)
    rows = get_db(request).all("SELECT * FROM training WHERE player_id = ? ORDER BY start_date, start_time, id", (player_id,))
    return {"series": [training.series_out(r) for r in rows], "kinds": training.KINDS}


@router.get("/players/{player_id}/training/occurrences")
def training_occurrences(player_id: int, request: Request, start: str = "", end: str = "") -> dict:
    """The sessions that fall between two dates, repeats included, each marked attended or cancelled."""
    user = require_user(request)
    owned_player(request, user, player_id)
    a, b = _window(start, end)
    items = occurrences_for(request, player_id, a, b)
    week = [o for o in items if not o["skipped"]]
    rows = {r["id"]: r for r in get_db(request).all("SELECT * FROM training WHERE player_id = ?", (player_id,))}
    minutes = sum(training.minutes(rows[o["series_id"]]) for o in week)
    return {"items": items, "summary": {"sessions": len(week), "attended": sum(1 for o in week if o["done"]), "minutes": minutes}}


@router.post("/training")
def create_training(body: TrainingIn, request: Request) -> dict:
    user = require_user(request)
    player = my_player(request, user)
    row = _checked(body)
    row.update({"user_id": user["id"], "player_id": player["id"], "created_at": time.time()})
    sid = get_db(request).run(f"INSERT INTO training({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))
    return training.series_out(get_db(request).one("SELECT * FROM training WHERE id = ?", (sid,)))


@router.patch("/training/{series_id}")
def edit_training(series_id: int, body: TrainingIn, request: Request) -> dict:
    user = require_user(request)
    owned_series(request, user, series_id)
    row = _checked(body)
    get_db(request).run(f"UPDATE training SET {', '.join(f'{k} = ?' for k in row)} WHERE id = ?", (*row.values(), series_id))
    return training.series_out(get_db(request).one("SELECT * FROM training WHERE id = ?", (series_id,)))


@router.delete("/training/{series_id}")
def delete_training(series_id: int, request: Request) -> dict:
    user = require_user(request)
    owned_series(request, user, series_id)
    get_db(request).run("DELETE FROM training WHERE id = ?", (series_id,))
    return {"ok": True}


@router.post("/training/{series_id}/occurrence")
def mark_occurrence(series_id: int, body: OccurrenceMark, request: Request) -> dict:
    """Cancel one session of a repeating series, bring it back, or mark it attended."""
    user = require_user(request)
    row = owned_series(request, user, series_id)
    day = training.parse_date(body.date)
    if day is None or day not in training.dates_between(row, day, day):
        raise HTTPException(400, "That series does not meet on that date.")
    skips, done = set(json.loads(row["skips"] or "[]")), set(json.loads(row["done"] or "[]"))
    if body.action == "skip":
        skips.add(body.date)
        done.discard(body.date)                    # a cancelled session cannot also be attended
    elif body.action == "unskip":
        skips.discard(body.date)
    elif body.action == "done":
        if body.date in skips:
            raise HTTPException(400, "That session was cancelled. Bring it back first.")
        done.add(body.date)
    else:
        done.discard(body.date)
    get_db(request).run("UPDATE training SET skips = ?, done = ? WHERE id = ?", (json.dumps(sorted(skips)), json.dumps(sorted(done)), series_id))
    return training.series_out(get_db(request).one("SELECT * FROM training WHERE id = ?", (series_id,)))

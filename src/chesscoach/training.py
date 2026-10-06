"""The training schedule: classes, lessons, club nights and practice, one-off or repeating.

A series is stored once (with how it repeats, and the dates that were skipped or attended). Sessions ("occurrences")
are worked out on demand for whatever range of dates a page is showing, so nothing has to be generated in advance.
Dates are ISO ("2026-10-13"), times are 24-hour "HH:MM".
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

KINDS = {
    "class": "Class", "lesson": "Private lesson", "club": "Club night", "practice": "Practice",
    "study": "Home study", "other": "Other",
}
RECURRENCES = ("none", "weekly", "biweekly", "monthly")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MAX_RANGE_DAYS = 400


def parse_date(text: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def weekdays_of(row: dict) -> list[int]:
    days = sorted({int(x) for x in (row.get("weekdays") or "").split(",") if x.strip().isdigit() and 0 <= int(x) <= 6})
    return days or [parse_date(row["start_date"]).weekday()]


def _add_months(date: dt.date, n: int, day: int) -> dt.date:
    month0 = date.month - 1 + n
    year, month = date.year + month0 // 12, month0 % 12 + 1
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def dates_between(row: dict, start: dt.date, end: dt.date) -> list[dt.date]:
    """Every date this series meets on within [start, end]."""
    first = parse_date(row["start_date"])
    last = parse_date(row.get("until") or "")
    if first is None or end < first or (last is not None and start > last):
        return []
    end = min(end, last) if last else end
    kind = row.get("recurrence", "none")
    if kind == "none":
        return [first] if start <= first <= end else []
    found: list[dt.date] = []
    if kind in ("weekly", "biweekly"):
        step = 7 * (1 if kind == "weekly" else 2)
        monday = first - dt.timedelta(days=first.weekday())
        n = max(0, (start - monday).days // step - 1)
        wanted = weekdays_of(row)
        while True:
            week = monday + dt.timedelta(days=n * step)
            if week > end:
                break
            for wd in wanted:
                day = week + dt.timedelta(days=wd)
                if first <= day and start <= day <= end:
                    found.append(day)
            n += 1
    elif kind == "monthly":
        n = max(0, (start.year - first.year) * 12 + start.month - first.month - 1)
        while True:
            day = _add_months(first, n, first.day)
            if day > end:
                break
            if day >= start and day >= first:
                found.append(day)
            n += 1
    return found


def pattern_text(row: dict) -> str:
    """'Every Tue and Thu, 16:30-17:30' in words."""
    when = f"{row['start_time']}-{row['end_time']}" if row["start_time"] and row["end_time"] else row["start_time"] or "all day"
    kind = row.get("recurrence", "none")
    first = parse_date(row["start_date"])
    if kind == "none" or first is None:
        return f"{first.strftime('%a %b')} {first.day}, {when}" if first else when
    if kind == "monthly":
        every = f"Monthly on the {first.day}{'th' if 10 < first.day % 100 < 14 else {1: 'st', 2: 'nd', 3: 'rd'}.get(first.day % 10, 'th')}"
    else:
        names = " and ".join(DAY_NAMES[d] for d in weekdays_of(row))
        every = f"Every {'other ' if kind == 'biweekly' else ''}{names}"
    until = parse_date(row.get("until") or "")
    return f"{every}, {when}" + (f", until {until.strftime('%b')} {until.day}" if until else "")


def occurrences(row: dict, start: dt.date, end: dt.date) -> list[dict]:
    skips, done = set(json.loads(row.get("skips") or "[]")), set(json.loads(row.get("done") or "[]"))
    out = []
    for day in dates_between(row, start, end):
        iso = day.isoformat()
        out.append({
            "series_id": row["id"], "date": iso, "start_time": row["start_time"], "end_time": row["end_time"],
            "title": row["title"], "kind": row["kind"], "location": row["location"], "coach": row["coach"],
            "topic": row["topic"], "notes": row["notes"], "recurrence": row["recurrence"],
            "skipped": iso in skips, "done": iso in done,
        })
    return out


def series_out(row: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    nxt = next((o for o in occurrences(row, today, today + dt.timedelta(days=400)) if not o["skipped"]), None)
    out = {k: row[k] for k in ("id", "title", "kind", "start_date", "start_time", "end_time", "location", "coach", "topic", "notes",
                               "recurrence", "until")}
    out.update({
        "weekdays": sorted(weekdays_of(row)) if row["recurrence"] in ("weekly", "biweekly") else [],
        "pattern": pattern_text(row), "kind_label": KINDS[row["kind"]],
        "skips": json.loads(row["skips"] or "[]"), "done": json.loads(row["done"] or "[]"),
        "next": nxt["date"] if nxt else None,
    })
    return out


def minutes(row: dict) -> int:
    """Length of one session in minutes (0 when no times are set)."""
    if not (TIME.match(row["start_time"] or "") and TIME.match(row["end_time"] or "")):
        return 0
    a, b = (int(row["start_time"][:2]) * 60 + int(row["start_time"][3:]), int(row["end_time"][:2]) * 60 + int(row["end_time"][3:]))
    return max(0, b - a)

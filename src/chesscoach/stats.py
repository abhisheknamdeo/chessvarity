"""The results table: wins, draws and losses by month and year, with accuracy and rating.

A game counts once. A game with moves counts through its own record; a tournament round that has no
game attached (for example one imported from USCF, which keeps results but not moves) counts through
the round. Practice games against the computer are summarized on their own so they do not flatter
or hurt the real record.
"""

from __future__ import annotations

import csv
import io

from . import pgnio

PRACTICE = "Practice vs computer"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CSV_COLUMNS = ["Period", "Games", "Won", "Drawn", "Lost", "Score %", "White games", "White score %", "Black games",
               "Black score %", "Analyzed games", "Average accuracy %", "Blunders per game", "Mistakes per game",
               "Tournaments", "Rating at start", "Rating at end", "Rating change"]


def month_key(date: str) -> str:
    """'2026.09.14' -> '2026.09'; a date with no usable month -> '' (shown as "No date")."""
    parsed = pgnio.parse_date(date)
    return f"{parsed[0]:04d}.{parsed[1]:02d}" if parsed else ""


def label(key: str) -> str:
    if not key:
        return "No date"
    if len(key) != 7:                  # a year such as "2026"
        return key
    year, month = key.split(".")
    return f"{MONTHS[int(month) - 1]} {year}"


def _points(wins: int, draws: int) -> float:
    return wins + 0.5 * draws


def _score(wins: int, draws: int, games: int) -> int | None:
    return round(100 * _points(wins, draws) / games) if games else None


def _row(key: str, entries: list[dict], events: list[dict]) -> dict:
    """One line of the table. Each entry is {outcome, color, accuracy, blunders, mistakes}; events supply ratings."""
    def count(subset, what):
        return sum(1 for e in subset if e["outcome"] == what)

    wins, draws, losses = (count(entries, x) for x in ("win", "draw", "loss"))
    games = wins + draws + losses
    sides = {}
    for side in ("white", "black"):
        sub = [e for e in entries if e["color"] == side]
        w, d = count(sub, "win"), count(sub, "draw")
        sides[side] = {"games": len(sub), "score": _score(w, d, len(sub))}
    analysed = [e for e in entries if e["accuracy"] is not None]
    rated = [e for e in events if e["rating_before"] is not None and e["rating_after"] is not None
             and e["rating_system"] in ("", "R")]
    rated.sort(key=lambda e: e["start_date"])
    start = rated[0]["rating_before"] if rated else None
    end = rated[-1]["rating_after"] if rated else None
    return {
        "key": key, "label": label(key), "games": games, "wins": wins, "draws": draws, "losses": losses,
        "unfinished": len(entries) - games,
        "score": _score(wins, draws, games),
        "white": sides["white"], "black": sides["black"],
        "analysed": len(analysed),
        "accuracy": round(sum(e["accuracy"] for e in analysed) / len(analysed), 1) if analysed else None,
        "blunders_per_game": round(sum(e["blunders"] for e in analysed) / len(analysed), 1) if analysed else None,
        "mistakes_per_game": round(sum(e["mistakes"] for e in analysed) / len(analysed), 1) if analysed else None,
        "events": len(events),
        "rating_start": start, "rating_end": end,
        "rating_change": end - start if start is not None and end is not None else None,
    }


def collect(games: list[dict], rounds: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn game rows and unlinked round rows into (real entries, practice entries), each with a month key."""
    real, practice = [], []
    for g in games:
        analysis = g.get("analysis") or {}
        counts = analysis.get("counts", {})
        done = g.get("status") == "done" and g.get("accuracy") is not None
        entry = {
            "key": month_key(g["date"]), "outcome": pgnio.outcome(g["result"], g["color"]), "color": g["color"],
            "accuracy": g["accuracy"] if done else None,
            "blunders": counts.get("blunders", 0), "mistakes": counts.get("mistakes", 0),
        }
        (practice if g.get("event") == PRACTICE else real).append(entry)
    for r in rounds:
        real.append({"key": month_key(r["start_date"]), "outcome": r["result"] or None, "color": r["color"] or "",
                     "accuracy": None, "blunders": 0, "mistakes": 0})
    return real, practice


def build(games: list[dict], rounds: list[dict], events: list[dict]) -> dict:
    """games: rows with date/result/color/event/status/accuracy/analysis (dict or None).
    rounds: rounds with no game attached, joined with their event's start_date.
    events: past events (start_date, rating_before/after/system) for the rating columns."""
    real, practice = collect(games, rounds)
    past = [e for e in events if e["kind"] != "upcoming"]

    def events_in(key: str) -> list[dict]:
        return [e for e in past if month_key(e["start_date"]) == key] if len(key) == 7 else \
               [e for e in past if month_key(e["start_date"]).startswith(key)] if key else \
               [e for e in past if not month_key(e["start_date"])]

    keys = sorted({e["key"] for e in real}, reverse=True)
    months = [_row(k, [e for e in real if e["key"] == k], events_in(k)) for k in keys]
    years = []
    for y in sorted({k[:4] for k in keys if k}, reverse=True):
        years.append(_row(y, [e for e in real if e["key"].startswith(y)], events_in(y)))
    total = _row("all", real, past)
    total["label"] = "All time"
    total["events"] = len(past)
    practice_row = _row("practice", practice, [])
    practice_row["label"] = PRACTICE
    return {"months": months, "years": years, "total": total, "practice": practice_row}


def to_csv(table: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in (*table["months"], *(dict(r, label=f"{r['label']} (year)") for r in table["years"]), table["total"]):
        writer.writerow([row["label"], row["games"], row["wins"], row["draws"], row["losses"], row["score"],
                         row["white"]["games"], row["white"]["score"], row["black"]["games"], row["black"]["score"],
                         row["analysed"], row["accuracy"], row["blunders_per_game"], row["mistakes_per_game"],
                         row["events"], row["rating_start"], row["rating_end"], row["rating_change"]])
    return out.getvalue()

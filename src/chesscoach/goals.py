"""The goal sheet: short-term and long-term goals, some measured automatically from the student's own games.

A goal can be tied to a metric (for example "accuracy" or the "Spotting threats" habit score). The app records
where the metric stood when the goal was made and then shows progress toward the target. A goal with no metric
is a simple to-do that the student ticks off themselves.
"""

from __future__ import annotations

HORIZONS = ("short", "long")
STATUSES = ("active", "done", "dropped")

BASE_METRICS = {
    "accuracy": {"label": "Average accuracy, last 5 games", "unit": "%", "better": "up"},
    "blunders": {"label": "Blunders per game, last 5 games", "unit": "", "better": "down"},
    "score": {"label": "Score in games (wins and half draws)", "unit": "%", "better": "up"},
    "games": {"label": "Games analyzed", "unit": "", "better": "up"},
    "puzzles": {"label": "Puzzles solved", "unit": "", "better": "up"},
    "streak": {"label": "Best practice streak (days in a row)", "unit": "", "better": "up"},
    "rating": {"label": "USCF regular rating", "unit": "", "better": "up"},
}
HABITS = {
    "attack": "Attacking the opponent", "passive": "Playing actively", "tactics": "Finding tactics",
    "threats": "Spotting threats", "blunders": "Blunder check", "opening": "Opening discipline",
    "converting": "Turning good positions into wins", "endgame": "Endgames",
}


def metric_catalog() -> dict[str, dict]:
    out = dict(BASE_METRICS)
    for hid, title in HABITS.items():
        out[f"habit_{hid}"] = {"label": f"Habit score: {title}", "unit": "/100", "better": "up"}
    return out


def current_values(games: list[dict], habit_report: dict, journey_data: dict, uscf_ratings: dict, table: dict) -> dict[str, float | None]:
    """The present value of every metric. None means there is not enough data yet."""
    recent = [g for g in games[-5:] if g.get("accuracy") is not None]
    values: dict[str, float | None] = {
        "accuracy": round(sum(g["accuracy"] for g in recent) / len(recent), 1) if recent else None,
        "blunders": round(sum(g["analysis"]["counts"]["blunders"] for g in recent) / len(recent), 1) if recent else None,
        "score": table["total"]["score"],
        "games": journey_data["stats"]["games"],
        "puzzles": journey_data["stats"]["puzzles"],
        "streak": journey_data["streak"]["best"],
        "rating": uscf_ratings.get("regular"),
    }
    scores = {h["id"]: h["score"] for h in habit_report.get("habits", [])}
    for hid in HABITS:
        values[f"habit_{hid}"] = scores.get(hid)
    return values


def progress(better: str, baseline: float | None, target: float | None, current: float | None) -> dict:
    """How far from the starting point toward the target, 0-100, and whether the target is met."""
    if current is None or target is None:
        return {"percent": None, "reached": False}
    reached = current >= target if better == "up" else current <= target
    if baseline is None or baseline == target:
        return {"percent": 100 if reached else 0, "reached": reached}
    fraction = (current - baseline) / (target - baseline)
    return {"percent": max(0, min(100, round(100 * fraction))), "reached": reached}


def _round_up(value: float, step: int) -> int:
    return int(-(-value // step) * step)


def suggestions(values: dict, habit_report: dict, existing_metrics: set[str], has_uscf: bool) -> list[dict]:
    """Goals worth setting now, based on where the student stands. Skips a metric that already has an active goal."""
    out: list[dict] = []

    def add(horizon, title, metric, target, notes, steps):
        if metric and metric in existing_metrics:
            return
        out.append({"horizon": horizon, "title": title, "metric": metric, "target": target, "notes": notes, "steps": steps})

    habits = habit_report.get("habits", []) if habit_report.get("ready") else []
    for h in [h for h in habits if h["level"] == "work"][:2]:
        target = min(100, _round_up(h["score"] + 15, 5))
        add("short", f"Raise “{h['title']}” to {target}", f"habit_{h['id']}", target, h["detail"],
            list(h["advice"][:2]) + [f"Work through the exercises: {h['train'][0]['label']}" if h["train"] and h["train"][0].get("label") else "Solve two puzzles on this every day"])
    if values["blunders"] is not None and values["blunders"] >= 1:
        add("short", "Play a game with fewer blunders", "blunders", max(0, round(values["blunders"] - 1, 1)),
            "Every move, run the blunder check: what does my move leave unprotected, and what is their most annoying reply?",
            ["Before each move, say out loud what they threaten", "After each game, count the blunders and write down the cause of each"])
    if values["accuracy"] is not None:
        target = min(95, _round_up(values["accuracy"] + 5, 5))
        add("short", f"Reach {target}% average accuracy", "accuracy", target,
            "Accuracy rises when you avoid the big mistakes. Focus on the seven-question routine, not on speed.",
            ["Use the Think page for 10 minutes on three days this week"])
    add("short", "Practice on 5 days in a row", "streak", 5, "A little each day beats a long session once a week.",
        ["Solve one puzzle a day", "Look at one model game move by move"])
    add("short", "Solve 20 puzzles", "puzzles", (values["puzzles"] or 0) + 20, "Puzzles train the pattern-spotting that stops blunders.", [])
    if has_uscf and values["rating"]:
        target = _round_up(values["rating"] + 50, 25)
        add("long", f"Reach a {target} USCF rating", "rating", target,
            "Ratings move slowly. The way there is fewer blunders, better openings and finishing won games.",
            ["Play in a tournament every 4 to 6 weeks", "Enter every game and review the biggest mistake"])
    add("long", "Analyze 30 of my own games", "games", max(30, (values["games"] or 0) + 20),
        "The more of your own games you study, the clearer your habits become.", ["Add each tournament game the same weekend"])
    add("long", "Score at least 50% over a whole season", "score", 50, "Winning half your games or more.", [])
    add("long", "Learn one opening for White and one for Black", "", None,
        "Know the first eight moves, the main idea, and one trap to avoid.", ["Pick them on the Tournament plan page", "Play each one in three games"])
    return out[:8]

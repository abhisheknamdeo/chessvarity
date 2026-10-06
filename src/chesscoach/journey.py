"""Progress that feels like a game: XP and a rank, a daily streak, and badges to earn.

Everything is computed from what the student has already done, so nothing extra is stored.
"""

from __future__ import annotations

import datetime as dt

RANKS = [(0, "Pawn"), (100, "Knight"), (300, "Bishop"), (700, "Rook"), (1400, "Queen"), (2500, "King")]
XP_PER_GAME = 20
XP_PER_PUZZLE = 8


def _day(timestamp: float) -> dt.date:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date()


def streaks(days: set[dt.date], today: dt.date) -> dict:
    """Consecutive days with activity. A streak stays alive until the end of the day after the last activity."""
    if not days:
        return {"current": 0, "best": 0, "today_done": False}
    best = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    current = 0
    cursor = today if today in days else today - dt.timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= dt.timedelta(days=1)
    return {"current": current, "best": best, "today_done": today in days}


def build(games: list[dict], solved: list[dict], today: dt.date | None = None) -> dict:
    """games: [{created_at, status, accuracy, event, blunders, plies}]; solved: [{puzzle_id, solved_at, theme}]."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    analysed = [g for g in games if g["status"] == "done"]
    puzzles = len(solved)
    xp = XP_PER_GAME * len(analysed) + XP_PER_PUZZLE * puzzles

    index = max(i for i, (floor, _) in enumerate(RANKS) if xp >= floor)
    rank = {"name": RANKS[index][1], "index": index, "xp_floor": RANKS[index][0]}
    if index + 1 < len(RANKS):
        nxt = RANKS[index + 1]
        span = nxt[0] - RANKS[index][0]
        rank["next"] = {"name": nxt[1], "xp": nxt[0], "needed": nxt[0] - xp}
        rank["progress"] = round(100 * (xp - RANKS[index][0]) / span)
    else:
        rank["next"] = None
        rank["progress"] = 100

    days = {_day(g["created_at"]) for g in games} | {_day(s["solved_at"]) for s in solved}
    streak = streaks(days, today)

    by_theme: dict[str, int] = {}
    for s in solved:
        by_theme[s["theme"]] = by_theme.get(s["theme"], 0) + 1
    clean = [g for g in analysed if g.get("plies", 0) >= 24 and g.get("blunders", 1) == 0]
    sharp = [g for g in analysed if (g.get("accuracy") or 0) >= 90 and g.get("plies", 0) >= 24]
    sparring = [g for g in games if g.get("event") == "Practice vs computer"]

    def badge(bid, title, desc, have, need, icon):
        return {"id": bid, "title": title, "desc": desc, "icon": icon, "earned": have >= need,
                "progress": min(have, need), "target": need}

    badges = [
        badge("first-game", "First game", "Analyze your first game.", len(analysed), 1, "wP"),
        badge("five-games", "Regular", "Analyze 5 games.", len(analysed), 5, "wN"),
        badge("ten-games", "Dedicated", "Analyze 10 games.", len(analysed), 10, "wB"),
        badge("first-puzzle", "Puzzle starter", "Solve your first puzzle.", puzzles, 1, "wR"),
        badge("ten-puzzles", "Puzzle fan", "Solve 10 puzzles.", puzzles, 10, "wQ"),
        badge("attacker", "Attacker", "Solve 5 attack puzzles.", by_theme.get("attack", 0) + by_theme.get("mates", 0), 5, "wK"),
        badge("trap-spotter", "Trap spotter", "Solve all the opening traps.", by_theme.get("traps", 0), 3, "bP"),
        badge("tactician", "Tactician", "Solve 5 tactics puzzles.", by_theme.get("tactics", 0), 5, "bN"),
        badge("clean-game", "Clean game", "Play a game (12+ moves) without a single blunder.", len(clean), 1, "bB"),
        badge("sharp", "Sharp play", "Reach 90% accuracy in a game.", len(sharp), 1, "bR"),
        badge("sparring", "Sparring partner", "Save a game you played against the computer.", len(sparring), 1, "bQ"),
        badge("streak-3", "On a roll", "Practice 3 days in a row.", streak["best"], 3, "bK"),
        badge("streak-7", "Week warrior", "Practice 7 days in a row.", streak["best"], 7, "wP"),
    ]
    return {
        "xp": xp, "rank": rank, "streak": streak, "badges": badges,
        "stats": {"games": len(analysed), "puzzles": puzzles},
        "earned": sum(1 for b in badges if b["earned"]),
    }

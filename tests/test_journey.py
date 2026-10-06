import datetime as dt

from chesscoach import academy, journey

D = dt.date


def ts(d: dt.date) -> float:
    return dt.datetime(d.year, d.month, d.day, 12, tzinfo=dt.timezone.utc).timestamp()


def test_streak_counts_consecutive_days_and_survives_until_tomorrow():
    today = D(2026, 9, 20)
    assert journey.streaks(set(), today) == {"current": 0, "best": 0, "today_done": False}
    days = {D(2026, 9, 17), D(2026, 9, 18), D(2026, 9, 19)}
    # Nothing yet today, but yesterday counts: the streak is still alive.
    assert journey.streaks(days, today) == {"current": 3, "best": 3, "today_done": False}
    assert journey.streaks(days | {today}, today)["current"] == 4
    # Two days missed: it is over, but the best run is remembered.
    assert journey.streaks(days, D(2026, 9, 22)) == {"current": 0, "best": 3, "today_done": False}
    gap = {D(2026, 9, 1), D(2026, 9, 2), D(2026, 9, 10)}
    assert journey.streaks(gap, D(2026, 9, 10))["current"] == 1 and journey.streaks(gap, D(2026, 9, 10))["best"] == 2


def game(day, **kw):
    return {"created_at": ts(day), "status": "done", "accuracy": 80.0, "event": "", "plies": 40, "blunders": 1, **kw}


def test_xp_rank_and_next_rank():
    today = D(2026, 9, 20)
    games = [game(today - dt.timedelta(days=i)) for i in range(4)]          # 4 games = 80 xp
    solved = [{"puzzle_id": f"p{i}", "solved_at": ts(today), "theme": "mates"} for i in range(3)]   # 3 puzzles = 24 xp
    out = journey.build(games, solved, today)
    assert out["xp"] == 104 and out["rank"]["name"] == "Knight" and out["rank"]["next"]["name"] == "Bishop"
    assert out["rank"]["next"]["needed"] == 196 and 0 <= out["rank"]["progress"] <= 100
    assert journey.build([], [], today)["rank"]["name"] == "Pawn"
    king = journey.build([], [{"puzzle_id": str(i), "solved_at": ts(today), "theme": "tactics"} for i in range(400)], today)
    assert king["rank"]["name"] == "King" and king["rank"]["next"] is None


def test_badges_are_earned_from_real_activity():
    today = D(2026, 9, 20)
    games = [game(today - dt.timedelta(days=i), blunders=0 if i == 0 else 2, accuracy=93.0 if i == 0 else 60.0) for i in range(3)]
    games.append(game(today, event="Practice vs computer"))
    games.append({**game(today), "status": "queued"})       # not analysed yet: earns nothing
    solved = [{"puzzle_id": f"m{i}", "solved_at": ts(today), "theme": "mates"} for i in range(5)]
    out = journey.build(games, solved, today)
    earned = {b["id"] for b in out["badges"] if b["earned"]}
    assert {"first-game", "first-puzzle", "attacker", "clean-game", "sharp", "sparring", "streak-3"} <= earned
    assert "five-games" not in earned and "streak-7" not in earned
    five = next(b for b in out["badges"] if b["id"] == "five-games")
    assert five["progress"] == 4 and five["target"] == 5   # 4 analysed games so far
    assert out["stats"] == {"games": 4, "puzzles": 5}


def test_the_daily_puzzle_is_stable_within_a_day_and_changes_between_days():
    a = academy.daily_puzzle("2026-09-20")
    assert academy.daily_puzzle("2026-09-20")["id"] == a["id"]
    assert a["fens"] and len(a["line"]) <= 5
    assert len({academy.daily_puzzle(f"2026-09-{d:02d}")["id"] for d in range(1, 29)}) > 5

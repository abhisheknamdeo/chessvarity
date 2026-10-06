"""Community points and levels.

Points are worked out from what people actually did (never stored), so they are always right, count past activity,
and drop if something is hidden by an admin. Liking your own things earns nothing, and only a few shares and
comments a day count, so there's no point in spamming.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

RULES = {
    "share": 10,         # shared a game with the community
    "question": 5,       # ...and asked a question about it
    "comment": 3,        # commented on someone else's game
    "first_answer": 5,   # the first person to answer someone's question
    "game_like": 2,      # someone liked a game you shared
    "helpful": 3,        # someone marked your comment helpful
}
DAILY_CAP = {"share": 5, "comment": 10}

LEVELS = [
    (0, "Newcomer"), (20, "Helper"), (60, "Contributor"), (150, "Mentor"),
    (300, "Coach"), (600, "Master Coach"), (1000, "Grandmaster"),
]

HOW_TO_EARN = [
    ("Share one of your games", RULES["share"]),
    ("Ask a question when you share", RULES["question"]),
    ("Comment on someone else's game", RULES["comment"]),
    ("Be the first to answer a question", RULES["first_answer"]),
    ("Someone likes a game you shared", RULES["game_like"]),
    ("Someone marks your comment helpful", RULES["helpful"]),
]


def level_for(points: int) -> dict:
    index = max(i for i, (floor, _) in enumerate(LEVELS) if points >= floor)
    floor, name = LEVELS[index]
    nxt = LEVELS[index + 1] if index + 1 < len(LEVELS) else None
    return {
        "level": index + 1, "name": name, "points": points, "floor": floor,
        "next_name": nxt[1] if nxt else None, "next_at": nxt[0] if nxt else None,
        "progress": 1.0 if not nxt else round((points - floor) / (nxt[0] - floor), 3),
    }


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def _capped(rows: list[dict], kind: str) -> dict[int, int]:
    """How many of each user's actions count, at most DAILY_CAP[kind] a day."""
    per_day: dict[tuple[int, str], int] = defaultdict(int)
    for r in rows:
        per_day[(r["user_id"], _day(r["created_at"]))] += 1
    out: dict[int, int] = defaultdict(int)
    for (user, _), n in per_day.items():
        out[user] += min(n, DAILY_CAP[kind])
    return out


def points(db, since: float = 0.0) -> dict[int, dict]:
    """{user id: {"total": n, "breakdown": {rule: points}}} for everyone with community activity since `since`."""
    shares = db.all("SELECT id, user_id, question, created_at FROM shares WHERE status = 'public' AND created_at >= ?", (since,))
    comments = db.all(
        "SELECT c.id, c.user_id, c.share_id, c.created_at FROM share_comments c JOIN shares s ON s.id = c.share_id "
        "WHERE c.status = 'visible' AND s.status = 'public' AND c.user_id != s.user_id AND c.created_at >= ?", (since,))
    first_answers = db.all(
        "SELECT c.user_id, c.created_at FROM share_comments c JOIN shares s ON s.id = c.share_id "
        "WHERE s.question != '' AND s.status = 'public' AND c.status = 'visible' AND c.user_id != s.user_id AND c.created_at >= ? "
        "AND c.id = (SELECT MIN(c2.id) FROM share_comments c2 WHERE c2.share_id = s.id AND c2.status = 'visible' AND c2.user_id != s.user_id)",
        (since,))
    game_likes = db.all(
        "SELECT s.user_id, COUNT(*) AS n FROM share_likes l JOIN shares s ON s.id = l.share_id "
        "WHERE s.status = 'public' AND l.user_id != s.user_id AND l.created_at >= ? GROUP BY s.user_id", (since,))
    helpful = db.all(
        "SELECT c.user_id, COUNT(*) AS n FROM comment_likes l JOIN share_comments c ON c.id = l.comment_id "
        "WHERE c.status = 'visible' AND l.user_id != c.user_id AND l.created_at >= ? GROUP BY c.user_id", (since,))

    tally: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for user, n in _capped(shares, "share").items():
        tally[user]["share"] += n * RULES["share"]
    for user, n in _capped([s for s in shares if s["question"]], "share").items():
        tally[user]["question"] += n * RULES["question"]
    for user, n in _capped(comments, "comment").items():
        tally[user]["comment"] += n * RULES["comment"]
    for r in first_answers:
        tally[r["user_id"]]["first_answer"] += RULES["first_answer"]
    for r in game_likes:
        tally[r["user_id"]]["game_like"] += r["n"] * RULES["game_like"]
    for r in helpful:
        tally[r["user_id"]]["helpful"] += r["n"] * RULES["helpful"]
    return {user: {"total": sum(b.values()), "breakdown": dict(b)} for user, b in tally.items()}


def levels_for_users(db, user_ids) -> dict[int, dict]:
    """Level badges for the people on a page (everyone starts as a Newcomer)."""
    everyone = points(db)
    return {uid: level_for(everyone.get(uid, {}).get("total", 0)) for uid in set(user_ids)}

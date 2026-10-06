"""Cross-game insight: habits, missed wins, openings and a dashboard for one player.

Everything here reads the per-game analysis stored by the worker; no engine is involved.
Thresholds are coaching heuristics, tuned to be encouraging rather than exact.
"""

from __future__ import annotations

import json

from . import pgnio

RECENT_GAMES = 10
MIN_MOVES = 20  # fewer analysed moves than this and a habit says nothing yet
ATTACK_TARGET = 0.5  # share of "free" moves that should make some kind of threat (a coaching heuristic)


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"
LEVELS = ((75, "strong"), (50, "ok"), (0, "work"))


def analysed_games(db, user_id: int, player_id: int) -> list[dict]:
    rows = db.all(
        "SELECT id, color, result, event, round, date, opponent, white_elo, black_elo, opening_eco, opening_name, opening_plies, "
        "plies, accuracy, analysis FROM games WHERE user_id = ? AND player_id = ? AND status = 'done' "
        "ORDER BY CASE WHEN date = '' THEN '9999' ELSE date END, id",
        (user_id, player_id),
    )
    for row in rows:
        row["analysis"] = json.loads(row["analysis"])
        row["outcome"] = pgnio.outcome(row["result"], row["color"])
    return rows


def _level(score: float) -> str:
    return next(name for floor, name in LEVELS if score >= floor)


def _sum(games: list[dict], *path: str) -> float:
    total = 0.0
    for g in games:
        node = g["analysis"]["habits"]
        for key in path:
            node = node[key]
        total += node
    return total


def _skill(games: list[dict], name: str) -> tuple[int, int]:
    ops = sum(g["analysis"]["skills"][name]["opportunities"] for g in games)
    ok = sum(g["analysis"]["skills"][name]["handled"] for g in games)
    return ok, ops


def _evidence(games: list[dict], categories: tuple[str, ...], limit: int = 4) -> list[dict]:
    """Example moments, worst first, each pointing back at its game and move."""
    found = []
    for g in games:
        for m in g["analysis"]["moments"]:
            if m["category"] in categories:
                found.append((m.get("importance", m["loss"]), g, m))
    found.sort(key=lambda x: -x[0])
    return [
        {
            "game_id": g["id"], "ply": m["ply"], "move_number": m["move_number"], "headline": m["headline"],
            "opponent": g["opponent"], "event": g["event"], "fen": m["fen"], "side": m["side"],
            "played": m["played"]["san"], "best": m["best"]["san"],
        }
        for _, g, m in found[:limit]
    ]


ADVICE = {
    "attack": [
        "When you are not in danger, ask before every move: can I give a check? Can I threaten something? Can I bring another piece toward their king?",
        "Count attackers and defenders around their king. If you have more attackers, look for a way to open lines (a pawn break or a piece sacrifice).",
        "Solve a few Attack Academy puzzles each day and replay the attacking model games. Attacking patterns repeat; learn them and you will spot them in your own games.",
        "Choose openings that develop quickly toward the king, like the Italian Game or the Scotch. See the Openings library.",
    ],
    "passive": [
        "After you defend a threat, stop and ask: what threat can I make now? Do not just make a safe waiting move.",
        "Retreating a piece is fine when it is attacked, but check first for a move that defends and attacks at the same time.",
        "Take space in the center with pawns when it is safe, and bring your pieces to active squares instead of shuffling.",
        "Try a counter-attack the next time your opponent attacks. A check or a threat against their king slows most attacks down.",
    ],
    "tactics": [
        "Before every move, look at all checks, then all captures, then all threats (in that order). Most tactics start with a forcing move.",
        "Practice forks, pins and discovered attacks in the Attack Academy; ten minutes a day works better than one long session.",
        "When your opponent's pieces are undefended or lined up, look for a double attack.",
    ],
    "threats": [
        "Use the THINK routine before every move: T is what is my opponent threatening? H is any checks? I is important captures? N is new threats for me? K is king safety.",
        "Look at the square your opponent's last move went to, and at everything that piece now attacks.",
        "Work through the threat positions in your Workbook. They come from your own games.",
    ],
    "blunders": [
        "Blunder check: before you let go of a piece, ask what can my opponent capture after this move? and does this leave anything unprotected?",
        "Count how many times each of your pieces is attacked and defended. If attackers outnumber defenders, do not leave it there.",
        "Slow down on captures and on moves with your queen: many blunders happen there.",
    ],
    "opening": [
        "Castle by move 10 to keep your king safe and connect your rooks.",
        "Develop a knight or bishop with almost every early move, and try not to move the same piece twice before you finish developing.",
        "Keep the queen at home in the first moves; bringing it out early lets your opponent gain time by attacking it.",
    ],
    "converting": [
        "When you are better, look for the most forcing continuation. Checks, captures and threats keep control.",
        "If you are ahead in material, trade pieces (not pawns) and keep your king safe. If you are not ahead, keep attacking.",
        "Before a quiet move, ask: what is my opponent's best defensive move, and can I take it away?",
    ],
    "endgame": [
        "In the endgame the king becomes a strong piece: bring it toward the center.",
        "Practice basic endgames: king and pawn, rook endgames and simple mates.",
        "Do not rush: with fewer pieces every move matters more.",
    ],
}

TRAIN = {
    "attack": [{"kind": "academy", "theme": "attack", "label": "Attack Academy: king attacks"},
               {"kind": "model", "label": "Attacking model games"}],
    "passive": [{"kind": "academy", "theme": "attack", "label": "Attack Academy"},
                {"kind": "workbook", "skill": "initiative", "label": "Your own passive positions"}],
    "tactics": [{"kind": "academy", "theme": "tactics", "label": "Tactics puzzles"},
                {"kind": "workbook", "skill": "tactics", "label": "Tactics you missed"}],
    "threats": [{"kind": "workbook", "skill": "threat_recognition", "label": "Threats you missed"}],
    "blunders": [{"kind": "workbook", "skill": "blunder_check", "label": "Pieces you left in danger"}],
    "opening": [{"kind": "openings", "label": "Opening library"}],
    "converting": [{"kind": "academy", "theme": "mates", "label": "Mating patterns"},
                   {"kind": "wins", "label": "Wins you missed"}],
    "endgame": [],
}


def _habit(hid: str, title: str, problem: str, strength: str, score: float, detail: str, games: list[dict],
           evidence: list[dict]) -> dict:
    score = max(0, min(100, round(score)))
    level = _level(score)
    return {
        "id": hid, "title": title, "score": score, "level": level,
        "headline": strength if level == "strong" else problem, "detail": detail,
        "evidence": evidence, "advice": ADVICE[hid], "train": TRAIN[hid], "games": len(games),
    }


def habits(all_games: list[dict], recent: int = RECENT_GAMES) -> dict:
    games = all_games[-recent:]
    moves = int(_sum(games, "moves")) if games else 0
    if moves < MIN_MOVES:
        return {"ready": False, "games": len(games), "moves": moves,
                "message": "Add and analyze a few more games. Habits appear once there are about 20 analyzed moves.",
                "habits": []}
    out = []

    free = _sum(games, "free_moves")
    if free >= 8:
        rate = _sum(games, "free_attacking") / free
        taken, ops = _skill(games, "attacking")
        score = 100 * min(1, rate / ATTACK_TARGET)
        if ops >= 3:
            score = 0.6 * score + 0.4 * (100 * taken / ops)
        out.append(_habit(
            "attack", "Attacking the opponent",
            "You are not attacking your opponent enough.", "You attack your opponent well.", score,
            f"When you were not in danger, {round(100 * rate)}% of your moves attacked (a check, a threat, "
            f"a winning capture, or a piece brought toward their king). Aim for about {round(100 * ATTACK_TARGET)}%."
            + (f" You took {taken} of {ops} clear attacking chances." if ops else ""),
            games, _evidence(games, ("missed_attack",))))

    reactive, retreats = _sum(games, "reactive"), _sum(games, "retreats")
    spirals = sum(1 for g in games for m in g["analysis"]["moments"] if m["category"] == "defensive_spiral")
    passive_rate = (reactive + retreats) / moves
    out.append(_habit(
        "passive", "Playing actively",
        "You are playing too passively.", "You play actively and keep the initiative.",
        100 * (1 - min(1, passive_rate / 0.5)) - 5 * spirals,
        f"{round(100 * reactive / moves)}% of your moves only answered a threat and made none of your own, "
        f"and {round(100 * retreats / moves)}% moved a piece backwards. "
        + (f"You fell into a defensive spiral {spirals} time(s)." if spirals else "No defensive spirals."),
        games, _evidence(games, ("defensive_spiral",))))

    found, ops = _skill(games, "tactics")
    if ops >= 2:
        out.append(_habit(
            "tactics", "Finding tactics",
            "You are missing tactics.", "You find tactics well.", 100 * found / ops,
            f"You found {found} of the {ops} clear tactical chances in your games.",
            games, _evidence(games, ("missed_tactic",))))

    ok, ops = _skill(games, "threat_recognition")
    if ops >= 2:
        out.append(_habit(
            "threats", "Spotting threats",
            "You are missing your opponent's threats.", "You spot your opponent's threats.", 100 * ok / ops,
            f"You dealt with {ok} of the {ops} real threats your opponents made.",
            games, _evidence(games, ("missed_threat",))))

    hung = sum(1 for g in games for m in g["analysis"]["moments"] if m["category"] == "hung_piece")
    out.append(_habit(
        "blunders", "Blunder check",
        "You leave pieces hanging.", "You rarely leave pieces hanging.",
        100 * (1 - min(1, (hung / moves) / 0.08)),
        f"{_n(hung, 'move')} left a piece or a fork on the table in {moves} moves.",
        games, _evidence(games, ("hung_piece",))))

    long_games = [g for g in games if g["analysis"]["habits"]["opening"]["developed"] is not None and g["plies"] >= 20]
    if long_games:
        castled = sum(1 for g in long_games
                      if (c := g["analysis"]["habits"]["opening"]["castled_by"]) is not None and c <= 10)
        developed = _sum(long_games, "opening", "developed") / len(long_games)
        queen = _sum(long_games, "opening", "early_queen") / len(long_games)
        repeats = _sum(long_games, "opening", "repeats") / len(long_games)
        score = 100 * (0.4 * castled / len(long_games) + 0.4 * min(1, developed / 3)
                       + 0.2 * (1 - min(1, (queen + repeats) / 2)))
        late = [g for g in long_games
                if (c := g["analysis"]["habits"]["opening"]["castled_by"]) is None or c > 10]
        evidence = [{"game_id": g["id"], "ply": 0, "move_number": 10, "headline": "Did not castle by move 10",
                     "opponent": g["opponent"], "event": g["event"], "fen": None, "side": g["color"],
                     "played": "", "best": ""} for g in late[:4]]
        out.append(_habit(
            "opening", "Opening discipline",
            "Your openings are slow or untidy.", "You handle your openings well.", score,
            f"You castled by move 10 in {castled} of {_n(len(long_games), 'game')} and had about "
            f"{developed:.1f} minor pieces developed by move 10 (aim for 3 or 4).",
            long_games, evidence))

    lost = [g for g in games if g["outcome"] != "win"]
    if lost:
        slipped = [g for g in lost if any(i["kind"] != "turning_point" for i in g["analysis"]["how_to_win"])]
        examples = [
            {"game_id": w["game_id"], "ply": w["ply"], "move_number": w["move_number"], "headline": w["headline"],
             "opponent": w["opponent"], "event": w["event"], "fen": w["fen"], "side": w["side"],
             "played": w["played"]["san"], "best": w["best"]["san"]}
            for w in _wins(slipped)[:4]
        ]
        out.append(_habit(
            "converting", "Turning good positions into wins",
            "You let good positions slip away.", "You convert good positions.",
            100 * (1 - len(slipped) / len(lost)),
            f"In {len(slipped)} of your {_n(len(lost), 'game')} that {'was' if len(lost) == 1 else 'were'} not a win, "
            "you had a clearly better position first.",
            games, examples))

    end_moves = int(_sum(games, "by_phase", "endgame", "moves"))
    if end_moves >= 10:
        mid_moves = max(1, int(_sum(games, "by_phase", "middlegame", "moves")))
        end_loss = _sum(games, "by_phase", "endgame", "loss") / end_moves
        mid_loss = _sum(games, "by_phase", "middlegame", "loss") / mid_moves
        out.append(_habit(
            "endgame", "Endgames",
            "Your endgames need work.", "Your endgames are solid.", 100 * (1 - min(1, end_loss / 8)),
            f"In endgames you lost about {end_loss:.1f} winning-chance points per move, "
            f"compared with {mid_loss:.1f} in the middlegame.",
            games, []))

    out.sort(key=lambda h: h["score"])
    return {"ready": True, "games": len(games), "moves": moves, "habits": out}


def _wins(games: list[dict]) -> list[dict]:
    """'How you could have won' positions from games that were not wins."""
    items = []
    for g in games:
        if g["outcome"] == "win":
            continue
        for item in g["analysis"]["how_to_win"]:
            items.append({**item, "game_id": g["id"], "opponent": g["opponent"], "event": g["event"],
                          "date": g["date"], "outcome": g["outcome"],
                          "importance": item["wp_before"] - 50 + item["loss"]})
    items.sort(key=lambda w: -w["importance"])
    return items


def wins(all_games: list[dict]) -> list[dict]:
    return _wins(all_games)[:30]


def openings(all_games: list[dict]) -> dict:
    """How the player has done in each opening family, by color."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for g in all_games:
        family = (g["opening_name"] or "Unnamed opening").split(":")[0].strip()
        groups.setdefault((g["color"], family), []).append(g)
    out = []
    for (color, family), games in groups.items():
        points = sum(1 if g["outcome"] == "win" else 0.5 if g["outcome"] == "draw" else 0 for g in games)
        opening_moves = sum(g["analysis"]["habits"]["by_phase"]["opening"]["moves"] for g in games)
        opening_loss = sum(g["analysis"]["habits"]["by_phase"]["opening"]["loss"] for g in games)
        out.append({
            "family": family, "color": color, "games": len(games),
            "wins": sum(g["outcome"] == "win" for g in games),
            "draws": sum(g["outcome"] == "draw" for g in games),
            "losses": sum(g["outcome"] == "loss" for g in games),
            "score": round(100 * points / len(games)),
            "accuracy": round(sum(g["accuracy"] for g in games) / len(games), 1),
            "book_plies": round(sum(g["opening_plies"] for g in games) / len(games), 1),
            "opening_loss": round(opening_loss / opening_moves, 1) if opening_moves else 0.0,
            "eco": next((g["opening_eco"] for g in games if g["opening_eco"]), ""),
            "example": {"game_id": games[-1]["id"]},
        })
    out.sort(key=lambda o: (-o["games"], o["family"]))
    weakest = [o for o in out if o["games"] >= 2 and o["score"] < 40]
    return {
        "families": out,
        "advice": [
            f"You scored {o['score']}% as {o['color']} in the {o['family']} over {o['games']} games. "
            "Look at the moments where you left the book and compare with the library line."
            for o in weakest[:3]
        ],
    }


def workbook(all_games: list[dict], skill: str | None = None, limit: int = 40) -> list[dict]:
    items = []
    for g in all_games:
        for m in g["analysis"]["moments"]:
            if skill and m.get("skill") != skill:
                continue
            items.append({
                "id": f"g{g['id']}-{m['ply']}", "game_id": g["id"], "date": g["date"],
                "vs": g["opponent"] or "opponent", "move_number": m["move_number"], "side": m["side"],
                "game": {
                    "opponent": g["opponent"], "event": g["event"], "match": g["round"], "date": g["date"],
                    "result": g["result"], "outcome": g["outcome"], "color": g["color"],
                    "opening": g["opening_name"], "eco": g["opening_eco"], "ply": m["ply"],
                    "played": m["played"]["san"], "accuracy": g["accuracy"],
                },
                "skill": m.get("skill"), "category": m["category"], "title": m["title"],
                "headline": m["headline"], "lesson": m["lesson"], "importance": m.get("importance", 0),
                "played": m["played"]["san"], "best": m["best"]["san"], "threat": m["threat"],
                "puzzle": m["puzzle"], "candidates": m["candidates"],
            })
    items.sort(key=lambda x: -x["importance"])
    return items[:limit]


def dashboard(all_games: list[dict]) -> dict:
    if not all_games:
        return {"games": 0}
    decided = [g for g in all_games if g["outcome"]]
    points = sum(1 if g["outcome"] == "win" else 0.5 if g["outcome"] == "draw" else 0 for g in decided)
    accs = [g["accuracy"] for g in all_games if g["accuracy"] is not None]
    recent, earlier = accs[-5:], accs[:-5]
    phases = {}
    for name in ("opening", "middlegame", "endgame"):
        n = _sum(all_games, "by_phase", name, "moves")
        phases[name] = {"moves": int(n), "loss": round(_sum(all_games, "by_phase", name, "loss") / n, 1) if n else None}
    by_color = {}
    for color in ("white", "black"):
        sub = [g for g in decided if g["color"] == color]
        by_color[color] = {
            "games": len(sub), "wins": sum(g["outcome"] == "win" for g in sub),
            "draws": sum(g["outcome"] == "draw" for g in sub), "losses": sum(g["outcome"] == "loss" for g in sub),
        }
    h = habits(all_games)
    ranked = h["habits"]
    return {
        "games": len(all_games),
        "record": {
            "wins": sum(g["outcome"] == "win" for g in decided), "draws": sum(g["outcome"] == "draw" for g in decided),
            "losses": sum(g["outcome"] == "loss" for g in decided),
            "score": round(100 * points / len(decided)) if decided else None,
        },
        "accuracy": {
            "average": round(sum(accs) / len(accs), 1) if accs else None,
            "recent": round(sum(recent) / len(recent), 1) if recent else None,
            "change": round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 1) if recent and earlier else None,
        },
        "series": [
            {"game_id": g["id"], "accuracy": g["accuracy"], "outcome": g["outcome"], "date": g["date"],
             "label": g["opponent"] or g["event"]} for g in all_games
        ],
        "phases": phases,
        "by_color": by_color,
        "focus": ranked[:3],
        "strengths": [x for x in ranked[::-1] if x["level"] == "strong"][:2],
        "habits_ready": h["ready"],
        "recent": [
            {"id": g["id"], "opponent": g["opponent"], "event": g["event"], "round": g["round"],
             "outcome": g["outcome"], "accuracy": g["accuracy"], "opening": g["opening_name"], "color": g["color"],
             "date": g["date"], "opponent_rating": (g.get("black_elo") if g["color"] == "white" else g.get("white_elo")) or ""}
            for g in all_games[-5:][::-1]
        ],
    }

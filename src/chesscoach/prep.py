"""Getting ready for a tournament: which openings to bring, and the attacking position to aim for in each.

For each repertoire opening there is a "target position": a well-known, healthy position that the opening
usually reaches, with the routes the pieces travel to get there and the squares to aim at. The student learns
the *ideas*, not a long memorised line, so the plans still make sense when the opponent deviates.
"""

from __future__ import annotations

import datetime as dt

import chess

from . import academy, pgnio

# id -> the position to aim for. `moves` is the whole line from the start. `routes` are journeys for a piece
# (each list of squares starts where the piece is in the position), `attacks` are what a piece is aiming at.
PLAYBOOK = {
    "italian": {
        "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O".split(),
        "routes": [{"squares": ["b1", "d2", "f1", "g3"], "note": "Bring the last knight around to the kingside via d2 and f1."},
                   {"squares": ["c4", "b3"], "note": "Keep the bishop safe on b3 where it still eyes f7."}],
        "attacks": [{"from": "c4", "to": "f7", "note": "f7 is guarded only by the king. Keep it under pressure."}],
        "aims": ["Play Re1 and Nbd2, then choose between d4 in the center or the knight route to g3 for a kingside attack.",
                 "Keep the pawn on d3 solid so your center cannot be undermined.",
                 "Once all your pieces are out, look for h3 and Bg5 to pin the knight on f6."],
        "watch": ["Do not play d4 too early if your pieces are not ready: ...exd4 and ...Nxe4 tricks appear.",
                  "Watch the pin on the f3 knight after ...Bg4."],
    },
    "evans": {
        "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O".split(),
        "routes": [{"squares": ["d1", "b3"], "note": "The queen joins the bishop against f7."},
                   {"squares": ["c1", "a3"], "note": "The bishop stops Black castling and pressures the dark squares."}],
        "attacks": [{"from": "c4", "to": "f7", "note": "The bishop and queen together aim at f7."}],
        "aims": ["You gave a pawn for lead in development, so use it: open lines fast and bring every piece out.",
                 "Play e5, Ba3 and Qb3 to keep Black from castling.",
                 "Recapture on d4 with pieces only when it opens lines for you."],
        "watch": ["If your attack stalls, you are simply a pawn down. Keep making threats.",
                  "Do not hang the bishop on c4 after ...d5."],
    },
    "two-knights": {
        "moves": "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7 Kxf7 Qf3+ Ke6 Nc3".split(),
        "routes": [],
        "attacks": [{"from": "c3", "to": "d5", "note": "Two pieces attack the knight on d5."},
                    {"from": "c4", "to": "d5", "note": "The bishop adds a second attacker."}],
        "aims": ["Black's king is out in the open, so keep every piece attacking and give it no time to hide.",
                 "The king on e6 has almost nowhere to go, so bring more pieces into the attack.",
                 "If Black knows the defense, choose the calmer 6.d3 or 5.d3 lines instead."],
        "watch": ["This line is sharp and one slip can lose. Practice it before you use it.",
                  "After 5...Na5 the sacrifice is not needed: play 6.Bb5+ and keep your extra pawn."],
    },
    "scotch": {
        "moves": "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Bc5 Be3 Qf6 c3 Nge7 Bc4 O-O O-O".split(),
        "routes": [{"squares": ["b1", "d2", "f3"], "note": "Reroute the last knight to reinforce the center."}],
        "attacks": [{"from": "c4", "to": "f7", "note": "The bishop pressures f7."},
                    {"from": "d4", "to": "c6", "note": "The knight can trade off Black's best defender."}],
        "aims": ["Open the center early, then develop the last pieces with tempo.",
                 "Use the e-file and the d4 knight to control the center.",
                 "Trade only when it helps your development."],
        "watch": ["Do not lose time moving the same piece twice.", "Watch for ...Qf6 forking b2 and d4."],
    },
    "vienna": {
        "moves": "e4 e5 Nc3 Nf6 f4 d5 fxe5 Nxe4 Nf3 Be7 d4 O-O Bd3".split(),
        "routes": [{"squares": ["f3", "g5"], "note": "The knight jumps to g5 with ideas on h7 and e4."},
                   {"squares": ["c1", "e3"], "note": "The bishop completes development and supports d4."}],
        "attacks": [{"from": "d3", "to": "e4", "note": "The bishop and knight both hit the knight on e4."},
                    {"from": "c3", "to": "e4", "note": "Attack the piece that took your pawn."}],
        "aims": ["Attack Black's knight on e4 with your pieces, then castle and use the f-file.",
                 "Bring the queen to e2 or h5 behind the attack.", "Trade the strong knight if you can."],
        "watch": ["After ...Bb4 or ...Qh4+, do not lose time: castle or block calmly.",
                  "Keep your king safe: f4 has loosened your kingside."],
    },
    "london": {
        "moves": "d4 d5 Bf4 Nf6 e3 e6 Nf3 Bd6 Bg3 O-O Bd3 c5 c3 Nc6 Nbd2".split(),
        "routes": [{"squares": ["f3", "e5"], "note": "The knight takes the strong square on e5."},
                   {"squares": ["a1", "c1"], "note": "Put a rook on the open c-file to meet ...c5."}],
        "attacks": [{"from": "d3", "to": "h7", "note": "The bishop points at the castled king."}],
        "aims": ["Complete the set-up first, then decide on a plan: e4 in the center or an attack on the kingside.",
                 "Trade the dark-squared bishops if Black offers, because your structure is solid.",
                 "Aim the bishop on d3 and a knight on e5 at the black king."],
        "watch": ["Do not hang the pawn on b2 when your bishop leaves c1.",
                  "Watch the ...c5 break hitting d4 and the ...Qb6 attack on b2."],
    },
    "two-knights-def": {
        "moves": ("e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Na5 Bb5+ c6 dxc6 bxc6 Be2 h6 Nf3 e4 Ne5 Bd6").split(),
        "routes": [{"squares": ["a5", "c4"], "note": "The knight returns to c4 where it attacks the bishop."},
                   {"squares": ["c8", "a6"], "note": "The bishop swings to a6 to stop White castling."}],
        "attacks": [{"from": "d6", "to": "e5", "note": "Attack the knight that has walked into the center."}],
        "aims": ["You gave a pawn to get a lead in development. Use it by attacking straight away.",
                 "Aim your pieces at the white bishop and the e5 knight and keep White's king in the center.",
                 "If White chooses the quiet 4.d3, just develop with ...Be7 and ...d5."],
        "watch": ["Do not rush your king: check that every move develops a piece or makes a threat.",
                  "After 4.Ng5, know that 4...d5 5.exd5 Na5 is the safe way to play."],
    },
    "sicilian-dragon": {
        "moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7 f3 O-O Qd2 Nc6".split(),
        "routes": [{"squares": ["h7", "h5"], "note": "The h-pawn advances to hit the white king if White castles long."}],
        "attacks": [{"from": "c6", "to": "d4", "note": "Trade the strong knight on d4."}],
        "aims": ["Castle, then trade the knight on d4 and use the c-file with your rooks.",
                 "Your bishop on g7 is your best piece. Keep the long diagonal open.",
                 "If White castles queenside, push h5 and go after the king."],
        "watch": ["Watch the Yugoslav Attack: Bc4, O-O-O and h4 are coming for your king.",
                  "Do not let White's h-pawn open the h-file without a plan."],
    },
    "qgd": {
        "moves": "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7 Rc1 c6 Bd3 dxc4 Bxc4 Nd5".split(),
        "routes": [{"squares": ["e6", "e5"], "note": "The freeing pawn break in the center."},
                   {"squares": ["d7", "b6"], "note": "The knight goes to b6 to challenge the bishop."}],
        "attacks": [{"from": "d5", "to": "c3", "note": "Trade White's active knight to relieve the pressure."}],
        "aims": ["Trade a couple of pieces to free your cramped game, then play ...e5 or ...c5.",
                 "Keep the pawn structure solid and your king safe.",
                 "Wait for White to over-extend and then hit back in the center."],
        "watch": ["Be careful about hanging the pawn on d5.", "Do not fall for the Elephant Trap yourself as White, and know it as Black."],
    },
    "kings-indian": {
        "moves": "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5 O-O Nc6 d5 Ne7".split(),
        "routes": [{"squares": ["f6", "e8"], "note": "Move the knight out of the way so the f-pawn can advance."},
                   {"squares": ["f7", "f5"], "note": "The pawn storm that starts the attack on the white king."}],
        "attacks": [{"from": "e7", "to": "d5", "note": "Put pressure on the white center pawn."}],
        "aims": ["Attack White's king with ...f5 while White attacks on the queenside. Whoever is faster wins.",
                 "Keep your bishop on g7 alive as long as you can.", "Do not trade queens when you are attacking."],
        "watch": ["Do not start ...f5 before your pieces are ready.", "Watch the c-pawn break c5 by White."],
    },
}

# What the family names in a player's own games look like, to spot openings they already play.
FAMILY_WORDS = {
    "italian": ("italian", "giuoco"), "evans": ("evans",), "two-knights": ("two knights", "fried liver"), "scotch": ("scotch",),
    "vienna": ("vienna",), "london": ("london",), "two-knights-def": ("two knights",), "sicilian-dragon": ("sicilian", "dragon"),
    "qgd": ("queen's gambit declined", "queen's gambit", "slav"), "kings-indian": ("king's indian", "kings indian"),
}

BEFORE = [
    "Sleep well the night before and eat a proper breakfast.",
    "Read your two opening plans once, not for the moves, for the ideas.",
    "Pack your scoresheet, a pen, water and a snack.",
    "Decide two rules for today (for example: 'check every capture' and 'castle by move 10').",
]
DURING = [
    "Before every move, ask: what does my opponent threaten?",
    "Write the move on your scoresheet, then look at the whole board once more before you play it.",
    "Spend time in tense positions (captures, checks, king safety). Play obvious moves quickly.",
    "If you make a mistake, breathe and find the best fighting move. The game is not over.",
]
AFTER = [
    "Write the opponent, color and result for every round straight away.",
    "Enter each game in Chess Varsity the same weekend so the coach can study it.",
    "Find the one turning point in each game and ask which question you skipped there.",
]


def target_position(opening_id: str) -> dict | None:
    """The position to aim for, ready to show on a board (FEN, arrows and words)."""
    play = PLAYBOOK.get(opening_id)
    if play is None:
        return None
    board, steps = chess.Board(), []
    for san in play["moves"]:
        move = board.push_san(san)
        steps.append({"san": san, "uci": move.uci(), "fen": board.fen()})
    arrows = []
    for route in play["routes"]:
        sq = route["squares"]
        arrows += [{"from": a, "to": b, "kind": "best"} for a, b in zip(sq, sq[1:])]
    arrows += [{"from": a["from"], "to": a["to"], "kind": "threat"} for a in play["attacks"]]
    return {"moves": play["moves"], "steps": steps, "fen": board.fen(), "arrows": arrows, "routes": play["routes"],
            "attacks": play["attacks"], "aims": play["aims"], "watch": play["watch"]}


def _family_record(opening_report: dict, opening_id: str, side: str) -> dict | None:
    words = FAMILY_WORDS.get(opening_id, ())
    found = [f for f in opening_report.get("families", []) if f["color"] == side and any(w in f["family"].lower() for w in words)]
    if not found:
        return None
    games = sum(f["games"] for f in found)
    points = sum(f["score"] * f["games"] for f in found) / games
    return {"games": games, "score": round(points)}


def recommend(side: str, habit_report: dict, opening_report: dict, how_many: int = 3) -> list[dict]:
    """Openings for `side`, best fit first, each with the reasons in plain words."""
    weak = {h["id"] for h in habit_report.get("habits", []) if h["level"] == "work"}
    needs_attack = bool(weak & {"attack", "passive"})
    needs_safety = bool(weak & {"blunders", "threats"})
    ranked = []
    for entry in academy.repertoire():
        if entry["side"] != side or entry["id"] not in PLAYBOOK:
            continue
        score, why = 0, []
        if entry["style"] == "attacking" and needs_attack:
            score += 3
            why.append("It gives you natural attacking chances, which is what your games need most.")
        if entry["style"] == "solid" and needs_safety:
            score += 2
            why.append("It is a solid set-up that keeps your king safe, which helps you avoid blunders.")
        record = _family_record(opening_report, entry["id"], side)
        if record and record["games"] >= 2:
            if record["score"] >= 50:
                score += 3
                why.append(f"You already play it and scored {record['score']}% in {record['games']} games. Stay with what works.")
            else:
                score -= 1
                why.append(f"You scored {record['score']}% in {record['games']} games with it, so learn its plan before using it again.")
        elif record:
            score += 1
            why.append("You have played it before, so it will feel familiar.")
        if not why:
            why.append("A dependable opening with clear plans that is easy to learn.")
        ranked.append((score, entry, why, record))
    ranked.sort(key=lambda t: (-t[0], t[1]["name"]))
    out = []
    for score, entry, why, record in ranked[:how_many]:
        out.append({"id": entry["id"], "name": entry["name"], "style": entry["style"], "side": side, "idea": entry["idea"],
                    "plans": entry["plans"], "traps": entry["traps"], "moves": entry["moves"], "why": why, "record": record,
                    "target": target_position(entry["id"])})
    return out


def schedule(days_until: int | None) -> list[dict]:
    """A simple countdown of what to do, from the number of days left (None when no date is known)."""
    plan = [
        (7, "A week before", "Choose your White and Black openings and play through each target position on the board."),
        (5, "Five days before", "Play two games against the computer starting from the target positions."),
        (3, "Three days before", "Do 5 puzzles a day and review your last game's biggest mistake."),
        (1, "The day before", "Rest. Read the seven-question routine once. Pack your bag."),
        (0, "Tournament day", "Follow the routine: threats first, blunder check every move."),
    ]
    if days_until is None:
        return [{"when": when, "task": task} for _, when, task in plan]
    return [{"when": when, "task": task, "days": d, "past": d > days_until} for d, when, task in plan]


def days_until(start_date: str, today: dt.date | None = None) -> int | None:
    """Whole days from today to a PGN-style date (2026.11.14), or None if the date is unknown."""
    parsed = pgnio.parse_date(start_date or "")
    if not parsed or parsed[2] is None:
        return None
    try:
        start = dt.date(*parsed)
    except ValueError:
        return None
    return (start - (today or dt.date.today())).days

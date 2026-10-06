"""Plain-language coaching text for analyzed moments.

Everything here is templated from facts the analyzer already established. An LLM
can later polish the wording, but it is never asked to judge the chess.
"""

from __future__ import annotations

SKILL_OF = {
    "missed_threat": "threat_recognition",
    "hung_piece": "blunder_check",
    "missed_tactic": "tactics",
    "missed_attack": "attacking",
    "defensive_spiral": "initiative",
    "mistake": None,
}

SKILL_LABEL = {
    "threat_recognition": "Spotting threats",
    "blunder_check": "Blunder check",
    "tactics": "Finding tactics",
    "attacking": "Attacking the king",
    "initiative": "Making your own threats",
}

TITLE = {
    "missed_threat": "Threat missed",
    "hung_piece": "Piece left in danger",
    "missed_tactic": "Tactic missed",
    "missed_attack": "Attack chance missed",
    "defensive_spiral": "Defensive spiral",
    "mistake": "Mistake",
}

QUESTION = {
    "missed_threat": "What is my opponent threatening?",
    "hung_piece": "After I move, can my opponent capture something or attack two things at once?",
    "missed_tactic": "Do I have a check, a capture, or a threat that wins something?",
    "missed_attack": "Can I create a threat against their king?",
    "defensive_spiral": "I just defended. What threat can I create now?",
    "mistake": "What is the most useful thing I can do with this move?",
}

LESSON = {
    "missed_threat": (
        "Before every move, look at what your opponent's last move attacks. "
        "Ask: 'If I do nothing, what can they do next?'"
    ),
    "hung_piece": (
        "Blunder check: before you let go of a piece, look at where it lands "
        "and what it leaves unprotected."
    ),
    "missed_tactic": "Look at every forcing move first: checks, then captures, then threats.",
    "missed_attack": (
        "When the other king is exposed, look for checks and threats before quiet moves. "
        "Bring more pieces toward the king."
    ),
    "defensive_spiral": (
        "Defending is not enough. After you deal with a threat, spend a moment "
        "finding one of your own so your opponent has to answer you."
    ),
    "mistake": "Slow down on this move and compare two or three candidate moves before choosing.",
}

THINK_MESSAGE = {
    "checks": "The key idea was a check. Always look at every check first, even if it looks strange.",
    "captures": "The key idea was a capture that wins material. Ask 'Can I win something?'",
    "threat": "The key idea was to notice the threat first. Ask 'What is my opponent threatening?'",
    "new_threats": "The key idea was to create a threat of your own.",
    "king_safety": "Your king was under pressure. Check its safety before anything else.",
}

PUZZLE_PROMPT = {
    "missed_threat": "It's your move. What is your opponent threatening, and how do you deal with it?",
    "hung_piece": "Find a safe move: one that doesn't leave anything to be captured.",
    "missed_tactic": "Find the strongest forcing move (check, capture or threat).",
    "missed_attack": "Find a move that attacks the enemy king.",
    "defensive_spiral": "You are not in danger. Find a move that makes a threat.",
    "mistake": "Find the best move.",
}


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _clause(t: dict) -> str:
    """What the opponent can do, as a sentence fragment ('their knight on g5 can ...')."""
    kind = t["kind"]
    if kind == "mate":
        return f"{t['san']} would be checkmate"
    if kind == "capture" and t["targets"]:
        target = t["targets"][0]
        note = "and nothing protects it" if not t["defended"] else "and would win material"
        return (
            f"their {t['piece']} on {t['from']} can capture your {target['piece']} on "
            f"{target['square']} {note}"
        )
    if kind == "fork":
        names = _join([f"{x['piece']} on {x['square']}" for x in t["targets"]])
        return (
            f"their {t['piece']} can go to {t['to']} and attack your {names} at the same time "
            "(a fork)"
        )
    return f"they were planning {t['san']}"


def _side_marker(moment: dict) -> str:
    return "." if moment["side"] == "white" else "..."


def _tactic_reasons(best: dict) -> list[str]:
    why = []
    if best["mate"]:
        why.append("It is checkmate.")
    elif best["check"]:
        why.append("It gives check, so your opponent has to respond right away.")
    if best["fork"]:
        why.append(f"It attacks their {_join(best['fork'])} at the same time (a fork).")
    if best["pin"]:
        why.append(f"It pins their {best['pin']}, so it cannot move.")
    if best["discovered"]:
        why.append(f"It uncovers an attack on their {best['discovered']}.")
    if best["captures"] and not best["mate"]:
        why.append(f"It captures a {best['captures']}.")
    if best["gain"] >= 1 and not best["mate"]:
        why.append(f"After the forcing moves you come out about {best['gain']} point(s) of material ahead.")
    if best["threat_san"] and not best["mate"]:
        why.append(f"It threatens {best['threat_san']}, so your opponent must react.")
    if "king_pressure" in best["reasons"]:
        why.append("It brings another piece into the attack on their king.")
    return why


def _attack_notes(moment: dict) -> list[str]:
    ap = moment["attack_potential"]
    notes = []
    if ap.get("king_exposure", 0) >= 10:
        notes.append("their king has lost its pawn cover or never castled")
    if ap.get("open_files", 0) >= 8:
        notes.append("there are open lines near their king")
    if ap.get("attackers", 0) >= 10:
        notes.append("several of your pieces already point at their king")
    if ap.get("checks_available", 0) > 0:
        notes.append("you have checks available")
    return notes


def _ways(moment: dict) -> list[dict]:
    return [c for c in moment["candidates"] if c["good"]]


def _candidate_note(c: dict) -> str:
    bits = {
        "defends": "stops the threat",
        "counterattacks": "answers the threat with an attack of your own",
        "attacks": "keeps the initiative",
        "improves": "a calm, useful move",
    }
    note = bits.get(c["role"], "")
    extras = []
    if c["gives_check"]:
        extras.append("gives check")
    if c["captures"]:
        extras.append(f"captures a {c['captures']}")
    if c["threat_san"]:
        extras.append(f"threatens {c['threat_san']}")
    if extras:
        note += f" - {', '.join(extras)}"
    return note


def winning_story(m: dict) -> dict:
    """Text for a 'how you could have won' position."""
    played, best = m["played"]["san"], m["best"]["san"]
    before, after = int(round(m["wp_before"])), int(round(m["wp_after"]))
    story = []
    if m["kind"] == "threw_away_win":
        story.append(f"You were winning here (your winning chances were about {before}%).")
        story.append(f"After {played} that dropped to about {after}%.")
        headline = f"A win slipped away at move {m['move_number']}"
    elif m["kind"] == "better_position":
        story.append(f"You were clearly better here (about {before}% winning chances).")
        story.append(f"{played} let much of that advantage go ({after}%).")
        headline = f"A better position at move {m['move_number']}"
    else:
        story.append(f"This is where the game turned: you were {m['state_before']}, and after {played} you were {m['state_after']}.")
        headline = f"The turning point at move {m['move_number']}"
    story.append(f"The strongest idea was {best}.")
    story.extend(_tactic_reasons(m["best"])[:3])
    m["headline"] = headline
    m["story"] = story
    m["line_text"] = _line_text(m["fen"], m["variation"])
    m["lesson"] = (
        "When you are better, look for the most forcing continuation: checks, captures and threats. "
        "Before a quiet move, ask 'Can I make my advantage bigger right now?'"
    )
    return m


def _line_text(fen: str, line: list[dict]) -> str:
    """'21. Qxh7+ Kxh7 22. Rh3+ ...' from a start FEN and a list of moves."""
    parts = fen.split(" ")
    white_turn = parts[1] == "w"
    number = int(parts[5])
    out = []
    for i, step in enumerate(line):
        if white_turn:
            out.append(f"{number}. {step['san']}")
        else:
            out.append(f"{number}... {step['san']}" if i == 0 else step["san"])
            number += 1
        white_turn = not white_turn
    return " ".join(out)


def narrate(moment: dict) -> dict:
    cat = moment["category"]
    m = moment
    marker = _side_marker(m)
    story: list[str] = []
    played, best = m["played"]["san"], m["best"]["san"]
    opp = m["opponent_last"]["san"] if m["opponent_last"] else None

    if cat == "missed_threat":
        t = m["threat"]
        if opp:
            story.append(f"Your opponent had just played {opp}.")
        story.append(f"That set up a threat: {_clause(t)}.")
        story.append(f"You played {played}, which did not deal with it.")
        if m["reply"] and m["reply"]["san"] == t["san"]:
            story.append(f"Your opponent carried out the threat with {m['reply']['san']}.")
        if m.get("repeats"):
            story.append(
                f"The same threat was still there on your next {m['repeats']} move(s) "
                "and it was not dealt with."
            )
        if m["reply"] and m["reply"]["san"].endswith("#"):
            story.append("The game ended in checkmate.")
        else:
            story.append(f"Your position went from {m['state_before']} to {m['state_after']}.")
        headline = f"Threat missed: {t['san']} was coming"
    elif cat == "hung_piece":
        a = m["allowed"]
        story.append(f"You played {played}.")
        story.append(f"After that, {_clause(a)}.")
        if m["reply"] and m["reply"]["san"] == a["san"]:
            story.append(f"Your opponent did exactly that with {a['san']}.")
        story.append(f"Your position went from {m['state_before']} to {m['state_after']}.")
        headline = f"{played} left something in danger"
    elif cat == "missed_tactic":
        story.append(f"You played {played}, but {best} was much stronger. Why it works:")
        story.extend(_tactic_reasons(m["best"]))
        headline = f"Tactic missed: {best}"
    elif cat == "missed_attack":
        notes = _attack_notes(m)
        story.append(
            f"You were not in danger, and your opponent's king was exposed "
            f"(attack score {m['attack_potential']['total']}/100)."
        )
        if notes:
            story.append(f"Why it was a good moment to attack: {_join(notes)}.")
        story.append(f"You played {played}, a quieter move.")
        story.append(f"{best} was the stronger, more active choice:")
        story.extend(_tactic_reasons(m["best"])[:2] or ["It keeps the initiative."])
        headline = f"Attack chance: {best}"
    elif cat == "defensive_spiral":
        s = m["spiral"]
        answers = _join([f"{x['number']}{marker}{x['san']}" for x in s["moves"]])
        story.append(
            f"From move {s['start']} to move {s['end']} you answered {s['length']} threats in a row "
            f"({answers})."
        )
        story.append("You handled each one, but you never made a threat of your own.")
        if s["chance_at"]:
            story.append(f"At move {s['chance_at']} you had a chance to fight back with {best}.")
        headline = f"Defensive spiral: moves {s['start']}-{s['end']}"
    else:
        story.append(f"You played {played}. Your position went from {m['state_before']} to {m['state_after']}.")
        story.append(f"{best} was the better move.")
        story.extend(_tactic_reasons(m["best"]))
        headline = f"{played} was a mistake"

    shift = m["balance"]["shift"]
    if cat in ("hung_piece", "mistake") and shift:
        story.append(shift[0]["text"])
    m["balance_text"] = m["balance"]["before"]["verdict"]["text"]

    ways = _ways(m)
    if cat == "missed_threat" and ways:
        ways_text = "; ".join(f"{c['san']} ({_candidate_note(c)})" for c in ways[:3])
        story.append(f"You had {len(ways[:3])} good way(s) to respond: {ways_text}.")

    think_key = m["think"]["key"]
    m["headline"] = headline
    m["story"] = story
    m["question"] = QUESTION[cat]
    m["lesson"] = LESSON[cat]
    m["think_message"] = None if cat in ("defensive_spiral", "mistake") else THINK_MESSAGE.get(think_key)
    m["skill"] = SKILL_OF[cat]
    m["title"] = TITLE[cat]
    m["puzzle"] = {
        "prompt": PUZZLE_PROMPT[cat],
        "fen": m["fen"],
        "good_moves": [c["uci"] for c in m["candidates"] if c["good"]] or [m["best"]["uci"]],
        "answer": (
            f"Your opponent threatened: {_clause(m['threat'])}." if m["threat"] and cat == "missed_threat" else None
        ),
        "threat_uci": m["threat"]["uci"] if m["threat"] else None,
    }
    return m


def summarize(result: dict) -> dict:
    moments = result["moments"]
    by_cat: dict[str, list[dict]] = {}
    for mo in moments:
        by_cat.setdefault(mo["category"], []).append(mo)

    game = result["game"]
    lines = []
    marker = "." if game["player_color"] == "white" else "..."
    weights = {"missed_threat": 3, "defensive_spiral": 3, "missed_attack": 2, "hung_piece": 2, "missed_tactic": 2}
    ranked = sorted(by_cat, key=lambda c: (weights.get(c, 1) * len(by_cat[c])), reverse=True)

    for cat in ranked:
        items = by_cat[cat]
        where = _join([f"{x['move_number']}{marker}{x['played']['san']}" for x in items[:4]])
        n = len(items)
        if cat == "missed_threat":
            text = f"{n} important threat(s) missed — your moves {where}."
        elif cat == "hung_piece":
            text = f"{n} time(s) a move left something in danger — {where}."
        elif cat == "missed_tactic":
            text = f"{n} tactic(s) missed — {where}."
        elif cat == "missed_attack":
            text = f"{n} attacking chance(s) passed by — {where}."
        elif cat == "defensive_spiral":
            spans = _join([f"moves {x['spiral']['start']}-{x['spiral']['end']}" for x in items])
            text = f"Defensive spiral in {spans}: answering threats without making your own."
        else:
            text = f"{n} other mistake(s) — {where}."
        lines.append({"category": cat, "skill": SKILL_OF[cat], "text": text, "title": TITLE[cat]})

    if ranked:
        top = ranked[0]
        focus = LESSON[top]
    else:
        focus = "No big moments found. Keep asking 'What is my opponent threatening?' before every move."

    training = []
    for cat in ranked:
        skill = SKILL_OF[cat]
        if skill:
            training.append(
                {
                    "skill": skill,
                    "label": SKILL_LABEL[skill],
                    "positions": len(by_cat[cat]),
                }
            )

    if not moments:
        headline = "A clean game. No big problems stood out."
    elif ranked[0] in ("missed_threat", "defensive_spiral"):
        headline = "Your biggest issue was reacting to your opponent instead of creating threats."
    elif ranked[0] == "hung_piece":
        headline = "Your biggest issue was leaving pieces where they could be captured."
    elif ranked[0] == "missed_attack":
        headline = "You had attacking chances but played too quietly."
    elif ranked[0] == "missed_tactic":
        headline = "Your biggest issue was missing tactics."
    else:
        headline = "You played a few inaccurate moves; see below."

    return {"headline": headline, "problems": lines, "todays_lesson": focus, "training": training}

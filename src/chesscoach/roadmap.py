"""The Chess Development Roadmap: a personal curriculum from the player's rating, their games and their own progress.

    roadmap = rating level (what to learn) + habits from their games (what is actually going wrong)
              + topics they have marked (where they are)

Every topic is written once, with the level where it is introduced. At any level a topic is then "review" (from an
earlier level), "learn now" (introduced here) or "preview" (the next level). Priorities come from the player's own
habit scores, weighted by what matters most at their level, so two players with the same rating get different plans.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------------------------------------------

BANDS = [
    {"key": "u500", "label": "Under 500", "lo": 0, "hi": 499},
    {"key": "500", "label": "500–799", "lo": 500, "hi": 799},
    {"key": "800", "label": "800–999", "lo": 800, "hi": 999},
    {"key": "1000", "label": "1000–1199", "lo": 1000, "hi": 1199},
    {"key": "1200", "label": "1200–1399", "lo": 1200, "hi": 1399},
    {"key": "1400", "label": "1400–1599", "lo": 1400, "hi": 1599},
    {"key": "1600", "label": "1600–1799", "lo": 1600, "hi": 1799},
    {"key": "1800", "label": "1800–1999", "lo": 1800, "hi": 1999},
    {"key": "2000", "label": "2000+", "lo": 2000, "hi": None},
]

# Practice guidelines for each level (guidelines, not rules).
BAND_META = [
    {"puzzles": 5, "difficulty": "one-move puzzles: capture a free piece, deliver mate in 1", "depth": "1 move: look at checks, captures and threats",
     "engine": "Don't use an engine during study; ask a coach or check the solution afterwards.",
     "repertoire": "No repertoire yet: follow the opening principles in every game.",
     "focus": "Stop leaving pieces where they can be taken, and take pieces your opponent leaves."},
    {"puzzles": 8, "difficulty": "mate in 1 and simple two-move tactics", "depth": "1–2 moves",
     "engine": "Solve first, always. Use an engine only to check a game after you have looked at it yourself.",
     "repertoire": "One opening as White, one answer to 1.e4, one answer to 1.d4; principles before memorizing.",
     "focus": "Check every move for what is attacked and what is undefended."},
    {"puzzles": 10, "difficulty": "two-move tactics: forks, pins, mate in 2", "depth": "2 moves (checks, captures, threats)",
     "engine": "Find your own answer before looking; review your games yourself before the engine.",
     "repertoire": "Keep one opening per color and learn its typical plans, not long lines.",
     "focus": "See your opponent's threat before every move, and look for your own forcing moves."},
    {"puzzles": 12, "difficulty": "2–3 move combinations", "depth": "2–3 moves; compare 2–3 candidate moves",
     "engine": "Calculate forcing moves on your own first; the engine checks your work.",
     "repertoire": "A small, stable repertoire; learn the common traps in your openings.",
     "focus": "Turn tactics into habits and start making simple plans."},
    {"puzzles": 15, "difficulty": "3–4 move combinations with a defensive resource", "depth": "3–4 moves in forcing lines",
     "engine": "Write down your analysis of a game before switching the engine on.",
     "repertoire": "A structured repertoire: typical pawn structures and middlegame plans of each opening.",
     "focus": "Calculate forcing lines accurately and understand the plans behind your openings."},
    {"puzzles": 15, "difficulty": "4–5 move combinations; quiet moves inside tactics", "depth": "4–5 moves where the position is forcing",
     "engine": "Use the engine to test your ideas, not to find them.",
     "repertoire": "Expand your repertoire; understand move orders and transpositions.",
     "focus": "Long-term weaknesses, prophylaxis and converting advantages."},
    {"puzzles": 12, "difficulty": "complex combinations and defensive puzzles", "depth": "5+ moves in forcing lines; evaluate the end position",
     "engine": "Prepare with the engine selectively; understand why its moves work.",
     "repertoire": "A deeper repertoire with alternatives, prepared with purpose.",
     "focus": "Strategic planning, the initiative and practical decision-making."},
    {"puzzles": 10, "difficulty": "hard combinations, studies, positional puzzles", "depth": "Deep calculation of critical lines; prune the rest",
     "engine": "Engine-assisted preparation and deep game analysis.",
     "repertoire": "Opponent-specific preparation and understanding novelties.",
     "focus": "Deep calculation, advanced endgames and preparation."},
    {"puzzles": 10, "difficulty": "studies and very hard combinations", "depth": "As deep as the position demands",
     "engine": "Engine-assisted preparation as a professional tool.",
     "repertoire": "A broad repertoire, prepared for specific opponents.",
     "focus": "Refine everything: preparation, endgame technique and practical play."},
]

# ---------------------------------------------------------------------------------------------------------------
# The eight areas, and the habit (from game analysis) that measures each one
# ---------------------------------------------------------------------------------------------------------------

CATEGORIES = [
    {"key": "tactics", "title": "Tactics", "habits": ["tactics"], "workbook": "tactics"},
    {"key": "thinking", "title": "Thinking process", "habits": ["threats"], "workbook": "threat_recognition"},
    {"key": "calculation", "title": "Calculation", "habits": ["blunders", "tactics"], "workbook": "blunder_check"},
    {"key": "opening", "title": "Opening", "habits": ["opening"], "workbook": None},
    {"key": "middlegame", "title": "Middlegame", "habits": ["passive", "converting"], "workbook": "initiative"},
    {"key": "attack", "title": "Attack & defense", "habits": ["attack", "passive"], "workbook": "initiative"},
    {"key": "endgame", "title": "Endgame", "habits": ["endgame"], "workbook": None},
    {"key": "repertoire", "title": "Opening repertoire", "habits": ["opening"], "workbook": None},
]
CATEGORY = {c["key"]: c for c in CATEGORIES}

# How much each area matters at each level (1 = normal). Tactics and threats dominate early; strategy and
# endgames grow with rating.
RELEVANCE = {
    "tactics":     [1.6, 1.6, 1.5, 1.5, 1.4, 1.2, 1.1, 1.0, 1.0],
    "thinking":    [1.6, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 1.0],
    "calculation": [1.2, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3, 1.3],
    "opening":     [0.8, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0, 1.1, 1.2],
    "middlegame":  [0.6, 0.7, 0.8, 1.0, 1.1, 1.2, 1.3, 1.3, 1.3],
    "attack":      [0.8, 0.9, 1.0, 1.1, 1.1, 1.1, 1.1, 1.1, 1.1],
    "endgame":     [0.8, 0.9, 1.0, 1.0, 1.1, 1.2, 1.2, 1.3, 1.3],
    "repertoire":  [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2],
}

# ---------------------------------------------------------------------------------------------------------------
# Topics: (key, area, level where it starts, title, what to be able to do)
# ---------------------------------------------------------------------------------------------------------------

_T = [
    # Opening fundamentals
    ("op_center", "opening", 0, "Control the center", "Put pawns and pieces on or towards e4, d4, e5 and d5."),
    ("op_develop", "opening", 0, "Develop knights and bishops", "Bring every minor piece out before starting an attack."),
    ("op_castle", "opening", 0, "Castle early", "Get your king safe, usually by move 10."),
    ("op_once", "opening", 1, "Don't move the same piece twice", "Each opening move should bring a new piece into play."),
    ("op_queen", "opening", 1, "Don't bring the queen out early", "An early queen gets chased and loses time."),
    ("op_replies", "opening", 1, "Basic replies to 1.e4 and 1.d4", "Know one sensible answer to each first move."),
    ("op_threats", "opening", 2, "Spot opening threats", "Recognize Scholar's mate, early forks and pins on the e-file."),
    ("op_structures", "opening", 2, "Common opening structures", "Know the pawn shapes your openings lead to."),
    ("op_breaks", "opening", 3, "Basic pawn breaks", "Know which pawn move frees your position (…d5, …c5, f4…)."),
    ("op_plans", "opening", 3, "Plans instead of move orders", "After the opening, know what you are trying to do."),
    ("op_traps", "opening", 4, "Common opening traps", "Know the traps in your openings, for both sides."),
    ("op_middlegame", "opening", 4, "Middlegame plans from your openings", "Know the typical plan of each opening you play."),
    ("op_moveorder", "opening", 5, "Move-order differences", "Understand why the order of moves matters."),
    ("op_transpose", "opening", 6, "Transpositions", "Recognize when a different move order reaches the same position."),
    ("op_theory", "opening", 7, "Deeper theory and novelties", "Know the critical lines and where new ideas come from."),
    ("op_prep", "opening", 8, "Opponent-specific preparation", "Prepare lines for a particular opponent."),
    # Tactics
    ("t_hanging", "tactics", 0, "Hanging pieces", "Notice pieces that can be taken for free: yours and theirs."),
    ("t_ccf", "tactics", 0, "Checks, captures and threats", "List the forcing moves before you choose a move."),
    ("t_mate1", "tactics", 0, "Mate in one", "Spot one-move checkmates, especially on the back rank."),
    ("t_fork", "tactics", 1, "Forks", "Attack two things at once, especially with knights and pawns."),
    ("t_double", "tactics", 1, "Double attacks", "Make one move create two threats."),
    ("t_pin", "tactics", 2, "Pins", "Pin a piece to the king or a bigger piece, and attack it."),
    ("t_skewer", "tactics", 2, "Skewers", "Attack a big piece so the one behind it falls."),
    ("t_backrank", "tactics", 2, "Back-rank tactics", "Punish a king trapped behind its own pawns."),
    ("t_discovered", "tactics", 3, "Discovered attacks", "Move one piece to unleash another; discovered checks."),
    ("t_removing", "tactics", 3, "Removing the defender", "Capture or chase away the piece that guards the target."),
    ("t_deflection", "tactics", 4, "Deflection", "Force a defender away from its duty."),
    ("t_attraction", "tactics", 4, "Attraction (decoy)", "Lure a piece, often the king, onto a bad square."),
    ("t_combos", "tactics", 4, "Basic combinations", "Combine two tactics in one forcing sequence."),
    ("t_zwischenzug", "tactics", 5, "In-between moves", "Insert a stronger move before the expected recapture."),
    ("t_xray", "tactics", 5, "X-ray attacks", "Use a piece's power through another piece."),
    ("t_clearance", "tactics", 6, "Clearance", "Clear a square or line for another piece, often with a sacrifice."),
    ("t_sacrifice", "tactics", 6, "Sacrificial combinations", "Give material for a mating attack or a winning endgame."),
    ("t_quiet", "tactics", 7, "Quiet moves in combinations", "Find the non-forcing move that makes a combination work."),
    # Middlegame
    ("m_activity", "middlegame", 1, "Active pieces", "Put pieces where they control many squares."),
    ("m_kingsafety", "middlegame", 1, "King safety", "Keep pawns in front of your castled king; don't open it needlessly."),
    ("m_worst", "middlegame", 3, "Improve your worst piece", "Find your least active piece and give it a job."),
    ("m_files", "middlegame", 3, "Open files and diagonals", "Put rooks on open files and bishops on open diagonals."),
    ("m_structure", "middlegame", 4, "Pawn structure", "Isolated, doubled and passed pawns, and what they mean for plans."),
    ("m_outposts", "middlegame", 4, "Outposts and weak squares", "Find squares pawns can't attack and put a piece there."),
    ("m_bishops", "middlegame", 4, "Good and bad bishops", "Know when a bishop is blocked by its own pawns."),
    ("m_breaks", "middlegame", 4, "Pawn breaks", "Use pawn moves to open lines where you are stronger."),
    ("m_prophylaxis", "middlegame", 5, "Prophylaxis", "Ask what your opponent wants, and stop it first."),
    ("m_weaknesses", "middlegame", 5, "Creating and attacking weaknesses", "Make targets, then pile up on them."),
    ("m_exchanges", "middlegame", 5, "Strategic exchanges", "Trade the right pieces: your bad ones, their good ones."),
    ("m_transform", "middlegame", 6, "Transforming advantages", "Turn one kind of advantage into another that wins."),
    ("m_static", "middlegame", 6, "Static vs dynamic advantages", "Know whether time is on your side or your opponent's."),
    ("m_positional_sac", "middlegame", 7, "Positional sacrifices", "Give material for lasting positional gains."),
    ("m_planning", "middlegame", 7, "Strategic planning", "Build a plan from the imbalances in the position."),
    # Endgame
    ("e_kq", "endgame", 0, "King and queen vs king", "Mate with a queen without stalemating."),
    ("e_kr", "endgame", 1, "King and rook vs king", "Mate with a rook using the box method."),
    ("e_kp", "endgame", 2, "King and pawn vs king", "Know when the pawn promotes and when it's a draw."),
    ("e_square", "endgame", 2, "Rule of the square", "Tell at a glance if a king catches a pawn."),
    ("e_opposition", "endgame", 3, "Opposition", "Use the kings' opposition to win or hold pawn endings."),
    ("e_keysquares", "endgame", 3, "Key squares", "Know the squares the king must reach to promote."),
    ("e_outside", "endgame", 4, "Outside passed pawn", "Use a distant passed pawn to decoy the enemy king."),
    ("e_rookbehind", "endgame", 4, "Rook behind the passed pawn", "Put rooks behind passed pawns, yours or theirs."),
    ("e_lucena", "endgame", 4, "Lucena position", "Win with rook and pawn by building a bridge."),
    ("e_philidor", "endgame", 4, "Philidor position", "Draw rook against rook and pawn with the third-rank defense."),
    ("e_zugzwang", "endgame", 5, "Zugzwang and breakthroughs", "Win pawn endings by running your opponent out of moves."),
    ("e_activerook", "endgame", 5, "Active rook, cutting off the king", "Keep your rook active; cut the enemy king off from the pawn."),
    ("e_bishops", "endgame", 5, "Same- and opposite-colored bishops", "Know which bishop endings are won and which are drawn."),
    ("e_knightbishop", "endgame", 6, "Knight vs bishop endings", "Know when each minor piece is better."),
    ("e_2bishops", "endgame", 6, "Two bishops vs king", "Mate with the bishop pair."),
    ("e_bn", "endgame", 7, "Bishop and knight vs king", "Mate with bishop and knight in the right corner."),
    ("e_theory", "endgame", 8, "Theoretical rook and minor-piece endings", "Vancura, Q vs R and other practical theory."),
    # Calculation
    ("c_forcing", "calculation", 1, "Calculate checks, captures and threats", "Work out what happens after each forcing move."),
    ("c_candidates", "calculation", 3, "Candidate moves", "Choose 2–3 candidate moves before calculating."),
    ("c_reply", "calculation", 4, "Find the opponent's best reply", "Always ask what your opponent does next."),
    ("c_visualise", "calculation", 4, "Visualise without moving pieces", "Hold the position in your head 3–4 moves ahead."),
    ("c_variations", "calculation", 5, "Several variations", "Compare the lines and choose on the final position."),
    ("c_blunder", "calculation", 2, "Blunder check", "Before you move, check what the move leaves undefended."),
    ("c_evaluate", "calculation", 6, "Evaluate the end position", "Judge who is better when the calculation stops."),
    ("c_deep", "calculation", 7, "Deep, pruned calculation", "Calculate the critical lines deeply and prune the rest."),
    # Thinking process
    ("th_last", "thinking", 0, "What did my opponent just do?", "Look at your opponent's last move before thinking about yours."),
    ("th_attacked", "thinking", 0, "Is anything attacked or hanging?", "Check every piece that is attacked or undefended."),
    ("th_threat", "thinking", 1, "What is my opponent threatening?", "Name the threat before choosing your move."),
    ("th_mine", "thinking", 1, "What checks, captures and threats do I have?", "Look for your own forcing moves every turn."),
    ("th_candidates", "thinking", 3, "Generate and compare candidate moves", "Pick 2–3 moves and compare them."),
    ("th_blundercheck", "thinking", 3, "Final blunder check", "Look once more at the chosen move before playing it."),
    ("th_plan", "thinking", 4, "Make a plan", "Know what you want to do in the next few moves."),
    ("th_prophylaxis", "thinking", 5, "Prophylactic thinking", "Think about your opponent's plan, not just yours."),
    ("th_positional", "thinking", 6, "Positional evaluation", "Weigh the imbalances to choose the right plan."),
    ("th_time", "thinking", 6, "Time management", "Spend time on critical moments, move quickly in simple ones."),
    # Attack & defence
    ("a_undefended", "attack", 0, "Identify undefended pieces", "Find the loose pieces on both sides."),
    ("a_weakking", "attack", 2, "Identify a weak king", "Spot a king with few defenders or broken pawns."),
    ("a_count", "attack", 2, "Count attackers and defenders", "Know whether a capture really wins."),
    ("a_threats", "attack", 3, "Create threats", "Make moves that force your opponent to react."),
    ("a_overload", "attack", 3, "Overloaded defenders", "Find a piece guarding two things and overload it."),
    ("a_bringpieces", "attack", 3, "Bring more pieces into the attack", "Ask which piece should join the attack next."),
    ("a_openlines", "attack", 4, "Open lines towards the king", "Use pawn breaks and sacrifices to open the king."),
    ("a_pawnstorm", "attack", 4, "Pawn storms", "Push pawns at a king castled on the other side."),
    ("a_defence", "attack", 4, "Defensive resources", "Find the move that holds, not just the one that hopes."),
    ("a_whennot", "attack", 5, "When NOT to attack", "Know when the position calls for patience instead."),
    ("a_sacking", "attack", 5, "Sacrifices near the king", "Classic sacrifices on h7, f7, g7 and e6."),
    ("a_counter", "attack", 6, "Counterattacking", "Answer an attack with a faster one of your own."),
    ("a_transition", "attack", 6, "From attack to a winning position", "Cash in the attack for a won endgame when it's right."),
    # Repertoire
    ("r_one", "repertoire", 1, "One opening per color", "Choose one White opening and one answer to 1.e4 and 1.d4."),
    ("r_plans", "repertoire", 3, "Plans and traps of your openings", "Know the ideas and the common traps."),
    ("r_structure", "repertoire", 4, "A structured repertoire", "Learn the typical pawn structures and plans."),
    ("r_expand", "repertoire", 5, "Expand and understand move orders", "Add variations; understand the move orders."),
    ("r_engine", "repertoire", 6, "Engine-assisted preparation", "Use an engine selectively, understanding the moves."),
    ("r_opponent", "repertoire", 7, "Preparation for opponents", "Prepare lines for specific opponents."),
]
TOPICS = [{"key": k, "category": c, "start": s, "title": t, "goal": g} for k, c, s, t, g in _T]
TOPIC = {t["key"]: t for t in TOPICS}

STATUSES = ["not_started", "learning", "practicing", "developing", "mastered"]

# The thinking routine grows with level.
THINKING_STEPS = [
    ["What did my opponent just do?", "Is anything attacked?", "Is anything hanging?", "What is my opponent threatening?",
     "What checks, captures and threats do I have?"],
    ["Identify my opponent's threat", "Generate candidate moves", "Calculate the forcing moves", "Compare the candidates",
     "Look for tactical consequences", "Evaluate the resulting position", "Blunder check", "Make the move"],
    ["Understand the position: imbalances and plans for both sides", "Prophylaxis: what does my opponent want?",
     "Candidate moves, including quiet and positional ones", "Calculate the critical lines; prune the rest",
     "Evaluate the end positions", "Blunder check and time check", "Make the move"],
]

# Practical questions for attack and defence.
ATTACK_QUESTIONS = ["Who has the initiative?", "What is my opponent's biggest threat?", "Can I create a forcing threat?",
                    "Which piece should join the attack?", "What happens if my attack fails?"]


def band_for(rating: int | None) -> int | None:
    if rating is None:
        return None
    for i, b in enumerate(BANDS):
        if rating >= b["lo"] and (b["hi"] is None or rating <= b["hi"]):
            return i
    return 0


def _performance(habits: dict) -> dict[str, dict]:
    """Per area: a 0-100 score from the player's games, with the evidence behind it (None where there's no data)."""
    by_id = {h["id"]: h for h in habits.get("habits", [])} if habits.get("ready") else {}
    out = {}
    for c in CATEGORIES:
        found = [by_id[h] for h in c["habits"] if h in by_id]
        if not found:
            out[c["key"]] = None
            continue
        out[c["key"]] = {
            "score": round(sum(h["score"] for h in found) / len(found)),
            "detail": " ".join(h["detail"] for h in found),
            "headline": found[0]["headline"],
            "examples": [e for h in found for e in h["evidence"]][:3],
        }
    return out


def _progress_score(statuses: dict[str, str], keys: list[str]) -> int | None:
    if not keys:
        return None
    return round(100 * sum(STATUSES.index(statuses.get(k, "not_started")) for k in keys) / (4 * len(keys)))


def _priority_label(weight: float) -> str:
    return "High" if weight >= 60 else "Medium" if weight >= 30 else "Low"


# Where each area is practised in the app, so the roadmap links straight to it (and those pages link back).
PRACTICE = {
    "tactics": {"href": "#/academy/tactics", "label": "Attack academy: Winning material"},
    "calculation": {"href": "#/academy/attack", "label": "Attack academy: Attack the king"},
    "attack": {"href": "#/academy/attack", "label": "Attack academy: Attack the king"},
    "opening": {"href": "#/openings/library", "label": "Openings: Library"},
    "repertoire": {"href": "#/openings/repertoire", "label": "Openings: Repertoire ideas"},
    "middlegame": {"href": "#/models", "label": "Model games"},
    "thinking": {"href": "#/think", "label": "Think like a Grandmaster"},
}
TOPIC_PRACTICE = {
    "t_mate1": {"href": "#/academy/mates", "label": "Attack academy: Mating patterns"},
    "t_backrank": {"href": "#/academy/mates", "label": "Attack academy: Mating patterns"},
    "op_traps": {"href": "#/academy/traps", "label": "Attack academy: Opening traps"},
    "op_replies": {"href": "#/openings/repertoire", "label": "Openings: Repertoire ideas"},
    "op_middlegame": {"href": "#/openings/repertoire", "label": "Openings: Repertoire ideas"},
    "r_plans": {"href": "#/academy/traps", "label": "Attack academy: Opening traps"},
}


def practice_for(topic: dict) -> dict | None:
    return TOPIC_PRACTICE.get(topic["key"]) or PRACTICE.get(topic["category"])


def build(rating: int | None, rating_system: str, viewing: int | None, habits: dict, statuses: dict[str, str],
          games: int) -> dict:
    """Everything the roadmap page shows, for the level being viewed (by default the player's own)."""
    current = band_for(rating)
    band = viewing if viewing is not None else (current if current is not None else 2)
    band = max(0, min(len(BANDS) - 1, band))
    meta = BAND_META[band]
    perf = _performance(habits)

    categories = []
    for c in CATEGORIES:
        mine = [t for t in TOPICS if t["category"] == c["key"]]
        review = [t for t in mine if t["start"] < band]
        now = [t for t in mine if t["start"] == band]
        preview = [t for t in mine if t["start"] == band + 1]
        scope = [t["key"] for t in review + now]
        progress = _progress_score(statuses, scope)
        p = perf[c["key"]]
        mastery = progress if p is None else (p["score"] if progress is None else round(0.6 * p["score"] + 0.4 * progress))
        weight = (100 - p["score"]) * RELEVANCE[c["key"]][band] if p else None
        done = sum(1 for k in scope if statuses.get(k) == "mastered")
        topic = lambda t: {**t, "status": statuses.get(t["key"], "not_started"), "practice": practice_for(t)}
        categories.append({
            "key": c["key"], "title": c["title"], "mastery": mastery, "performance": p, "progress": progress,
            "priority": _priority_label(weight) if weight is not None else None, "weight": weight,
            "completed": done, "total": len(scope),
            "review": [topic(t) for t in review], "now": [topic(t) for t in now], "preview": [topic(t) for t in preview],
            "workbook": c["workbook"], "practice": PRACTICE.get(c["key"]),
        })

    # The next three priorities: from the games where there are any, otherwise from what matters at this level.
    measured = sorted((c for c in categories if c["weight"] is not None), key=lambda c: -c["weight"])
    if measured:
        chosen = measured[:3]
    else:
        chosen = sorted(categories, key=lambda c: -RELEVANCE[c["key"]][band])[:3]
    priorities = [_priority(c, band, meta, games) for c in chosen]

    return {
        "rating": rating, "rating_system": rating_system, "current_band": current, "band": band,
        "bands": [{"index": i, **b} for i, b in enumerate(BANDS)],
        "is_current": current == band, "is_future": current is not None and band > current,
        "next_milestone": BANDS[band + 1]["lo"] if band + 1 < len(BANDS) else None,
        "future_milestone": BANDS[band + 2]["lo"] if band + 2 < len(BANDS) else None,
        "meta": meta, "categories": categories, "priorities": priorities,
        "thinking": THINKING_STEPS[0 if band <= 2 else 1 if band <= 5 else 2],
        "attack_questions": ATTACK_QUESTIONS,
        "weekly_plan": _weekly_plan(band, meta, [c["key"] for c in chosen]),
        "personal": bool(measured), "games": games, "statuses": STATUSES,
    }


FOCUS = {
    "tactics": lambda b, m: [f"Solve {m['puzzles']} puzzles a day: {m['difficulty']}",
                             "Before each move, list checks, captures and threats"],
    "thinking": lambda b, m: ["Before every move, say your opponent's threat out loud (or write it)",
                              "Review the threats you missed in your recent games"],
    "calculation": lambda b, m: [f"Calculation goal: {m['depth']}", "Blunder-check every move before you play it"],
    "opening": lambda b, m: ["Follow the opening principles: center, development, castling",
                             "Look up where your games left the book, and why"],
    "middlegame": lambda b, m: ["Each move, find your worst piece and improve it", "Look for an active plan instead of waiting"],
    "attack": lambda b, m: ["Ask which piece should join the attack next", "Study attacking model games at your level"],
    "endgame": lambda b, m: ["Study one endgame from this level's list each week", "Play out won endgames against the computer"],
    "repertoire": lambda b, m: [m["repertoire"], "Write down the main plan of each opening you play"],
}
TARGET = {
    "tactics": "80%+ of clear tactical chances found in your next 10 games",
    "thinking": "Deal with at least 8 of every 10 real threats in your games",
    "calculation": "No pieces left hanging in your next 5 games",
    "opening": "Develop all minor pieces and castle in every game",
    "middlegame": "Fewer passive moves and more wins from good positions",
    "attack": "Create at least one real attacking plan per game",
    "endgame": "Hold your accuracy in endgames as well as in middlegames",
    "repertoire": "Play your chosen openings in every game for a month",
}


def _priority(c: dict, band: int, meta: dict, games: int) -> dict:
    p = c["performance"]
    learn = [t["title"] for t in c["now"]] or [t["title"] for t in c["review"][-3:]]
    return {
        "category": c["key"], "title": c["title"], "priority": c["priority"] or "Focus",
        "why": (f"{p['detail']}" if p else f"A key area at the {BANDS[band]['label']} level."),
        "focus_on": learn[:4], "do": FOCUS[c["key"]](band, meta), "target": TARGET[c["key"]],
        "examples": p["examples"] if p else [], "workbook": c["workbook"],
    }


def _weekly_plan(band: int, meta: dict, priorities: list[str]) -> list[dict]:
    """Seven days, weighted towards the top priorities."""
    names = {c["key"]: c["title"] for c in CATEGORIES}
    p1 = priorities[0] if priorities else "tactics"
    p2 = priorities[1] if len(priorities) > 1 else "endgame"
    p3 = priorities[2] if len(priorities) > 2 else "opening"
    puzzles = meta["puzzles"]
    return [
        {"day": "Monday", "plan": f"{puzzles} tactical puzzles + {names[p1].lower()} focus"},
        {"day": "Tuesday", "plan": f"{names[p2]} study + 1 training game"},
        {"day": "Wednesday", "plan": f"{puzzles} puzzles + {names[p1].lower()} review of your own mistakes"},
        {"day": "Thursday", "plan": f"{names[p3]} study" + (" + one endgame from the list" if p3 != "endgame" else "")},
        {"day": "Friday", "plan": f"Calculation exercises ({meta['depth']})"},
        {"day": "Saturday", "plan": "Play 2 serious games, then analyze them here"},
        {"day": "Sunday", "plan": "Review your mistakes and update your roadmap progress"},
    ]

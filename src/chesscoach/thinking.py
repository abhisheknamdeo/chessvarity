"""Thinking like a strong player: a fixed routine of questions, answered from the position without naming a best move.

Nothing here calls an engine. The point is the habit: before choosing a move, find out what the last move
did, what the opponent threatens, which pieces are loose, whether either king is in danger, and what the
position is asking for. The answers are facts about the board, so the student still does the deciding.
"""

from __future__ import annotations

import chess

from . import balance
from . import tactics as T

ROUTINE = [
    {"id": "change", "title": "1. What just changed?",
     "question": "Look at your opponent's last move. What does that piece attack now? What did it stop guarding? Which line did it open?"},
    {"id": "threats", "title": "2. What does my opponent want to do next?",
     "question": "If it were their move again, what could they capture, fork or checkmate? Say it out loud before anything else."},
    {"id": "loose", "title": "3. Which pieces are loose?",
     "question": "A piece that nothing protects can be won by one good move. Find every loose piece, yours and theirs."},
    {"id": "forcing", "title": "4. Checks, captures and threats",
     "question": "Strong players look at forcing moves first, for both sides, because they leave the opponent the fewest choices."},
    {"id": "king", "title": "5. Where are the kings?",
     "question": "Which king is safer? Has each side castled, and are there open lines toward either king?"},
    {"id": "plan", "title": "6. What is my plan?",
     "question": "Every position asks for something. Compare material, king safety, piece activity, space and pawns, then choose a plan that fits."},
    {"id": "check", "title": "7. Blunder check",
     "question": "Pick your move, then before you touch the piece, ask: what does this leave undefended, and what is the most annoying reply?"},
]

BLUNDER_CHECK = [
    "Where does the piece I am moving land? Can anything of theirs capture it there?",
    "What did that piece protect before it moved? Is anything now loose?",
    "What is their most annoying reply: a check, a capture, a fork, a pin?",
    "Does my move open a line to my own king?",
    "Have I answered the threat I found in step 2?",
]

PLAN_IDEAS = {
    "material": (
        ["You are ahead in material, so trade pieces (not pawns) and keep everything protected.",
         "When you are ahead, a simple safe move beats a clever risky one."],
        ["You are behind in material, so keep pieces on the board and look for activity and your opponent's king.",
         "Do not trade pieces unless it gets rid of an attacker. Aim for complications where the stronger side can slip."]),
    "king_safety": (
        ["Their king is exposed. Bring more pieces toward it (a rook lift, the queen, a knight) and open lines near it.",
         "Attack only when several pieces can join. One piece alone rarely mates."],
        ["Your king is the one in danger. Make it safe before starting anything: castle, keep the pawn shield, trade off their attackers.",
         "Do not open lines near your own king."]),
    "activity": (
        ["Your pieces are more active. Keep them that way: use open files and diagonals and do not retreat without a reason.",
         "Open the position to make your active pieces count."],
        ["Their pieces are more active. Improve your worst-placed piece first and put a rook on an open file.",
         "Trade off their most active piece if you can."]),
    "space": (
        ["You have more space. Squeeze: take squares away from their pieces and trade the pieces that are short of room.",
         "Avoid trading your space away by pushing pawns without support."],
        ["You are short of space. Trade pieces to relieve the pressure and prepare a pawn break in the center.",
         "Keep your pieces protected because there is little room to run."]),
    "structure": (
        ["Your pawns are healthier. Aim at their weak pawns (isolated or doubled) and keep your own solid.",
         "A healthy pawn structure matters more the longer the game goes on."],
        ["Your pawn structure has weaknesses. Keep those pawns protected and avoid making more pawn moves near them.",
         "Look for activity to make up for it, because weak pawns are easier to protect with active pieces."]),
    "initiative": (
        ["You have more threats. Keep making them: each move should ask a question the opponent must answer.",
         "Do not slow down with a quiet move unless it adds another attacker."],
        ["They have more threats. Every move should answer the threats first. A move that does not answer them loses time.",
         "Look for a move that answers a threat and improves a piece at the same time."]),
}
DEVELOP = "Finish your development first: bring out the minor pieces, castle, and connect the rooks."


def _name(piece: chess.Piece | None) -> str:
    return T.NAME[piece.piece_type] if piece else "piece"


def _sq(square: int) -> str:
    return chess.square_name(square)


def _defended(board: chess.Board, square: int) -> bool:
    piece = board.piece_at(square)
    return bool(piece and board.is_attacked_by(piece.color, square))


NO_LAST_MOVE = ["No move has just been made here. Start by asking what each side's pieces are aiming at."]


def _what_changed(board: chess.Board, me: chess.Color, last_uci: str | None) -> list[str]:
    try:
        move = chess.Move.from_uci(last_uci) if last_uci else None
    except ValueError:
        move = None
    piece = board.piece_at(move.to_square) if move else None
    if piece is None:
        return NO_LAST_MOVE
    mover = "You" if piece.color == me else "Your opponent"
    facts = [f"{mover} moved the {_name(piece)} to {_sq(move.to_square)}."]
    if board.is_check():
        facts.append("That gives check, so the first job is to answer it.")
    targets = []
    for square in board.attacks(move.to_square):
        other = board.piece_at(square)
        if other and other.color != piece.color and other.piece_type != chess.KING:
            bare = "and nothing protects it" if not _defended(board, square) else "(it is protected)"
            targets.append(f"the {_name(other)} on {_sq(square)} {bare}")
    if targets:
        facts.append(f"From there it attacks {'; '.join(targets)}.")
    else:
        facts.append("From there it does not attack any enemy piece yet, so ask what it is preparing.")
    if piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        facts.append("It is a long-range piece, so also look along its lines for what it is aiming at through other pieces.")
    return facts


def _threats(board: chess.Board, me: chess.Color) -> list[str]:
    if board.turn == me and board.is_check():
        return ["You are in check. The check is the threat, so answer it first (capture the checker, block, or move the king)."]
    found = T.find_threats(board, me)
    if not found:
        return ["I find no immediate way for them to win material or mate if they moved right now. Still ask what they are building."]
    facts = []
    for t in found[:4]:
        mover = _name(board.piece_at(t.from_square))
        where = _sq(t.from_square)
        if t.kind == "mate":
            facts.append(f"Checkmate threat: their {mover} on {where} could deliver mate ({t.san}).")
        elif t.kind == "fork":
            hit = " and ".join(f"your {T.NAME[p]} on {_sq(s)}" for s, p in t.targets[:3])
            facts.append(f"Fork threat: their {mover} on {where} could jump in and attack {hit} at once ({t.san}).")
        else:
            square, victim = t.targets[0]
            note = " Your piece is protected, but the trade still loses you material." if t.defended else " It is not protected enough."
            facts.append(f"Capture threat: their {mover} on {where} could take your {T.NAME[victim]} on {_sq(square)} ({t.san}), "
                         f"winning about {t.gain} point{'s' if t.gain != 1 else ''}.{note}")
    return facts


def _loose(board: chess.Board, me: chess.Color) -> list[str]:
    def loose(color: chess.Color) -> list[str]:
        out = []
        for square, piece in board.piece_map().items():
            if piece.color != color or piece.piece_type == chess.KING:
                continue
            if not board.is_attacked_by(color, square):
                attacked = board.is_attacked_by(not color, square)
                out.append((T.VALUE[piece.piece_type], f"{_name(piece)} on {_sq(square)}" + (" (already attacked!)" if attacked else "")))
        out.sort(reverse=True)
        return [text for _, text in out]

    mine, theirs = loose(me), loose(not me)
    return [
        ("Your loose pieces: " + ", ".join(mine[:6]) + ". Protect them or make sure nothing can attack them.") if mine
        else "None of your pieces is loose. Everything you own is protected.",
        ("Their loose pieces: " + ", ".join(theirs[:6]) + ". These are targets: can you attack one with tempo?") if theirs
        else "None of their pieces is loose right now.",
    ]


def _forcing(board: chess.Board, me: chess.Color) -> list[str]:
    if board.turn != me:
        return ["It is not your move. Imagine you were on move and list the checks and captures anyway; it is good practice."]
    checks, captures = [], []
    for move in board.legal_moves:
        if board.gives_check(move):
            checks.append(board.san(move))
        elif board.is_capture(move):
            gain = T.see_capture(board, move)
            tag = "wins material" if gain > 0 else "an even trade" if gain == 0 else "loses material"
            captures.append(f"{board.san(move)} ({tag})")
    facts = []
    facts.append("Checks: " + (", ".join(checks[:8]) if checks else "none") + ".")
    facts.append("Captures: " + (", ".join(captures[:8]) if captures else "none") + ".")
    facts.append("These are the moves to consider first. They are options to think about, not a recommendation: "
                 "check what each one leaves you open to.")
    return facts


def _king(board: chess.Board, me: chess.Color) -> list[str]:
    facts = []
    for color, who in ((me, "Your"), (not me, "Their")):
        ks = board.king(color)
        if ks is None:
            continue
        home = chess.square_rank(ks) == (0 if color == chess.WHITE else 7)
        castled = chess.square_file(ks) in (0, 1, 2, 6, 7) and home
        if castled:
            state = "has castled and is tucked away"
        elif board.has_castling_rights(color):
            state = "is still in the center but can still castle"
        elif home:
            state = "is in the center and can no longer castle"
        else:
            state = "has wandered away from its home rank"
        hitters = T.pieces_hitting(board, not color, T.king_zone(board, color))
        pressure = f" {len(hitters)} enemy piece{'s' if len(hitters) != 1 else ''} aim at the squares around it." if hitters else ""
        facts.append(f"{who} king on {_sq(ks)} {state}.{pressure}")
    return facts


def _plan(board: chess.Board, me: chess.Color) -> tuple[list[str], dict]:
    read = balance.describe(board, me)
    scores = read["scores"]
    ideas: list[str] = []
    developed = balance._developed(board, me)
    if board.fullmove_number <= 12 and (developed < 3 or board.has_castling_rights(me)):
        ideas.append(DEVELOP)
    ranked = sorted(balance.DIMENSIONS, key=lambda k: -abs(scores[k]))
    for key in ranked:
        if abs(scores[key]) >= balance.NOTABLE and len(ideas) < 4:
            ideas.extend(PLAN_IDEAS[key][0 if scores[key] > 0 else 1][:1])
    mine = balance._pawns(board, me)
    if mine["passed"] and len(ideas) < 5:
        ideas.append(f"You have a passed pawn on {mine['passed'][0]}. Support it and push it when it is safe.")
    if not ideas:
        ideas.append("Nothing stands out yet, so improve your worst-placed piece, keep everything protected, "
                     "and wait for your opponent to make a mistake.")
    facts = [read["verdict"]["text"]] + [n["text"] for n in read["notes"]]
    return facts + ["So a sensible plan is:"] + ideas, read


def examine(fen: str, last_uci: str | None = None, color: str | None = None) -> dict:
    """The seven-step routine for a position, from `color`'s point of view (default: the side to move)."""
    board = chess.Board(fen)
    me = board.turn if color not in ("white", "black") else chess.WHITE if color == "white" else chess.BLACK
    plan_facts, read = _plan(board, me)
    answers = {
        "change": _what_changed(board, me, last_uci),
        "threats": _threats(board, me),
        "loose": _loose(board, me),
        "forcing": _forcing(board, me),
        "king": _king(board, me),
        "plan": plan_facts,
        "check": BLUNDER_CHECK,
    }
    return {
        "side": "white" if me == chess.WHITE else "black", "turn": "white" if board.turn == chess.WHITE else "black",
        "steps": [{**step, "facts": answers[step["id"]]} for step in ROUTINE],
        "balance": {"scores": read["scores"], "labels": balance.LABELS, "verdict": read["verdict"]},
    }


# -- The guide: things to understand before, and while, you play ---------------------------------------

GUIDE = {
    "loop": {
        "title": "The Grandmaster loop",
        "intro": "Strong players are not smarter at every move. They ask the same short list of questions every single move, "
                 "so they almost never miss a threat. Make it your habit and your blunders will drop.",
        "steps": ROUTINE,
    },
    "traps": [
        {"name": "The greedy pawn", "sign": "A free pawn (or piece) that your opponent left there on purpose.",
         "habit": "When something is free, ask 'why did they allow this?' before you take it. Look at what taking it opens up."},
        {"name": "The pinned piece", "sign": "Your piece stands in front of something more valuable (your queen or king).",
         "habit": "Before you place a piece on a line with your queen or king, ask whether an enemy bishop or rook could pin it."},
        {"name": "The queen raid", "sign": "Your queen wanders out early and captures a pawn far from home.",
         "habit": "Count your queen's escape squares before you send her out. If she can be trapped, do not go."},
        {"name": "The f7 / f2 weakness", "sign": "A bishop and a queen or knight both aim at the pawn next to the king, and it is only protected by the king.",
         "habit": "Count how many pieces attack the square next to your king and how many protect it. Castle early to fix it."},
        {"name": "The back-rank mate", "sign": "Your king is castled behind unmoved pawns and your rooks have left the back rank.",
         "habit": "Make a small escape square with h3 or a3 once the position gets tactical, and keep a rook on the back rank."},
        {"name": "The discovered attack", "sign": "One of their pieces steps aside and reveals an attack from a bishop, rook or queen behind it.",
         "habit": "Look at the pieces behind their pieces. What would attack you if that piece moved with a threat of its own?"},
        {"name": "The fork", "sign": "A knight can jump to a square that attacks two of your pieces (often the king and queen or a rook).",
         "habit": "Look at every square their knights can reach and see what sits on the squares they attack from there."},
        {"name": "The desperado", "sign": "A piece that is about to be lost grabs something on the way out.",
         "habit": "When you win a piece, ask what it can still capture before it goes."},
    ],
    "principles": [
        {"title": "Answer the threat, then improve", "text": "If they threaten something, deal with it first. A move that ignores the threat has to be a bigger threat."},
        {"title": "Loose pieces drop off", "text": "Every time you move, check that all your pieces are protected. A loose piece is a target."},
        {"title": "Forcing moves first", "text": "Checks, captures and threats leave the opponent the fewest replies, so look at them for both sides before quiet moves."},
        {"title": "One move at a time, but with a plan", "text": "A plan does not mean a fixed line. It is a direction (attack their king, fix your king, open a file) that you keep choosing moves for."},
        {"title": "Use your clock", "text": "Spend your time on the moves where the position is sharp: captures, checks, king safety. Play obvious moves quickly."},
        {"title": "Reset after a mistake", "text": "One blunder is not the end. Breathe, look at the board fresh, and ask what the best fighting chance is now. Resigning early is the only sure loss."},
    ],
    "phases": [
        {"title": "Opening", "goal": "Finish development", "text": "Fight for the center, bring out the knights and bishops, castle, connect the rooks. Do not move the same piece twice without a reason and do not bring the queen out early."},
        {"title": "Middlegame", "goal": "Make a plan", "text": "Compare the imbalances (material, king safety, activity, space, pawns), then pick a plan that fits. Improve your worst piece. Watch for tactics on every move."},
        {"title": "Endgame", "goal": "Activate your king", "text": "The king becomes a strong piece. Push passed pawns with support, get rooks behind them, and count moves before you race."},
    ],
    "after_game": [
        "Write down your opponent, the result and the round straight after the game, while you remember it.",
        "Enter the moves as soon as you can (the scoresheet helps) and let the coach find the turning points.",
        "Find the one moment where the game changed and ask which of the seven questions you skipped there.",
    ],
}

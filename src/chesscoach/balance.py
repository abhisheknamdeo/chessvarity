"""Who is better where? A plain-language reading of a position's imbalances.

Each score runs from -100 (clearly worse for the player) to +100 (clearly better).
These are coaching heuristics that point at what to look at; the engine still has the last word on who is winning.
"""

from __future__ import annotations

import chess

from . import tactics as T

DIMENSIONS = ("material", "king_safety", "activity", "space", "structure", "initiative")
LABELS = {
    "material": "Material",
    "king_safety": "King safety",
    "activity": "Piece activity",
    "space": "Space",
    "structure": "Pawn structure",
    "initiative": "Threats & initiative",
}
NOTABLE = 25  # a score this far from zero is worth mentioning

PHRASES = {
    "material": ("You are ahead in material.", "You are behind in material."),
    "king_safety": ("Their king is more exposed than yours.", "Your king is more exposed than theirs."),
    "activity": ("Your pieces are more active.", "Their pieces are more active."),
    "space": ("You control more space.", "They control more space."),
    "structure": ("Your pawn structure is healthier.", "Their pawn structure is healthier."),
    "initiative": ("You have more threats.", "They have more threats."),
}
LOSS_PHRASES = {
    "material": "It cost you material.",
    "king_safety": "It weakened your king.",
    "activity": "It made your pieces less active.",
    "space": "It gave up space.",
    "structure": "It damaged your pawn structure.",
    "initiative": "It handed your opponent the initiative.",
}


def _clamp(x: float) -> float:
    return max(-100.0, min(100.0, x))


def _material(board: chess.Board, color: chess.Color) -> float:
    total = T.material(board, color)
    if len(board.pieces(chess.BISHOP, color)) >= 2:
        total += 0.5
    return total


def _mobility(board: chess.Board, color: chess.Color) -> int:
    own = board.occupied_co[color]
    total = 0
    for square, piece in board.piece_map().items():
        if piece.color == color and piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            total += len(board.attacks(square) & ~chess.SquareSet(own))
    return total


def _developed(board: chess.Board, color: chess.Color) -> int:
    home = 0 if color == chess.WHITE else 7
    return sum(
        1
        for sq in board.pieces(chess.KNIGHT, color) | board.pieces(chess.BISHOP, color)
        if chess.square_rank(sq) != home
    )


def _rook_files(board: chess.Board, color: chess.Color) -> int:
    score = 0
    for sq in board.pieces(chess.ROOK, color):
        f = chess.square_file(sq)
        pawns = [board.piece_at(chess.square(f, r)) for r in range(8)]
        own = any(p and p.piece_type == chess.PAWN and p.color == color for p in pawns)
        theirs = any(p and p.piece_type == chess.PAWN and p.color != color for p in pawns)
        if not own and not theirs:
            score += 2
        elif not own:
            score += 1
    return score


def _space(board: chess.Board, color: chess.Color) -> int:
    ranks = range(4, 8) if color == chess.WHITE else range(0, 4)
    return sum(
        1
        for r in ranks
        for f in range(8)
        if len(board.attackers(color, chess.square(f, r))) > len(board.attackers(not color, chess.square(f, r)))
    )


def _center(board: chess.Board, color: chess.Color) -> int:
    score = 0
    for sq in (chess.D4, chess.E4, chess.D5, chess.E5):
        p = board.piece_at(sq)
        if p and p.piece_type == chess.PAWN and p.color == color:
            score += 2
        score += len(board.attackers(color, sq)) - len(board.attackers(not color, sq))
    return score


def _pawns(board: chess.Board, color: chess.Color) -> dict:
    mine = board.pieces(chess.PAWN, color)
    theirs = board.pieces(chess.PAWN, not color)
    isolated = doubled = 0
    passed: list[str] = []
    files = [chess.square_file(s) for s in mine]
    for sq in mine:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        if not any(abs(chess.square_file(o) - f) == 1 for o in mine):
            isolated += 1
        if files.count(f) > 1:
            doubled += 1
        ahead = range(r + 1, 8) if color == chess.WHITE else range(0, r)
        blocked = any(
            chess.square_file(o) in (f - 1, f, f + 1) and chess.square_rank(o) in ahead for o in theirs
        )
        if not blocked:
            passed.append(chess.square_name(sq))
    return {"isolated": isolated, "doubled": len(files) - len(set(files)), "passed": passed}


def _threat_value(board: chess.Board, victim: chess.Color) -> int:
    return sum(min(t.gain, 9) for t in T.find_threats(board, victim)[:3])


def scores(board: chess.Board, color: chess.Color) -> dict[str, float]:
    """Each dimension from `color`'s point of view."""
    other = not color
    mine_pawns, their_pawns = _pawns(board, color), _pawns(board, other)
    struct = lambda p: 2 * len(p["passed"]) - p["isolated"] - p["doubled"]
    activity = (
        (_mobility(board, color) - _mobility(board, other))
        + 3 * (_rook_files(board, color) - _rook_files(board, other))
        + 2 * (_developed(board, color) - _developed(board, other))
    )
    king_safety = T.attack_potential(board, color)["total"] - T.attack_potential(board, other)["total"]
    space = (_space(board, color) - _space(board, other)) + (_center(board, color) - _center(board, other))
    return {
        "material": _clamp((_material(board, color) - _material(board, other)) / 5 * 100),
        "king_safety": _clamp(king_safety),
        "activity": _clamp(activity * 4),
        "space": _clamp(space * 4),
        "structure": _clamp((struct(mine_pawns) - struct(their_pawns)) * 15),
        "initiative": _clamp((_threat_value(board, other) - _threat_value(board, color)) * 12),
    }


def describe(board: chess.Board, color: chess.Color, wp: float | None = None) -> dict:
    """Scores, notable imbalances in words, and an overall verdict for one position."""
    s = scores(board, color)
    notable = sorted((k for k in DIMENSIONS if abs(s[k]) >= NOTABLE), key=lambda k: -abs(s[k]))
    notes = [{"key": k, "score": round(s[k]), "text": PHRASES[k][0 if s[k] > 0 else 1]} for k in notable]
    pros = [k for k in notable if s[k] > 0]
    cons = [k for k in notable if s[k] < 0]
    if pros and cons:
        label = "unbalanced"
        text = (
            f"An unbalanced position: {PHRASES[pros[0]][0][:-1].lower()}, but "
            f"{PHRASES[cons[0]][1][:-1].lower()}."
        )
    elif pros:
        label, text = "you-better", "Most of the imbalances favour you: " + PHRASES[pros[0]][0].lower()
    elif cons:
        label, text = "opponent-better", "Most of the imbalances favour your opponent: " + PHRASES[cons[0]][1].lower()
    else:
        label, text = "balanced", "The position is balanced: no side has a clear edge yet."
    if wp is not None:
        engine = "you are better" if wp >= 60 else "you are worse" if wp <= 40 else "it is about equal"
        text += f" The engine says {engine}."
    return {"scores": {k: round(v) for k, v in s.items()}, "notes": notes, "verdict": {"label": label, "text": text}}


def shift(before: dict, after: dict) -> list[dict]:
    """How a move changed things: biggest drops first (positive `drop` = worse for the player)."""
    out = []
    for k in DIMENSIONS:
        delta = after["scores"][k] - before["scores"][k]
        if delta <= -20:
            out.append({"key": k, "drop": -delta, "text": LOSS_PHRASES[k]})
    out.sort(key=lambda x: -x["drop"])
    return out

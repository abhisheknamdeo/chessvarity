"""Move-by-move commentary in plain language, built from facts (tactics.py) plus engine evaluations.

`annotate` narrates every move of a game. With a viewpoint the text speaks to that player
("You develop the knight"); without one it names the sides ("White develops the knight").
Nothing here judges chess by itself: mistakes and strong moves come from the engine's numbers.
"""

from __future__ import annotations

import chess

from . import tactics as T
from .engine import PositionEval, wp_state

INACCURACY, MISTAKE, BLUNDER = 5.0, 10.0, 20.0
CENTRE = {chess.D4, chess.E4, chess.D5, chess.E5}
BIG_CENTRE = CENTRE | {chess.C4, chess.C5, chess.F4, chess.F5, chess.C3, chess.F3, chess.C6, chess.F6}
OPENING_PLIES = 24


class Voice:
    """Who is speaking about whom, so the same facts read naturally either way."""

    def __init__(self, viewpoint: chess.Color | None):
        self.vp = viewpoint

    def subj(self, color: chess.Color) -> str:
        if self.vp is None:
            return "White" if color == chess.WHITE else "Black"
        return "You" if color == self.vp else "Your opponent"

    def poss(self, color: chess.Color) -> str:
        if self.vp is None:
            return "White's" if color == chess.WHITE else "Black's"
        return "your" if color == self.vp else "your opponent's"

    def verb(self, color: chess.Color, base: str) -> str:
        """Present tense: 'You develop' but 'White develops' / 'Your opponent develops'."""
        if self.vp is not None and color == self.vp:
            return base
        if base.endswith(("s", "x", "ch", "sh")):
            return base + "es"
        return base + "s"


def _sq(square: int) -> str:
    return chess.square_name(square)


def _name(piece_type: int) -> str:
    return T.NAME[piece_type]


def _threatened_pieces(after: chess.Board, square: int, victim: chess.Color) -> list[tuple[int, int]]:
    """Enemy pieces the piece on `square` attacks that are loose or worth more than it."""
    mine = after.piece_at(square)
    found = []
    for target in after.attacks(square):
        piece = after.piece_at(target)
        if piece is None or piece.color != victim or piece.piece_type == chess.KING:
            continue
        loose = not after.is_attacked_by(victim, target)
        bigger = T.VALUE[piece.piece_type] > T.VALUE[mine.piece_type]
        if loose and piece.piece_type == chess.PAWN and mine.piece_type != chess.PAWN:
            found.append((target, piece.piece_type))
        elif (loose and piece.piece_type != chess.PAWN) or bigger:
            found.append((target, piece.piece_type))
    found.sort(key=lambda t: -T.VALUE[t[1]])
    return found[:2]


def _describe_action(board: chess.Board, move: chess.Move, info: T.MoveInfo, v: Voice, ply: int) -> tuple[str, list[str]]:
    """The 'what happened' sentence for a move."""
    mover = board.turn
    piece = board.piece_at(move.from_square)
    name, to = _name(piece.piece_type), _sq(move.to_square)
    who = v.subj(mover)
    tags: list[str] = []
    if board.is_castling(move):
        side = "kingside" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "queenside"
        tags.append("castle")
        return f"{who} {v.verb(mover, 'castle')} {side}, tucking the king away and bringing a rook into play.", tags
    if move.promotion:
        tags.append("promotion")
        return f"{who} {v.verb(mover, 'promote')} the pawn to a {_name(move.promotion)} on {to}!", tags
    if board.is_capture(move):
        tags.append("capture")
        captured = "pawn" if board.is_en_passant(move) else _name(info.captured)
        extra = " (en passant)" if board.is_en_passant(move) else ""
        return f"{who} {v.verb(mover, 'capture')} the {captured} on {to} with the {name}{extra}.", tags
    if piece.piece_type == chess.PAWN:
        tags.append("pawn")
        centre = " to take space in the center" if move.to_square in CENTRE else ""
        two = " two squares" if abs(chess.square_rank(move.to_square) - chess.square_rank(move.from_square)) == 2 else ""
        return f"{who} {v.verb(mover, 'push')} the {chess.FILE_NAMES[chess.square_file(move.from_square)]}-pawn{two} to {to}{centre}.", tags
    home = 0 if mover == chess.WHITE else 7
    developing = piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) == home and ply <= OPENING_PLIES
    if developing:
        tags.append("develop")
        centre = ", eyeing the center" if move.to_square in BIG_CENTRE else ""
        return f"{who} {v.verb(mover, 'develop')} the {name} to {to}{centre}.", tags
    if piece.piece_type == chess.QUEEN and board.fullmove_number <= 5:
        tags.append("early-queen")
        return f"{who} {v.verb(mover, 'bring')} the queen out early to {to}. It can be chased by enemy pieces, so watch out.", tags
    if piece.piece_type == chess.ROOK:
        f = chess.square_file(move.to_square)
        file_pieces = [board.piece_at(chess.square(f, r)) for r in range(8)]
        pawns = [p for p in file_pieces if p and p.piece_type == chess.PAWN]
        if not pawns:
            tags.append("open-file")
            return f"{who} {v.verb(mover, 'place')} the rook on the open {chess.FILE_NAMES[f]}-file, where nothing blocks it.", tags
        if not any(p.color == mover for p in pawns):
            tags.append("open-file")
            return f"{who} {v.verb(mover, 'place')} the rook on the half-open {chess.FILE_NAMES[f]}-file, aiming at the enemy pawns.", tags
    delta = chess.square_rank(move.to_square) - chess.square_rank(move.from_square)
    if (delta < 0 if mover == chess.WHITE else delta > 0) and piece.piece_type != chess.KING:
        tags.append("retreat")
        return f"{who} {v.verb(mover, 'pull')} the {name} back to {to}.", tags
    if piece.piece_type == chess.KING:
        return f"{who} {v.verb(mover, 'move')} the king to {to}.", tags
    return f"{who} {v.verb(mover, 'move')} the {name} to {to}.", tags


def _state_for(wp: float, mover: chess.Color, v: Voice) -> str:
    """'You are better' / 'White is winning'..., wp is the mover's winning chances."""
    state = wp_state(wp)
    who = v.subj(mover)
    return f"{who} {'are' if v.vp == mover else 'is'} {state}" if state != "about equal" else "The position is about equal"


def _threat_text(t: T.Threat) -> str:
    if t.kind == "mate":
        return f"checkmate with {t.san}"
    if t.kind == "fork":
        return f"a fork with {t.san}"
    target = t.targets[0] if t.targets else None
    return f"winning the {_name(target[1])} on {_sq(target[0])} with {t.san}" if target else t.san


def annotate(
    boards: list[chess.Board],
    moves: list[chess.Move],
    evals: list[PositionEval],
    viewpoint: chess.Color | None = None,
    book_ply: int = 0,
    opening_name: str = "",
) -> list[dict]:
    """One entry per move: {ply, san, text, tags, wp (mover's chances after), loss}."""
    v = Voice(viewpoint)
    out = []
    for i, move in enumerate(moves):
        board, after = boards[i], boards[i + 1]
        mover = board.turn
        ply = i + 1
        info = T.describe_move(board, move)
        who = v.subj(mover)
        opp = v.subj(not mover)

        main, tags = _describe_action(board, move, info, v, ply)
        extras: list[str] = []
        ev, nxt = evals[i], evals[i + 1]
        best_wp = ev.wp(mover)
        line = ev.line_for(move)
        played_wp = 100.0 if after.is_checkmate() else (line.wp(mover) if line else nxt.wp(mover))
        loss = max(0.0, best_wp - played_wp)

        if after.is_checkmate():
            tags.append("mate")
            extras.append("Checkmate! The king has no escape.")
        else:
            if info.is_check:
                tags.append("check")
                extras.append("It gives check, so the king must respond.")
            if info.fork:
                tags.append("fork")
                names = " and ".join(_name(p) for _, p in info.fork.targets)
                extras.append(f"It is a fork: the {_name(info.piece_type)} attacks the {names} at the same time.")
            elif info.pin:
                tags.append("pin")
                extras.append(f"It pins the {_name(info.pin[1])}: that piece cannot move without exposing something behind it.")
            elif info.discovered:
                tags.append("discovered")
                extras.append(f"It uncovers an attack on the {_name(info.discovered[1])} from a piece behind.")

            # A sacrifice: material can be taken, yet the engine still likes the move.
            can_take = info.hangs_moved_piece and (info.piece_type != chess.PAWN)
            if can_take and loss <= 6 and not board.is_capture(move) and T.VALUE[info.piece_type] >= 3:
                tags.append("sacrifice")
                extras.append(f"It is a sacrifice: the {_name(info.piece_type)} can be taken, but the attack that follows is worth more.")
            elif board.is_capture(move) and T.see_capture(board, move) < 0 and loss <= 6:
                tags.append("sacrifice")
                extras.append("It gives up material on purpose: the engine likes what comes next.")

            if not (info.fork or info.is_check):
                targets = _threatened_pieces(after, move.to_square, not mover)
                if targets:
                    tags.append("attack")
                    sq, pt = targets[0]
                    extras.append(f"It now attacks the {_name(pt)} on {_sq(sq)}.")
                else:
                    made = [t for t in T.mover_threats(board, move) if t.gain >= 3]
                    if made:
                        tags.append("threat")
                        extras.append(f"It threatens {_threat_text(made[0])}.")

            faced = [t for t in T.find_threats(board, mover) if t.gain >= 3]
            if faced:
                remaining = {(t.kind, t.san) for t in T.find_threats(after, mover)}
                if (faced[0].kind, faced[0].san) not in remaining:
                    tags.append("defence")
                    extras.append(f"It deals with the threat of {_threat_text(faced[0])}.")
                elif loss >= MISTAKE:
                    tags.append("missed-threat")
                    extras.append(f"It ignores the threat of {_threat_text(faced[0])}.")

            if loss >= MISTAKE and nxt.best is not None:
                hit = T.threat_for_move(after, nxt.best.move, mover) if after.turn != mover else None
                if hit and hit.kind in ("capture", "fork", "mate") and "missed-threat" not in tags:
                    tags.append("hangs")
                    extras.append(f"It allows {_threat_text(hit)}.")

        judge = None
        if loss >= BLUNDER:
            judge, tags = "This is a blunder", tags + ["blunder"]
        elif loss >= MISTAKE:
            judge, tags = "This is a mistake", tags + ["mistake"]
        elif loss >= INACCURACY:
            judge, tags = "This is a small inaccuracy", tags + ["inaccuracy"]
        must: list[str] = [e for e in extras if e.startswith("Checkmate")]
        if judge and ev.best is not None:
            best_san = board.san(ev.best.move)
            sentence = f"{judge}. {best_san} was better."
            extras.append(sentence)
            if loss >= MISTAKE:
                must.append(sentence)  # a real mistake is always worth saying
        elif ev.best is not None and ev.best.move == move and len(ev.lines) > 1 and best_wp - ev.lines[1].wp(mover) >= 15 and not after.is_checkmate():
            tags.append("only-move")
            extras.append("It was the only good move here: the alternatives were much worse.")

        before_state, after_state = wp_state(best_wp), wp_state(played_wp)
        if before_state != after_state and not after.is_checkmate() and loss < 100:
            improved = played_wp > best_wp - 0.1 or after_state in ("winning", "better")
            if after_state in ("winning", "losing") or (loss < INACCURACY and improved):
                extras.append(_state_for(played_wp, mover, v) + " now.")

        opening_note = None
        if book_ply and ply == book_ply and opening_name:
            opening_note = f"The opening so far is the {opening_name}."
        elif book_ply and ply == book_ply + 1:
            opening_note = "From here the game leaves well-known opening theory."

        # Keep it readable: the action, then the most important extras (mistakes and mates always stay).
        priority = ["Checkmate", "It is a fork", "It pins", "It uncovers", "It is a sacrifice", "It gives up", "It gives check",
                    "It threatens", "It now attacks", "It deals", "It ignores", "It allows", "This is a", "It was the only"]
        extras.sort(key=lambda s: next((n for n, p in enumerate(priority) if s.startswith(p)), len(priority)))
        chosen = list(must)
        for e in extras:
            if e not in chosen and len(chosen) < 3:
                chosen.append(e)
        chosen.sort(key=lambda s: extras.index(s))
        if opening_note:
            chosen.append(opening_note)
        text = " ".join([main] + chosen)
        out.append({"ply": ply, "san": board.san(move), "text": text, "tags": sorted(set(tags)),
                    "wp": round(played_wp, 1), "loss": round(loss, 1), "mover": "white" if mover == chess.WHITE else "black"})
    return out


THEME_LESSONS = {
    "sacrifice": "Give up material when it opens lines or drags the enemy king into danger, but only when you can see the follow-up.",
    "fork": "Look for a piece that can attack two things at once; the opponent can only save one.",
    "pin": "A pinned piece is a target: attack it again.",
    "discovered": "Moving one piece can uncover an attack from another.",
    "check": "Keep giving checks when they force the king somewhere worse; every check takes away a choice.",
    "open-file": "Rooks belong on open files, where they can reach the enemy position.",
    "castle": "Castle early: it protects the king and connects the rooks.",
    "develop": "Bring every piece into the game before starting a big attack.",
    "mate": "Attacking play ends in checkmate: count the attackers against the defenders around the king.",
}


def game_notes(commentary: list[dict], result: str, moves_count: int, opening_name: str = "") -> dict:
    """A short summary and lessons for a whole game, from the tags of its commentary."""
    tags: dict[str, int] = {}
    for c in commentary:
        for t in c["tags"]:
            tags[t] = tags.get(t, 0) + 1
    winner = {"1-0": "White", "0-1": "Black"}.get(result)
    ending = "checkmate" if any("mate" in c["tags"] for c in commentary) else "a decisive advantage"
    turning = max((c for c in commentary if c["loss"] >= MISTAKE), key=lambda c: c["loss"], default=None)
    parts = []
    if winner:
        parts.append(f"{winner} won by {ending} on move {(moves_count + 1) // 2}.")
    elif result == "1/2-1/2":
        parts.append("The game was drawn.")
    if opening_name:
        parts.append(f"It began as the {opening_name}.")
    if tags.get("sacrifice"):
        parts.append(f"Watch for the sacrifice{'s' if tags['sacrifice'] > 1 else ''}: material is given up to break open the king.")
    if turning:
        side = "White" if turning["mover"] == "white" else "Black"
        parts.append(f"The turning point was {(turning['ply'] + 1) // 2}{'.' if turning['mover'] == 'white' else '...'} {turning['san']} by {side}.")
    lessons = [THEME_LESSONS[t] for t in ("sacrifice", "fork", "pin", "discovered", "open-file", "check", "mate") if tags.get(t)]
    themes = [t for t in ("sacrifice", "fork", "pin", "discovered", "check", "open-file", "mate", "castle") if tags.get(t)]
    return {"summary": " ".join(parts), "lessons": lessons[:4], "themes": themes}

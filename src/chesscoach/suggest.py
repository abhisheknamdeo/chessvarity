"""Move suggestions that say what a move does and why it is good (or not), from the engine's lines plus board facts.

The engine (Stockfish, several lines) decides which moves are best and how much better they are. Everything said
about a move is a fact read from the board: what it captures, checks, forks or pins, which threat it stops, which
piece it attacks, protects, develops or frees, and what the opponent can do next. Nothing here guesses.
"""

from __future__ import annotations

import chess

from . import balance, commentary
from . import tactics as T
from .engine import Line

CENTRE = (chess.D4, chess.E4, chess.D5, chess.E5)
MAX_REASONS = 4
MAX_PV = 7

GAIN = {
    "king_safety": "Their king ends up more exposed than yours, or yours safer than theirs.",
    "activity": "Your pieces get more room and more open lines (better piece activity).",
    "space": "You control more of the board, especially the center.",
    "structure": "Your pawn structure improves compared with theirs.",
    "initiative": "It swings the threats your way: you face fewer, or you make more.",
}
PHASE_ADVICE = {
    "opening": "It follows opening principles: develop pieces, control the center, get the king safe.",
    "middlegame": "It improves the placement of your pieces while keeping everything protected.",
    "endgame": "It makes progress in the endgame, where every tempo counts.",
}


def eval_words(wp: float) -> str:
    """More careful than 'better' or 'worse': how big the advantage is, from the side to move's view."""
    if wp >= 90:
        return "winning"
    if wp >= 75:
        return "clearly better"
    if wp >= 60:
        return "better"
    if wp >= 54:
        return "slightly better"
    if wp > 46:
        return "equal"
    if wp > 40:
        return "slightly worse"
    if wp > 25:
        return "worse"
    if wp > 10:
        return "clearly worse"
    return "losing"


def quality(gap: float, rank: int, mate_against: bool) -> tuple[str, str]:
    """(code, label) for a candidate, from how many winning-chance points it gives up against the best move."""
    if mate_against:
        return "bad", "Not recommended: it walks into a forced mate"
    if gap <= 2:
        return ("best", "Best move") if rank == 0 else ("equal", "Just as good")
    if gap <= 6:
        return "good", "Good alternative"
    if gap <= 14:
        return "ok", "Playable, a little worse"
    if gap <= 28:
        return "weak", "Weaker: a real mistake"
    return "bad", "Not recommended: a blunder"


def _mate_for(line: Line, color: chess.Color) -> int | None:
    """Mate distance from `color`'s view: positive means `color` mates."""
    if line.mate is None:
        return None
    return line.mate if color == chess.WHITE else -line.mate


def score_text(line: Line, color: chess.Color) -> str:
    mate = _mate_for(line, color)
    if mate is not None:
        return f"mate in {abs(mate)}" if mate > 0 else f"mated in {abs(mate)}"
    cp = line.cp if color == chess.WHITE else -line.cp
    return f"{cp / 100:+.1f}"


def pv_text(board: chess.Board, pv: list[chess.Move], limit: int = MAX_PV) -> str:
    """The engine's line as numbered moves: '3. Nf3 Nc6 4. Bb5'."""
    b = board.copy(stack=False)
    parts = []
    for i, move in enumerate(pv[:limit]):
        number = b.fullmove_number
        if b.turn == chess.WHITE:
            parts.append(f"{number}. {b.san(move)}")
        else:
            parts.append(f"{number}... {b.san(move)}" if i == 0 else b.san(move))
        b.push(move)
    return " ".join(parts)


def _side(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


def _loose(board: chess.Board, color: chess.Color) -> set[int]:
    """Pieces of `color` that an enemy piece attacks and nothing of `color` protects."""
    return {
        sq for sq, p in board.piece_map().items()
        if p.color == color and p.piece_type != chess.KING and board.is_attacked_by(not color, sq) and not board.is_attacked_by(color, sq)
    }


def _phase(board: chess.Board) -> str:
    if board.fullmove_number <= 10 and len(board.piece_map()) >= 26:
        return "opening"
    return "endgame" if len(board.piece_map()) <= 14 else "middlegame"


def _reasons(board: chess.Board, move: chess.Move, line: Line, gap: float, rank: int, second_gap: float | None,
             best_san: str) -> tuple[list[tuple[int, str]], list[str]]:
    """(prioritized reasons, warnings) for one candidate move."""
    mover, opp = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    name, to, frm = T.NAME[piece.piece_type], chess.square_name(move.to_square), chess.square_name(move.from_square)
    info = T.describe_move(board, move)
    after = board.copy(stack=False)
    after.push(move)
    why: list[tuple[int, str]] = []
    warn: list[str] = []
    mate = _mate_for(line, mover)

    if after.is_checkmate():
        why.append((0, "It is checkmate."))
    elif mate is not None and mate > 0:
        why.append((0, f"It forces checkmate in {mate} move{'s' if mate != 1 else ''} if you follow the line."))
    elif mate is not None and mate < 0:
        warn.append(f"Careful: after this, {_side(opp)} has a forced checkmate in {abs(mate)}.")

    if not after.is_checkmate():
        if info.is_check:
            replies = after.legal_moves.count()
            why.append((2, f"It gives check, and {_side(opp)} has only {replies} legal {'reply' if replies == 1 else 'replies'}, so you decide what happens next."))
        if board.is_capture(move):
            victim = "pawn" if board.is_en_passant(move) else T.NAME[info.captured]
            gain = T.see_capture(board, move)
            if gain > 0:
                why.append((1, f"It wins material: the {name} takes the {victim} on {to} and the exchange there favours you by about {gain} point{'s' if gain != 1 else ''}."))
            elif gain == 0:
                why.append((3, f"It trades your {name} for the {victim} on {to}, which simplifies the position in your favour."))
            else:
                why.append((2, f"It gives up the {name} for the {victim} on purpose: the attack or the open lines that follow are worth more."))
        if move.promotion:
            why.append((0, f"The pawn promotes to a {T.NAME[move.promotion]} on {to}."))
        if info.fork:
            names = " and ".join(f"the {T.NAME[p]}" for _, p in info.fork.targets)
            why.append((1, f"It is a fork: the {name} on {to} attacks {names} at the same time, and the opponent can only save one."))
        elif info.pin:
            why.append((2, f"It pins the {T.NAME[info.pin[1]]}: that piece cannot move without exposing something more valuable behind it."))
        elif info.discovered:
            why.append((2, f"It uncovers an attack on the {T.NAME[info.discovered[1]]} from the piece behind."))

        # Threats you were facing, and whether this move deals with them.
        if board.is_check():
            how = "by capturing the checking piece" if board.is_capture(move) else \
                "by moving the king" if move.from_square == board.king(mover) else "by blocking the check"
            why.append((1, f"It gets your king out of check {how}."))
        else:
            faced = [t for t in T.find_threats(board, mover) if t.gain >= 3]
            if faced:
                left = {(t.kind, t.san) for t in T.find_threats(after, mover)}
                if (faced[0].kind, faced[0].san) not in left:
                    why.append((1, f"It stops your opponent's threat of {commentary._threat_text(faced[0])}."))
                elif gap >= 6:
                    warn.append(f"It does not deal with the threat of {commentary._threat_text(faced[0])}.")

        # Safety of the piece that moved, and pieces it now protects.
        if board.is_attacked_by(opp, move.from_square) and not info.hangs_moved_piece and not board.is_capture(move):
            why.append((3, f"It moves the attacked {name} on {frm} to safety."))
        fixed = [sq for sq in _loose(board, mover) - {move.from_square}
                 if after.piece_at(sq) and after.piece_at(sq).color == mover and sq not in _loose(after, mover)]
        if fixed:
            p = board.piece_at(fixed[0])
            why.append((3, f"It protects your loose {T.NAME[p.piece_type]} on {chess.square_name(fixed[0])}, which the opponent was attacking."))

        # What the move attacks or threatens.
        if not info.fork and not info.is_check:
            targets = []
            for target in after.attacks(move.to_square):
                victim = after.piece_at(target)
                if victim is None or victim.color != opp or victim.piece_type == chess.KING:
                    continue
                unprotected = not after.is_attacked_by(opp, target)
                if unprotected or T.VALUE[victim.piece_type] > T.VALUE[piece.piece_type]:
                    targets.append((T.VALUE[victim.piece_type], target, victim, unprotected))
            if targets:
                _, target, victim, unprotected = max(targets, key=lambda t: t[0])
                why.append((4, f"From {to} the {name} attacks the {T.NAME[victim.piece_type]} on {chess.square_name(target)}"
                               + (", which nothing protects." if unprotected else ", a more valuable piece than itself.")))
            else:
                made = [t for t in T.mover_threats(board, move) if t.gain >= 3]
                if made:
                    why.append((5, f"It threatens {commentary._threat_text(made[0])}."))

        # Plans: castling, development, the centre, open lines, rooks, kings and passed pawns.
        home = 0 if mover == chess.WHITE else 7
        if board.is_castling(move):
            side = "kingside" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "queenside"
            why.append((3, f"It castles {side}: the king is tucked away behind its pawns and the rook joins the game."))
        elif piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) == home and _phase(board) == "opening":
            centre = [chess.square_name(s) for s in CENTRE if s in after.attacks(move.to_square)]
            out = balance._developed(after, mover)
            why.append((4, f"It develops the {name} ({out} of 4 minor pieces are now out)"
                           + (f" and it now watches {' and '.join(centre[:2])} in the centre." if centre else ".")))
        elif piece.piece_type == chess.PAWN and move.to_square in CENTRE:
            why.append((4, f"The {chess.FILE_NAMES[chess.square_file(move.from_square)]}-pawn takes a share of the centre, which gives your pieces room."))
        elif piece.piece_type == chess.ROOK:
            f = chess.square_file(move.to_square)
            pawns = [p for p in (board.piece_at(chess.square(f, r)) for r in range(8)) if p and p.piece_type == chess.PAWN]
            if not pawns:
                why.append((4, f"The rook takes the open {chess.FILE_NAMES[f]}-file, where nothing blocks it."))
            elif not any(p.color == mover for p in pawns):
                why.append((4, f"The rook takes the half-open {chess.FILE_NAMES[f]}-file and lines up on their pawn."))
        elif piece.piece_type == chess.KING and _phase(board) == "endgame":
            why.append((4, "In the endgame the king is a strong piece, and this brings it toward the action."))
        elif piece.piece_type == chess.PAWN and to in balance._pawns(after, mover)["passed"]:
            why.append((3, f"It pushes the passed pawn on {to}: no enemy pawn can stop it, so support it toward promotion."))

        # Squares the moved piece now covers that the opponent's pieces could otherwise use.
        if piece.piece_type != chess.KING and not (info.fork or info.is_check):
            fresh = (after.attacks(move.to_square) & ~board.attacks(move.from_square)) if piece.piece_type != chess.PAWN \
                else after.attacks(move.to_square)
            taken = [sq for sq in fresh
                     if (after.piece_at(sq) is None or after.piece_at(sq).color == opp)
                     and any(after.piece_type_at(a) not in (chess.PAWN, chess.KING) for a in after.attackers(opp, sq))
                     and T.VALUE[piece.piece_type] <= 3]
            if taken and not any(text.startswith("From ") for _, text in why):
                squares = " and ".join(chess.square_name(s) for s in taken[:2])
                why.append((5, f"It now covers {squares}, so {_side(opp)}'s pieces cannot land {'there' if len(taken[:2]) == 1 else 'on them'} without being challenged."))

        best_open = None
        for sq, p in board.piece_map().items():
            if p.color != mover or sq == move.from_square or p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                continue
            gained = len(after.attacks(sq)) - len(board.attacks(sq))
            if gained >= 3 and (best_open is None or gained > best_open[0]):
                best_open = (gained, sq, p)
        if best_open:
            why.append((5, f"It opens lines for the {T.NAME[best_open[2].piece_type]} on {chess.square_name(best_open[1])}, which now covers {best_open[0]} more squares."))

        before, later = balance.scores(board, mover), balance.scores(after, mover)
        shifts = sorted(((later[k] - before[k], k) for k in GAIN if later[k] - before[k] >= 15), reverse=True)
        if shifts and len(why) < 4:
            why.append((6, GAIN[shifts[0][1]]))

        # Weighing it against the other options.
        if rank == 0 and second_gap is not None and second_gap >= 10:
            why.append((2, f"It is clearly the best: the next-best move leaves you about {second_gap:.0f}% worse in winning chances."))
        elif rank > 0 and gap >= 3:
            why.append((7, f"It gives up about {gap:.0f}% of your winning chances compared with {best_san}."))
        elif second_gap is not None and second_gap < 3:
            why.append((7, "Several moves score almost the same here, so this one is a matter of taste: pick the one that fits your plan."))

        if info.hangs_moved_piece and gap >= 4 and not board.is_capture(move):
            warn.append(f"Careful: the {name} on {to} can be captured after this move.")
        reply = line.pv[1] if len(line.pv) > 1 else None
        if reply is not None and gap >= 6:
            hit = T.threat_for_move(after, reply, mover)
            if hit and hit.kind in ("capture", "fork", "mate") and (hit.gain >= 3 or hit.kind == "mate"):
                warn.append(f"It allows {_side(opp)} to play {after.san(reply)}: {commentary._threat_text(hit)}.")

    if not why:
        why.append((8, PHASE_ADVICE[_phase(board)]))
    return why, warn


def _headline(board: chess.Board, move: chess.Move, v: commentary.Voice) -> str:
    """One plain sentence for what the move is. (The 'queen out early' warning is left out: the engine likes this move.)"""
    text, tags = commentary._describe_action(board, move, T.describe_move(board, move), v, board.ply() + 1)
    if "early-queen" in tags:
        return f"You move the queen to {chess.square_name(move.to_square)}."
    return text


def _reply_text(after: chess.Board, reply: chess.Move, side: chess.Color) -> str:
    """What the opponent's expected answer does, in a few words."""
    info = T.describe_move(after, reply)
    bits = []
    if after.is_capture(reply):
        bits.append(f"taking the {'pawn' if after.is_en_passant(reply) else T.NAME[info.captured]} on {chess.square_name(reply.to_square)}")
    if info.is_check:
        bits.append("giving check")
    if info.fork:
        bits.append("forking two of your pieces")
    return f"{_side(side)} would most likely answer {after.san(reply)}" + (f", {' and '.join(bits)}." if bits else ".")


def build(board: chess.Board, lines: list[Line], count: int = 2) -> dict:
    """The best `count` moves for the side to move, each with an evaluation, reasons, warnings and the engine's line."""
    mover = board.turn
    # A time-limited search can leave two lines a hair out of order, so present them best first.
    lines = sorted(lines, key=lambda ln: -ln.wp(mover))[:count]
    best_wp = lines[0].wp(mover)
    best_san = board.san(lines[0].move)
    v = commentary.Voice(mover)
    moves = []
    for rank, line in enumerate(lines):
        wp = line.wp(mover)
        gap = max(0.0, best_wp - wp)
        second_gap = max(0.0, best_wp - lines[1].wp(mover)) if rank == 0 and len(lines) > 1 else None
        why, warn = _reasons(board, line.move, line, gap, rank, second_gap, best_san)
        reasons = [text for _, text in sorted(why, key=lambda t: t[0])][:MAX_REASONS]
        headline = _headline(board, line.move, v)
        after = board.copy(stack=False)
        after.push(line.move)
        answer = None
        if len(line.pv) > 1 and not after.is_game_over():
            answer = {"san": after.san(line.pv[1]), "text": _reply_text(after, line.pv[1], not mover)}
        code, label = quality(gap, rank, (_mate_for(line, mover) or 0) < 0)
        moves.append({
            "uci": line.move.uci(), "san": board.san(line.move), "rank": rank + 1,
            "wp": round(wp, 1), "gap": round(gap, 1), "score": score_text(line, mover), "state": eval_words(wp),
            "quality": code, "label": label, "headline": headline, "reasons": reasons, "warnings": warn,
            "reply": answer, "line": pv_text(board, line.pv),
            "text": " ".join([headline] + reasons[:1]),
        })
    faced = [] if board.is_check() else [t for t in T.find_threats(board, mover) if t.gain >= 3][:2]
    context = {
        "side": _side(mover), "state": eval_words(best_wp), "score": score_text(lines[0], mover),
        "in_check": board.is_check(),
        "threats": [f"{_side(not mover)} threatens {commentary._threat_text(t)}." for t in faced],
        "verdict": balance.describe(board, mover)["verdict"]["text"],
    }
    return {"moves": moves, "context": context}

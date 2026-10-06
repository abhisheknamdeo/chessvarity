"""Turns a PGN game into coaching 'moments'.

Stockfish measures how much a move cost; tactics.py names what happened. The two
are combined here, then explain.py phrases the result for a young player.
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Callable

import chess
import chess.pgn

from . import balance as B
from . import tactics as T
from .engine import Engine, PositionEval, win_pct, wp_state
from .commentary import annotate as annotate_moves
from .explain import narrate, summarize, winning_story
from .openings import book

logging.getLogger("chess.engine").setLevel(logging.ERROR)

# Winning-chance points (0-100 scale) lost by a move.
INACCURACY, MISTAKE, BLUNDER = 5.0, 10.0, 20.0
THREAT_SWING = 10.0  # what the opponent would gain if we passed, to count as a real threat
NEAR_BEST = 8.0  # a candidate this close to the best move is "also good"
ATTACK_POTENTIAL_MIN = 40
MIN_SPIRAL = 3
OPENING_MOVES = 8  # full moves before which a run of defensive replies isn't called a spiral
MAX_MOMENTS = 8

Progress = Callable[[float, str], None]


def pick_color(game: chess.pgn.Game, player: str | None, color: str | None) -> chess.Color:
    if color:
        return chess.WHITE if color.lower().startswith("w") else chess.BLACK
    if player:
        needle = player.lower()
        for side, key in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
            if needle in game.headers.get(key, "").lower():
                return side
    raise ValueError(
        "Could not tell which side to coach. Pass the player's name as it appears "
        "in the PGN headers, or choose white/black."
    )


def pick_colors(game: chess.pgn.Game, player: str | None, color: str | None) -> list[chess.Color]:
    """Like pick_color, but 'both' analyzes each side in turn (handy for games without names)."""
    if color and color.lower() == "both":
        return [chess.WHITE, chess.BLACK]
    return [pick_color(game, player, color)]


def _result(token: str, final: chess.Board) -> str:
    """The PGN result, or the actual outcome when a pasted move list has no result."""
    if token in ("", "*") and final.is_checkmate():
        return "0-1" if final.turn == chess.WHITE else "1-0"
    return token or "*"


def _won(result: str, color: chess.Color) -> bool | None:
    """True/False for a decided game, None for a draw or unfinished game."""
    if result not in ("1-0", "0-1"):
        return None
    return (result == "1-0") == (color == chess.WHITE)


def _phase(board: chess.Board) -> str:
    non_pawn = sum(
        T.VALUE[p.piece_type]
        for p in board.piece_map().values()
        if p.piece_type not in (chess.PAWN, chess.KING)
    )
    if non_pawn <= 24:
        return "endgame"
    return "opening" if board.fullmove_number <= 10 else "middlegame"


def _is_retreat(board: chess.Board, move: chess.Move) -> bool:
    """A quiet piece move back toward the player's own side of the board."""
    piece = board.piece_at(move.from_square)
    if piece.piece_type in (chess.PAWN, chess.KING) or board.is_capture(move) or board.gives_check(move):
        return False
    delta = chess.square_rank(move.to_square) - chess.square_rank(move.from_square)
    return delta < 0 if piece.color == chess.WHITE else delta > 0


def accuracy(losses: list[float]) -> float:
    """Lichess-style accuracy from per-move winning-chance losses."""
    if not losses:
        return 100.0
    per_move = [max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * x) - 3.1669)) for x in losses]
    return sum(per_move) / len(per_move)


# --------------------------------------------------------------------------
# Per-move assessment
# --------------------------------------------------------------------------


def _attack_profile(board: chess.Board, move: chess.Move, info: T.MoveInfo) -> dict:
    """Does this move start or continue an attack? Records why."""
    mover, enemy = board.turn, not board.turn
    before = len(T.pieces_hitting(board, mover, T.king_zone(board, enemy)))
    b = board.copy(stack=False)
    b.push(move)
    after = len(T.pieces_hitting(b, mover, T.king_zone(b, enemy)))
    threats = [t for t in T.mover_threats(board, move) if t.gain >= 3]
    win = T.see_capture(board, move) if info.is_capture else 0
    reasons = []
    if info.is_check:
        reasons.append("check")
    if info.fork:
        reasons.append("fork")
    if info.pin:
        reasons.append("pin")
    if info.discovered:
        reasons.append("discovered")
    if threats:
        reasons.append("threat")
    if win > 0:
        reasons.append("wins_material")
    if after > before:
        reasons.append("king_pressure")
    return {"attacking": bool(reasons), "reasons": reasons, "threats": threats, "zone_after": after}


def _threat_still_works(
    board_after: chess.Board, threat: dict, victim: chess.Color, reply_eval: PositionEval
) -> bool:
    move: chess.Move = threat["move"]
    if move not in board_after.legal_moves:
        return False
    recognized: T.Threat | None = threat["threat"]
    if recognized is None:
        return reply_eval.best is not None and reply_eval.best.move == move
    now = T.threat_for_move(board_after, move, victim)
    return now is not None and (now.kind == "mate" or now.gain * 2 >= recognized.gain)


def _threat_dict(engine: Engine, board: chess.Board, color: chess.Color, best_wp: float):
    """What the opponent would do with a free move, if it matters."""
    null = engine.analyse_threat(board)
    if null is None or null.best is None:
        return None
    swing = best_wp - null.wp(color)
    if swing < THREAT_SWING:
        return None
    nb = T.opponent_to_move(board, color)
    move = null.best.move
    recognized = T.threat_for_move(nb, move, color)
    if recognized is None:
        # Several replies can be nearly as strong; prefer one we can name.
        for ln in null.lines[1:]:
            if ln.wp(color) - null.best.wp(color) > NEAR_BEST:
                break
            recognized = T.threat_for_move(nb, ln.move, color)
            if recognized:
                move = ln.move
                break
    if recognized is None:
        # The engine's idea isn't a simple capture/fork/mate: fall back to the
        # biggest concrete threat if there is one. A quiet move (castling, a
        # pawn push) is a plan, not a threat, so it is ignored unless it is a
        # forcing sacrifice the engine rates very highly.
        concrete = [t for t in T.find_threats(board, color) if t.gain >= 3]
        if concrete:
            recognized = concrete[0]
            move = recognized.move
        elif not (swing >= 20 and (nb.is_capture(move) or nb.gives_check(move))):
            return None
    return {
        "move": move,
        "san": nb.san(move) if move in nb.legal_moves else move.uci(),
        "swing": swing,
        "threat": recognized,
        "variation": T.variation_sans(nb, null.best.pv, 4),
    }


def _allowed_threat(
    after: chess.Board, nxt: PositionEval, color: chess.Color, loss: float, move: chess.Move, gained: int
):
    """The tactic the opponent gets after our move, if any (a capture, fork or mate).

    A recapture on the square we just captured on is an even trade, not a blunder:
    it only counts if it wins more than we just took.
    """
    if nxt.best is None or after.is_game_over():
        return None

    def real(found: T.Threat | None) -> bool:
        if found is None:
            return False
        recapture = found.kind == "capture" and found.move.to_square == move.to_square
        return not (recapture and found.gain <= gained)

    # The engine's top reply can be an unnamed sacrifice while a plain capture is
    # nearly as strong, so look at every near-best reply.
    for ln in nxt.lines:
        if ln.wp(color) - nxt.best.wp(color) > NEAR_BEST:
            break
        found = T.threat_for_move(after, ln.move, color)
        if real(found):
            return found
    if loss >= MISTAKE:
        for found in T.find_threats(after, color):
            if found.gain >= 3 and real(found):
                return found
    return None


def _assess(engine, boards, evals, moves, i, color) -> dict:
    board, move = boards[i], moves[i]
    ev, nxt = evals[i], evals[i + 1]
    best = ev.best
    best_wp = ev.wp(color)
    line = ev.line_for(move)
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        played_wp = 100.0
    else:
        played_wp = line.wp(color) if line else nxt.wp(color)
    loss = max(0.0, best_wp - played_wp)

    rec = {
        "i": i,
        "board": board,
        "move": move,
        "san": board.san(move),
        "ev": ev,
        "best_wp": best_wp,
        "played_wp": played_wp,
        "loss": loss,
        "actual": moves[i : i + 4],
        "after": after,
        "phase": _phase(board),
        "retreat": _is_retreat(board, move),
        "opponent_last": (boards[i - 1].san(moves[i - 1]), moves[i - 1]) if i > 0 else None,
        "reply": (after.san(moves[i + 1]), moves[i + 1]) if i + 1 < len(moves) else None,
    }
    if best is None:
        return {**rec, "category": None, "faced_threat": False, "made_threat": False}

    rec["threat"] = _threat_dict(engine, board, color, best_wp)
    concrete = [t for t in T.find_threats(board, color) if t.gain >= 3]
    rec["faced_threat"] = bool(board.is_check() or rec["threat"] or concrete)

    played_info = T.describe_move(board, move)
    rec["played_info"] = played_info
    rec["played_attack"] = _attack_profile(board, move, played_info)
    rec["made_threat"] = played_info.is_check or bool(rec["played_attack"]["threats"])

    best_info = T.describe_move(board, best.move)
    rec["best_info"] = best_info
    rec["best_attack"] = _attack_profile(board, best.move, best_info)
    rec["best_gain"] = T.pv_gain(board, best.pv)
    rec["attack_potential"] = T.attack_potential(board, color)
    rec["own_king_danger"] = T.attack_potential(board, not color)["total"]

    # Second-best gap: is the best move the *only* good one?
    rec["gap"] = best_wp - ev.lines[1].wp(color) if len(ev.lines) > 1 else 0.0
    prev = moves[i - 1] if i > 0 else None
    rec["is_recapture"] = bool(
        best_info.is_capture and prev and boards[i - 1].is_capture(prev) and prev.to_square == best.move.to_square
    )

    # What did the move allow?
    gained = 0
    if board.is_capture(move):
        taken = board.piece_at(move.to_square)
        gained = T.VALUE[taken.piece_type] if taken else 1
    rec["allowed"] = _allowed_threat(after, nxt, color, loss, move, gained)

    still_works = bool(
        rec["threat"] and _threat_still_works(after, rec["threat"], color, nxt)
    )
    rec["threat_ignored"] = still_works

    # Attack chance: any near-best candidate that attacks, while we're not under fire.
    attack_candidates = [
        ln for ln in ev.lines
        if best_wp - ln.wp(color) <= NEAR_BEST
        and _attack_profile(board, ln.move, T.describe_move(board, ln.move))["attacking"]
    ]
    rec["attack_candidates"] = attack_candidates
    rec["attack_chance"] = bool(
        attack_candidates
        and rec["attack_potential"]["total"] >= ATTACK_POTENTIAL_MIN
        and not rec["faced_threat"]
    )
    rec["tactic_chance"] = bool(
        (best_info.is_mate or (best_info.forcing or best_info.fork or best_info.pin or best_info.discovered))
        and rec["gap"] >= 15
        and best_wp >= 50
        and not rec["is_recapture"]
    )
    return _categorize(rec)


def _categorize(rec: dict) -> dict:
    loss = rec["loss"]
    cat = None
    if loss >= MISTAKE:
        best_info = rec["best_info"]
        if best_info.is_mate and not rec["threat_ignored"]:
            cat = "missed_tactic"
        elif rec["threat_ignored"]:
            cat = "missed_threat"
        elif rec["allowed"] is not None:
            cat = "hung_piece"
        elif rec["tactic_chance"] or (best_info.forcing and rec["best_gain"] >= 2):
            cat = "missed_tactic"
        elif rec["best_attack"]["attacking"] and rec["attack_potential"]["total"] >= ATTACK_POTENTIAL_MIN:
            cat = "missed_attack"
        elif loss >= 15:
            cat = "mistake"
    elif rec["attack_chance"] and not rec["played_attack"]["attacking"] and loss >= INACCURACY:
        # Only when the quiet move actually cost something: playing the engine's
        # own choice is never a "missed" attack.
        cat = "missed_attack"
    rec["category"] = cat
    return rec


# --------------------------------------------------------------------------
# Whole game
# --------------------------------------------------------------------------


def _find_spirals(records: list[dict]) -> list[list[dict]]:
    """Runs of consecutive moves where the player only reacted and never threatened."""
    runs, current = [], []
    for rec in records:
        # Early moves answer pawn and knight attacks while developing; that is normal, not passivity.
        reactive = (
            rec["board"].fullmove_number >= OPENING_MOVES
            and rec.get("faced_threat")
            and not rec.get("made_threat")
        )
        if reactive:
            current.append(rec)
        else:
            if len(current) >= MIN_SPIRAL:
                runs.append(current)
            current = []
    if len(current) >= MIN_SPIRAL:
        runs.append(current)
    return runs


def analyze_game(
    game: chess.pgn.Game,
    engine: Engine,
    color: chess.Color,
    progress: Progress | None = None,
    max_moments: int = MAX_MOMENTS,
    player_name: str | None = None,
) -> dict:
    progress = progress or (lambda f, m: None)
    engine.new_game()
    board = game.board()
    boards, moves, played = [board.copy(stack=False)], [], []
    for move in game.mainline_moves():
        san = board.san(move)
        board.push(move)
        moves.append(move)
        played.append({"san": san, "uci": move.uci(), "fen": board.fen()})
        boards.append(board.copy(stack=False))
    if not moves:
        raise ValueError("The game has no moves.")

    evals = []
    for n, b in enumerate(boards):
        progress(0.6 * n / len(boards), f"Analysing position {n + 1} of {len(boards)}")
        evals.append(engine.analyse(b))

    player_plies = [i for i, m in enumerate(moves) if boards[i].turn == color]
    records = []
    for n, i in enumerate(player_plies):
        progress(0.6 + 0.35 * n / len(player_plies), f"Studying move {n + 1} of {len(player_plies)}")
        records.append(_assess(engine, boards, evals, moves, i, color))
    progress(0.97, "Writing the coaching notes")

    spirals = _find_spirals(records)
    moments = _build_moments(records, spirals, color, max_moments)
    losses = [r["loss"] for r in records]
    skills = _skill_stats(records, spirals)
    result_token = _result(game.headers.get("Result", "*"), boards[-1])
    won = _won(result_token, color)
    counts = {
        "blunders": sum(1 for x in losses if x >= BLUNDER),
        "mistakes": sum(1 for x in losses if MISTAKE <= x < BLUNDER),
        "inaccuracies": sum(1 for x in losses if INACCURACY <= x < MISTAKE),
    }
    headers = game.headers
    side_name = "White" if color == chess.WHITE else "Black"

    def named(key: str) -> str:
        value = headers.get(key, "?")
        return key if value in ("", "?") else value

    player_name = player_name or named(side_name)
    result = {
        "game": {
            "player": player_name,
            "white": named("White"),
            "black": named("Black"),
            "white_elo": headers.get("WhiteElo", ""),
            "black_elo": headers.get("BlackElo", ""),
            "result": result_token,
            "event": headers.get("Event", ""),
            "date": "" if "?" in headers.get("Date", "") else headers.get("Date", ""),
            "player_color": "white" if color == chess.WHITE else "black",
            "moves": len(moves),
        },
        "accuracy": round(accuracy(losses), 1),
        "counts": counts,
        "skills": skills,
        "moments": moments,
        "spirals": [
            {"start": r[0]["board"].fullmove_number, "end": r[-1]["board"].fullmove_number, "length": len(r)}
            for r in spirals
        ],
        "start_fen": boards[0].fen(),
        "moves": played,
        "timeline": _timeline(boards, evals),
        "habits": _habits_raw(records, boards, spirals, color, moments),
        "how_to_win": _how_to_win(records, color, won),
        "commentary": _commentary(game, boards, moves, evals, color),
    }
    result["summary"] = summarize(result)
    progress(1.0, "Done")
    return result


def _commentary(game: chess.pgn.Game, boards, moves, evals, color: chess.Color) -> list[dict]:
    """A sentence or two for every move of the game, spoken to the player."""
    opening, book_ply = book().detect(game)
    notes = annotate_moves(boards, moves, evals, viewpoint=color, book_ply=book_ply,
                           opening_name=opening.name if opening else "")
    return [{"ply": n["ply"], "text": n["text"], "tags": n["tags"]} for n in notes]


def _timeline(boards: list[chess.Board], evals: list[PositionEval]) -> list[dict]:
    """White's winning chances after every ply, plus what each move cost the side that played it."""
    out = [{"ply": 0, "wp": round(evals[0].wp(chess.WHITE), 1), "loss": 0.0, "white_moved": None}]
    for k in range(1, len(evals)):
        mover = boards[k - 1].turn
        loss = max(0.0, evals[k - 1].wp(mover) - evals[k].wp(mover))
        out.append(
            {"ply": k, "wp": round(evals[k].wp(chess.WHITE), 1), "loss": round(loss, 1),
             "white_moved": mover == chess.WHITE}
        )
    return out


def _habits_raw(records: list[dict], boards, spirals, color: chess.Color, moments: list[dict]) -> dict:
    """Counts behind the cross-game 'habits' (attacking, passivity, tactics, opening discipline)."""
    rated = [r for r in records if r.get("best_info")]
    free = [r for r in rated if not r["faced_threat"]]
    by_phase = {p: {"moves": 0, "loss": 0.0} for p in ("opening", "middlegame", "endgame")}
    for r in records:
        by_phase[r["phase"]]["moves"] += 1
        by_phase[r["phase"]]["loss"] += r["loss"]
    early = [r for r in records if r["board"].fullmove_number <= 10]
    castled_by = next((r["board"].fullmove_number for r in records if r["board"].is_castling(r["move"])), None)

    # Pieces moved twice in the first eight moves (development wasted on shuffling).
    moved: dict[int, int] = {}
    repeats = 0
    for r in records:
        if r["board"].fullmove_number > 8:
            break
        piece = r["board"].piece_type_at(r["move"].from_square)
        if piece in (chess.PAWN, chess.KING) or r["board"].is_castling(r["move"]):
            continue
        count = moved.pop(r["move"].from_square, 0) + 1
        moved[r["move"].to_square] = count
        if count == 2:
            repeats += 1

    counts = {}
    for m in moments:
        counts[m["category"]] = counts.get(m["category"], 0) + 1
    return {
        "moves": len(records),
        "by_phase": {p: {"moves": d["moves"], "loss": round(d["loss"], 1)} for p, d in by_phase.items()},
        "free_moves": len(free),
        "free_attacking": sum(1 for r in free if r["played_attack"]["attacking"]),
        "checks": sum(1 for r in rated if r["played_info"].is_check),
        "captures": sum(1 for r in rated if r["played_info"].is_capture),
        "made_threat": sum(1 for r in rated if r["made_threat"]),
        "retreats": sum(1 for r in records if r["retreat"]),
        "reactive": sum(1 for r in rated if r["faced_threat"] and not r["made_threat"]),
        "spiral_moves": sum(len(s) for s in spirals),
        "zone_pressure": round(sum(r["played_attack"]["zone_after"] for r in rated) / max(1, len(rated)), 2),
        "opening": {
            "developed": B._developed(boards[early[-1]["i"] + 1], color) if early else 0,
            "castled_by": castled_by,
            "early_queen": sum(
                1 for r in early
                if r["board"].fullmove_number <= 6 and r["board"].piece_type_at(r["move"].from_square) == chess.QUEEN
            ),
            "repeats": repeats,
        },
        "moments": counts,
    }


def _how_to_win(records: list[dict], color: chess.Color, won: bool | None) -> list[dict]:
    """Positions where the player was clearly better (or the game turned) and what was strongest.

    Skipped for won games: there the player already found a way.
    """
    if won:
        return []
    picks: list[tuple[float, dict, str]] = []
    for rec in records:
        if not rec.get("best_info"):
            continue
        before, loss = rec["best_wp"], rec["loss"]
        if before >= 60 and loss >= 12:
            kind = "threw_away_win" if before >= 75 else "better_position"
            picks.append((before - 50 + loss, rec, kind))
    if not picks:
        turning = next(
            (r for r in records if r.get("best_info") and r["best_wp"] >= 40 and r["loss"] >= 15), None
        )
        if turning:
            picks.append((turning["loss"], turning, "turning_point"))
    picks.sort(key=lambda p: -p[0])
    items = []
    for _, rec, kind in sorted(picks[:3], key=lambda p: p[1]["i"]):
        moment = _moment(rec, color, line_plies=8)
        moment["kind"] = kind
        winning_story(moment)
        items.append(moment)
    return items


def _candidate_list(rec: dict, color: chess.Color) -> list[dict]:
    board, ev = rec["board"], rec["ev"]
    out = []
    for ln in ev.lines[:4]:
        info = T.describe_move(board, ln.move)
        profile = _attack_profile(board, ln.move, info)
        role = "attacks" if profile["attacking"] else "improves"
        if rec.get("threat"):
            after = board.copy(stack=False)
            after.push(ln.move)
            if not _threat_still_works(after, rec["threat"], color, ev):
                role = "defends" if not profile["attacking"] else "counterattacks"
        out.append(
            {
                "san": info.san,
                "uci": ln.move.uci(),
                "role": role,
                "reasons": profile["reasons"],
                "wp": round(ln.wp(color), 1),
                "good": rec["best_wp"] - ln.wp(color) <= NEAR_BEST,
                "gives_check": info.is_check,
                "captures": T.NAME[info.captured] if info.captured else None,
                "threat_san": profile["threats"][0].san if profile["threats"] else None,
            }
        )
    return out


def _think_checklist(rec: dict, color: chess.Color, candidates: list[dict]) -> dict:
    board = rec["board"]
    checks = [board.san(m) for m in board.legal_moves if board.gives_check(m)]
    good_checks = [c["san"] for c in candidates if c["gives_check"] and c["good"]]
    captures = [
        board.san(m)
        for m in board.legal_moves
        if board.is_capture(m) and T.see_capture(board, m) > 0
    ]
    new_threats = [c["san"] for c in candidates if c["good"] and c["threat_san"]]
    best_info = rec["best_info"]
    if best_info.is_check:
        key = "checks"
    elif best_info.is_capture and T.see_capture(board, rec["ev"].best.move) > 0:
        key = "captures"
    elif rec.get("threat") and candidates and candidates[0]["role"] in ("defends", "counterattacks"):
        key = "threat"
    elif rec["best_attack"]["threats"]:
        key = "new_threats"
    elif rec["own_king_danger"] >= 40:
        key = "king_safety"
    else:
        key = None
    return {
        "threat": {"available": bool(rec.get("threat") or rec["faced_threat"])},
        "checks": {"available": bool(checks), "moves": checks[:4], "good": good_checks[:3]},
        "captures": {"available": bool(captures), "moves": captures[:4]},
        "new_threats": {"available": bool(new_threats), "moves": new_threats[:3]},
        "king_safety": {"available": rec["own_king_danger"] >= 40, "danger": rec["own_king_danger"]},
        "key": key,
    }


def _moment(rec: dict, color: chess.Color, line_plies: int = 6) -> dict:
    board = rec["board"]
    ev: PositionEval = rec["ev"]
    candidates = _candidate_list(rec, color)
    balance_before = B.describe(board, color, rec["best_wp"])
    balance_after = B.describe(rec["after"], color, rec["played_wp"])
    threat = rec.get("threat")
    threat_out = None
    if threat:
        t = threat["threat"]
        threat_out = {
            "san": threat["san"],
            "uci": threat["move"].uci(),
            "kind": t.kind if t else "positional",
            "piece": T.NAME[t.piece_type] if t else None,
            "from": T.sq_name(t.from_square) if t else T.sq_name(threat["move"].from_square),
            "to": T.sq_name(threat["move"].to_square),
            "targets": [{"square": T.sq_name(s), "piece": T.NAME[p]} for s, p in t.targets] if t else [],
            "defended": t.defended if t else False,
            "gain": t.gain if t else 0,
            "variation": threat["variation"],
        }
    allowed = rec.get("allowed")
    allowed_out = None
    if allowed:
        allowed_out = {
            "san": allowed.san,
            "uci": allowed.move.uci(),
            "kind": allowed.kind,
            "piece": T.NAME[allowed.piece_type],
            "from": T.sq_name(allowed.from_square),
            "to": T.sq_name(allowed.move.to_square),
            "targets": [{"square": T.sq_name(s), "piece": T.NAME[p]} for s, p in allowed.targets],
            "defended": allowed.defended,
            "gain": allowed.gain,
        }
    best_info = rec["best_info"]
    return {
        "ply": rec["i"] + 1,
        "move_number": board.fullmove_number,
        "side": "white" if color == chess.WHITE else "black",
        "category": rec["category"],
        "loss": round(rec["loss"], 1),
        "state_before": wp_state(rec["best_wp"]),
        "state_after": wp_state(rec["played_wp"]),
        "wp_before": round(rec["best_wp"], 1),
        "wp_after": round(rec["played_wp"], 1),
        "fen": board.fen(),
        "played": {"san": rec["san"], "uci": rec["move"].uci()},
        "best": {
            "san": best_info.san,
            "uci": best_info.uci,
            "check": best_info.is_check,
            "mate": best_info.is_mate,
            "fork": [T.NAME[p] for _, p in best_info.fork.targets] if best_info.fork else None,
            "pin": T.NAME[best_info.pin[1]] if best_info.pin else None,
            "discovered": T.NAME[best_info.discovered[1]] if best_info.discovered else None,
            "captures": T.NAME[best_info.captured] if best_info.captured else None,
            "gain": rec["best_gain"],
            "reasons": rec["best_attack"]["reasons"],
            "threat_san": rec["best_attack"]["threats"][0].san if rec["best_attack"]["threats"] else None,
        },
        "opponent_last": (
            {"san": rec["opponent_last"][0], "uci": rec["opponent_last"][1].uci()}
            if rec["opponent_last"] else None
        ),
        "reply": {"san": rec["reply"][0], "uci": rec["reply"][1].uci()} if rec["reply"] else None,
        "threat": threat_out,
        "allowed": allowed_out,
        "candidates": candidates,
        "variation": T.variation_sans(board, ev.best.pv, line_plies),
        "actual": T.variation_sans(board, rec["actual"], 4),
        "balance": {
            "before": balance_before,
            "after": balance_after,
            "shift": B.shift(balance_before, balance_after),
        },
        "attack_potential": rec["attack_potential"],
        "think": _think_checklist(rec, color, candidates),
    }


def _build_moments(records, spirals, color, max_moments) -> list[dict]:
    moments = []
    previous = None
    for rec in records:
        cat = rec.get("category")
        if not cat:
            previous = None
            continue
        moment = _moment(rec, color)
        same_threat = (
            previous is not None
            and cat == "missed_threat"
            and previous["category"] == "missed_threat"
            and previous["threat"]["san"] == moment["threat"]["san"]
            and previous["ply"] + 2 == moment["ply"]
        )
        if same_threat:
            # The same threat ignored again: report it once.
            previous["repeats"] = previous.get("repeats", 0) + 1
            previous["ply_last"] = moment["ply"]
            previous["loss"] = max(previous["loss"], moment["loss"])
            previous["importance"] = max(previous["importance"], moment["loss"] + 6)
            previous["state_after"] = moment["state_after"]
            continue
        bonus = {"missed_threat": 6, "hung_piece": 4, "missed_attack": 2, "mistake": -5}.get(cat, 0)
        moment["importance"] = rec["loss"] + bonus
        moments.append(moment)
        previous = moment
    for moment in moments:
        narrate(moment)

    for run in spirals:
        chance = next((r for r in run if r.get("attack_chance")), None)
        anchor = chance or run[-1]
        moment = _moment(anchor, color)
        moment.update(
            {
                "category": "defensive_spiral",
                "importance": 8 + 2 * len(run),
                "spiral": {
                    "start": run[0]["board"].fullmove_number,
                    "end": run[-1]["board"].fullmove_number,
                    "length": len(run),
                    "moves": [
                        {
                            "number": r["board"].fullmove_number,
                            "san": r["san"],
                            "faced": r["opponent_last"][0] if r["opponent_last"] else "",
                        }
                        for r in run
                    ],
                    "chance_at": chance["board"].fullmove_number if chance else None,
                },
            }
        )
        narrate(moment)
        moments.append(moment)

    moments.sort(key=lambda m: m["importance"], reverse=True)
    keep = moments[:max_moments]
    keep.sort(key=lambda m: m["ply"])
    return keep


def _skill_stats(records: list[dict], spirals) -> dict:
    """How often the player did the right thing when the chance came up."""

    def rate(opportunities: int, taken: int):
        return {
            "opportunities": opportunities,
            "handled": taken,
            "score": round(100 * taken / opportunities) if opportunities else None,
        }

    rated = [r for r in records if r.get("best_info")]
    faced = [r for r in rated if r.get("threat")]
    attack_ops = [r for r in rated if r["attack_chance"]]
    tactic_ops = [r for r in rated if r["tactic_chance"]]
    return {
        "threat_recognition": rate(len(faced), sum(1 for r in faced if not r["threat_ignored"])),
        "blunder_check": rate(len(rated), sum(1 for r in rated if r["allowed"] is None or r["loss"] < MISTAKE)),
        "tactics": rate(len(tactic_ops), sum(1 for r in tactic_ops if r["loss"] < INACCURACY)),
        "attacking": rate(
            len(attack_ops),
            sum(1 for r in attack_ops if r["played_attack"]["attacking"] or r["loss"] < INACCURACY),
        ),
        "initiative": rate(
            len(rated), len(rated) - sum(len(run) for run in spirals)
        ),
    }

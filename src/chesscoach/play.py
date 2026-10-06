"""Play against the computer from any position, and ask it for a hint."""

from __future__ import annotations

import math
import os
import random
import threading
from pathlib import Path

import chess
import chess.engine

from . import suggest
from .engine import DEFAULT_ENGINE, MATE_CP, Line

SUGGEST_DEPTH = 20        # suggestions search up to this deep, or for SUGGEST_SECONDS, whichever comes first
SUGGEST_SECONDS = 1.2

# How the computer plays at each level.
#
# It looks at several candidate moves with Stockfish at full strength, then chooses like a human of that strength
# would: usually a good move, sometimes a weaker one. `temp` (in centipawns) sets how readily it picks a weaker move,
# `cap` the worst move it will ever pick (None = anything), `blunder` the chance of a completely random move (for
# beginners). `book` is how many plies it follows real named openings. Tuned by measuring average centipawn loss
# against a strong reference (roughly: 2400 ~ 20, 2000 ~ 35, 1700 ~ 55, 1400 ~ 85, 1200 ~ 120, 1000 ~ 170).
# Stockfish's own UCI_Elo limiter was used before, but it is calibrated for long time controls and, with a fraction
# of a second per move, played well below its label and made oddly random moves.
LEVELS = [
    {"id": 1, "label": "Beginner", "elo": 800, "temp": 300, "cap": None, "blunder": 0.12, "depth": 6, "time": 0.25, "lines": 8, "book": 4},
    {"id": 2, "label": "Casual", "elo": 1000, "temp": 280, "cap": 900, "blunder": 0.05, "depth": 8, "time": 0.3, "lines": 8, "book": 6},
    {"id": 3, "label": "Improving", "elo": 1200, "temp": 240, "cap": 700, "blunder": 0.0, "depth": 10, "time": 0.4, "lines": 8, "book": 8},
    {"id": 4, "label": "Club player", "elo": 1400, "temp": 120, "cap": 400, "blunder": 0.0, "depth": 12, "time": 0.5, "lines": 8, "book": 10},
    {"id": 5, "label": "Strong club", "elo": 1700, "temp": 75, "cap": 250, "blunder": 0.0, "depth": 14, "time": 0.7, "lines": 8, "book": 12},
    {"id": 6, "label": "Expert", "elo": 2000, "temp": 65, "cap": 200, "blunder": 0.0, "depth": 16, "time": 1.0, "lines": 8, "book": 16},
    {"id": 7, "label": "Master", "elo": 2400, "temp": 30, "cap": 90, "blunder": 0.0, "depth": 18, "time": 1.5, "lines": 6, "book": 20},
    {"id": 8, "label": "Full strength", "elo": 3000, "temp": 0, "cap": 0, "blunder": 0.0, "depth": 22, "time": 2.5, "lines": 1, "book": 20},
]
MATE = 10000


def _key(board: chess.Board) -> str:
    return board.epd()


_BOOK: dict[str, dict[str, int]] | None = None


def opening_book() -> dict[str, dict[str, int]]:
    """{position: {move (UCI): how many named lines continue with it}}, from the 3,800 named openings."""
    global _BOOK
    if _BOOK is None:
        from .openings import book as openings_book
        table: dict[str, dict[str, int]] = {}
        for opening in openings_book().openings:
            board = chess.Board()
            for san in opening.sans:
                move = board.parse_san(san)
                bucket = table.setdefault(_key(board), {})
                bucket[move.uci()] = bucket.get(move.uci(), 0) + 1
                board.push(move)
        _BOOK = table
    return _BOOK


def _plies_played(board: chess.Board) -> int:
    return (board.fullmove_number - 1) * 2 + (0 if board.turn == chess.WHITE else 1)


def _pick(rng: random.Random, candidates: list[tuple[chess.Move, float]], temp: float) -> chess.Move:
    """Choose among (move, loss) pairs: the smaller the loss, the likelier; temp=0 always takes the best."""
    if temp <= 0 or len(candidates) == 1:
        return candidates[0][0]
    weights = [math.exp(-loss / temp) for _, loss in candidates]
    return rng.choices([m for m, _ in candidates], weights=weights, k=1)[0]


def game_state(board: chess.Board) -> dict:
    """Whether the game is over, and why, in words a player understands."""
    if board.is_checkmate():
        reason = "checkmate"
    elif board.is_stalemate():
        reason = "stalemate"
    elif board.is_insufficient_material():
        reason = "not enough material to checkmate"
    elif board.can_claim_threefold_repetition() or board.is_repetition(3):
        reason = "the same position three times"
    elif board.can_claim_fifty_moves():
        reason = "the fifty-move rule"
    else:
        reason = ""
    over = bool(reason)
    return {"over": over, "result": board.result(claim_draw=True) if over else None, "reason": reason, "check": board.is_check()}


class PlayEngine:
    """One Stockfish shared by all players' games, used one request at a time."""

    def __init__(self, path: str | os.PathLike | None = None):
        self._path = Path(path or os.environ.get("STOCKFISH_PATH") or DEFAULT_ENGINE)
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.Lock()
        self._rng = random.Random()

    def _start(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            if not self._path.exists():
                raise FileNotFoundError(f"Stockfish not found at {self._path}")
            self._engine = chess.engine.SimpleEngine.popen_uci(str(self._path))
            self._engine.configure({"Threads": 1, "Hash": 128})
        return self._engine

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.quit()
                self._engine = None

    def reply(self, board: chess.Board, level_id: int) -> chess.Move:
        level = next((lv for lv in LEVELS if lv["id"] == level_id), LEVELS[4])
        legal = list(board.legal_moves)
        if len(legal) == 1:
            return legal[0]
        rng = self._rng

        # 1. The opening: real named lines, weighted by how many variations follow each move.
        if _plies_played(board) < level["book"]:
            known = opening_book().get(_key(board))
            if known:
                moves = [chess.Move.from_uci(u) for u in known]
                return rng.choices(moves, weights=[math.sqrt(n) for n in known.values()], k=1)[0]

        # 2. A beginner sometimes just plays something.
        if level["blunder"] and rng.random() < level["blunder"]:
            return rng.choice(legal)

        # 3. Candidate moves from a full-strength search.
        with self._lock:
            engine = self._start()
            engine.configure({"UCI_LimitStrength": False, "Skill Level": 20})
            infos = engine.analyse(board, chess.engine.Limit(depth=level["depth"], time=level["time"]),
                                   multipv=min(level["lines"], len(legal)))
        scored = []
        for info in infos:
            pv = info.get("pv")
            if pv:
                scored.append((pv[0], info["score"].pov(board.turn).score(mate_score=MATE)))
        if not scored:
            return legal[0]
        best = scored[0][1]
        candidates = [(move, best - score) for move, score in scored]
        # Never throw away a won position by more than the level's cap; always take a mate the level can see.
        if level["cap"] is not None:
            candidates = [c for c in candidates if c[1] <= level["cap"]] or candidates[:1]
        if best >= MATE - 100 and level["elo"] >= 1200:
            return scored[0][0]
        return _pick(rng, candidates, level["temp"])

    def suggest(self, board: chess.Board, n: int = 2) -> dict:
        """The engine's best `n` moves for the side to move: evaluation, reasons, warnings and the line it expects.

        One search of about a second with several lines, so every candidate is judged at the same depth.
        """
        with self._lock:
            engine = self._start()
            engine.configure({"UCI_LimitStrength": False, "Skill Level": 20})
            infos = engine.analyse(board, chess.engine.Limit(depth=SUGGEST_DEPTH, time=SUGGEST_SECONDS), multipv=n)
        lines = []
        for info in infos:
            pv = info.get("pv") or []
            if pv:
                white = info["score"].white()
                lines.append(Line(pv[0], white.score(mate_score=MATE_CP), white.mate(), list(pv)))
        return suggest.build(board, lines, n)

    def hint(self, board: chess.Board) -> dict:
        """The engine's best move with the reasons for it."""
        result = self.suggest(board, 1)
        return {**result["moves"][0], "context": result["context"]}

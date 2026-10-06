"""Stockfish wrapper: cached multi-line analysis and null-move ('what is he threatening?') probes."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine

DEFAULT_ENGINE = (
    Path(__file__).resolve().parents[2]
    / "engines"
    / "stockfish"
    / "stockfish-windows-x86-64-universal.exe"
)
MATE_CP = 10000


def win_pct(cp: float) -> float:
    """Centipawns (White's view) to White's winning chances, 0-100 (Lichess's curve)."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


@dataclass
class Line:
    move: chess.Move
    cp: int  # White's point of view; mates are +-MATE_CP
    mate: int | None  # White's point of view: >0 White mates in n, <0 Black mates in n
    pv: list[chess.Move]

    def wp(self, color: chess.Color) -> float:
        white = win_pct(self.cp)
        return white if color == chess.WHITE else 100 - white


@dataclass
class PositionEval:
    fen: str
    lines: list[Line] = field(default_factory=list)
    terminal_white_wp: float | None = None  # set for checkmate / stalemate

    @property
    def best(self) -> Line | None:
        return self.lines[0] if self.lines else None

    def wp(self, color: chess.Color) -> float:
        """Winning chances for `color` assuming best play from the side to move."""
        if self.best is None:
            white = self.terminal_white_wp if self.terminal_white_wp is not None else 50.0
            return white if color == chess.WHITE else 100 - white
        return self.best.wp(color)

    def line_for(self, move: chess.Move) -> Line | None:
        return next((ln for ln in self.lines if ln.move == move), None)


def wp_state(wp: float) -> str:
    """Plain-language description of a winning-chances number."""
    if wp >= 80:
        return "winning"
    if wp >= 60:
        return "better"
    if wp >= 40:
        return "about equal"
    if wp >= 20:
        return "worse"
    return "losing"


class Engine:
    def __init__(
        self,
        path: str | os.PathLike | None = None,
        depth: int = 12,
        multipv: int = 4,
        threads: int = 1,
        hash_mb: int = 128,
        max_seconds: float | None = None,
    ):
        path = Path(path or os.environ.get("STOCKFISH_PATH") or DEFAULT_ENGINE)
        if not path.exists():
            raise FileNotFoundError(
                f"Stockfish not found at {path}. Set STOCKFISH_PATH or pass --engine."
            )
        self.depth = depth
        self.max_seconds = max_seconds  # optional cap per position, so a search can never run away
        self.multipv = multipv
        self._engine = chess.engine.SimpleEngine.popen_uci(str(path))
        # One thread keeps the search deterministic, so re-analysing a game gives the same coaching.
        self._engine.configure({"Threads": threads, "Hash": hash_mb})
        self._cache: dict[str, PositionEval] = {}
        self._game = object()

    def new_game(self) -> None:
        """Forget everything about the previous game (cache and the engine's hash tables)."""
        self._cache.clear()
        self._game = object()

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def analyse(self, board: chess.Board) -> PositionEval:
        fen = board.fen()
        cached = self._cache.get(fen)
        if cached:
            return cached
        result = PositionEval(fen)
        if board.is_checkmate():
            # The side to move has been mated.
            result.terminal_white_wp = 0.0 if board.turn == chess.WHITE else 100.0
        elif board.is_game_over():
            result.terminal_white_wp = 50.0
        else:
            infos = self._engine.analyse(
                board, chess.engine.Limit(depth=self.depth, time=self.max_seconds), multipv=self.multipv, game=self._game
            )
            for info in infos:
                pv = info.get("pv") or []
                if not pv:
                    continue
                white = info["score"].white()
                result.lines.append(
                    Line(pv[0], white.score(mate_score=MATE_CP), white.mate(), list(pv))
                )
        self._cache[fen] = result
        return result

    def analyse_threat(self, board: chess.Board) -> PositionEval | None:
        """Analyze the position as if the side to move passed. None when in check."""
        if board.is_check():
            return None
        probe = board.copy(stack=False)
        probe.push(chess.Move.null())
        return self.analyse(probe)

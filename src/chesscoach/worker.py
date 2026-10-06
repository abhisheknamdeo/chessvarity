"""Background analysis queue: one engine, one game at a time, resumable after a restart."""

from __future__ import annotations

import io
import json
import logging
import queue
import threading
import time
from typing import Callable

import chess
import chess.pgn

from .analyzer import analyze_game
from .db import Database
from .engine import Engine

log = logging.getLogger("chesscoach.worker")


class AnalysisWorker:
    def __init__(self, db: Database, engine_factory: Callable[[], Engine], close_engine: bool = True):
        self.db = db
        self._factory = engine_factory
        self._close_engine = close_engine
        self._engine: Engine | None = None
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # Anything interrupted by a restart goes back in the queue.
        self.db.run("UPDATE games SET status = 'queued', progress = 0 WHERE status = 'analyzing'")
        # Games analysed before commentary existed are analysed again (same result, plus commentary).
        self.db.run(
            "UPDATE games SET status = 'queued', progress = 0 WHERE status = 'done' AND analysis NOT LIKE ?",
            ('%"commentary"%',),
        )
        for row in self.db.all("SELECT id FROM games WHERE status = 'queued' ORDER BY id"):
            self._queue.put(row["id"])
        self._thread = threading.Thread(target=self._loop, name="analysis-worker", daemon=True)
        self._thread.start()

    def submit(self, game_id: int) -> None:
        self._queue.put(game_id)

    def wait_idle(self, timeout: float = 120.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.1)
        return False

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=10)
        if self._engine is not None and self._close_engine:
            self._engine.close()
        self._engine = None

    def _loop(self) -> None:
        while True:
            game_id = self._queue.get()
            try:
                if game_id is None:
                    return
                self._process(game_id)
            except Exception:  # never let one bad game stop the queue
                log.exception("analysis of game %s failed unexpectedly", game_id)
            finally:
                self._queue.task_done()

    def _process(self, game_id: int) -> None:
        row = self.db.one(
            "SELECT g.*, p.name AS player_name FROM games g JOIN players p ON p.id = g.player_id WHERE g.id = ?",
            (game_id,),
        )
        if row is None or row["status"] != "queued":
            return  # deleted, or already handled
        self.db.run("UPDATE games SET status = 'analyzing', progress = 0, error = '' WHERE id = ?", (game_id,))
        last = [0.0]

        def progress(fraction: float, _message: str) -> None:
            now = time.time()
            if now - last[0] > 0.6:
                last[0] = now
                self.db.run("UPDATE games SET progress = ? WHERE id = ?", (round(fraction, 3), game_id))

        try:
            game = chess.pgn.read_game(io.StringIO(row["pgn"]))
            color = chess.WHITE if row["color"] == "white" else chess.BLACK
            if self._engine is None:
                self._engine = self._factory()
            result = analyze_game(game, self._engine, color, progress, player_name=row["player_name"])
            self.db.run(
                "UPDATE games SET status = 'done', progress = 1, accuracy = ?, analysis = ?, error = '' WHERE id = ?",
                (result["accuracy"], json.dumps(result), game_id),
            )
        except Exception as err:
            log.exception("analysis of game %s failed", game_id)
            self.db.run("UPDATE games SET status = 'error', error = ? WHERE id = ?", (str(err)[:300], game_id))

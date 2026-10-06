"""Play against the computer from any position."""

from __future__ import annotations

import chess
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import require_user
from .play import LEVELS, game_state

router = APIRouter(prefix="/api/play")


class Position(BaseModel):
    fen: str = Field(max_length=120)
    level: int = Field(default=5, ge=1, le=len(LEVELS))  # 1700, the same default as the Play page


class Suggest(BaseModel):
    fen: str = Field(max_length=120)
    n: int = Field(default=2, ge=1, le=3)


@router.post("/suggest")
def suggest(body: Suggest, request: Request) -> dict:
    """The engine's best moves (two by default) for the side to move, with a reason for each."""
    require_user(request)
    board = _board(body.fen)
    if board.is_game_over():
        return {"moves": [], "context": None, "over": True}
    try:
        return {**request.app.state.play.suggest(board, body.n), "over": False}
    except FileNotFoundError as err:
        raise HTTPException(503, "The chess engine is not available on this server.") from err


def _board(fen: str) -> chess.Board:
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, "That position is not valid.")
    if not board.is_valid():
        raise HTTPException(400, "That position is not legal (check the kings and pieces).")
    return board


@router.get("/levels")
def levels(request: Request) -> list[dict]:
    require_user(request)
    return [{k: lv[k] for k in ("id", "label", "elo")} for lv in LEVELS]


@router.post("/reply")
def reply(body: Position, request: Request) -> dict:
    """The computer's move for the side to move in `fen`."""
    require_user(request)
    board = _board(body.fen)
    if board.is_game_over(claim_draw=True):
        raise HTTPException(400, "The game is already over.")
    try:
        move = request.app.state.play.reply(board, body.level)
    except FileNotFoundError as err:
        raise HTTPException(503, "The chess engine is not available on this server.") from err
    san = board.san(move)
    board.push(move)
    return {"move": {"uci": move.uci(), "san": san}, "fen": board.fen(), **game_state(board)}


@router.post("/hint")
def hint(body: Position, request: Request) -> dict:
    require_user(request)
    board = _board(body.fen)
    if board.is_game_over():
        raise HTTPException(400, "The game is already over.")
    try:
        return request.app.state.play.hint(board)
    except FileNotFoundError as err:
        raise HTTPException(503, "The chess engine is not available on this server.") from err

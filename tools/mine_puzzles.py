"""Find puzzles in games with Stockfish and write src/chesscoach/data/academy_mined.json.

    uv run python tools/mine_puzzles.py

A position becomes a puzzle only when the best move is clearly unique (the second-best line is
far worse or does not mate as fast) and the solution line is fully forced for the solver.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chesscoach import academy, tactics as T  # noqa: E402
from chesscoach.engine import DEFAULT_ENGINE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "chesscoach" / "data" / "academy_mined.json"
DEPTH = 16
PER_GAME = {"mates": 1, "attack": 2, "tactics": 3}
MATE_LIMIT = [3]


def games() -> list[tuple[str, list[chess.Board]]]:
    out = []
    for g in academy.model_games():
        board = chess.Board()
        boards = [board.copy()]
        for m in g["moves"]:
            board.push_uci(m["uci"])
            boards.append(board.copy())
        out.append((g["id"], boards))
    path = ROOT / "sample_games" / "simulated_games.pgn"
    if path.exists():
        with open(path, encoding="utf-8") as handle:
            n = 0
            while (game := chess.pgn.read_game(handle)) is not None:
                board = game.board()
                boards = [board.copy()]
                for move in game.mainline_moves():
                    board.push(move)
                    boards.append(board.copy())
                out.append((f"sim{n}", boards))
                n += 1
    return out


def material(board: chess.Board, color: chess.Color) -> int:
    return T.material(board, color) - T.material(board, not color)


def analyse(engine, board):
    return engine.analyse(board, chess.engine.Limit(depth=DEPTH), multipv=2)


def mate_puzzle(board, infos):
    best = infos[0]["score"].pov(board.turn)
    n = best.mate()
    if n is None or n < 1 or n > MATE_LIMIT[0]:
        return None
    if len(infos) > 1:
        other = infos[1]["score"].pov(board.turn).mate()
        if other is not None and 0 < other <= n + 1:
            return None  # another quick mate exists: the solution is not unique
    pv = infos[0]["pv"][: 2 * n - 1]
    if len(pv) != 2 * n - 1:
        return None
    return "mate", n, pv


def tactic_puzzle(board, infos):
    if len(infos) < 2:
        return None
    mover = board.turn
    a = infos[0]["score"].pov(mover).score(mate_score=10000)
    b = infos[1]["score"].pov(mover).score(mate_score=10000)
    if infos[0]["score"].pov(mover).is_mate() or a < 200 or a - b < 200:
        return None
    pv = infos[0]["pv"][:3]
    if len(pv) < 3:
        return None
    first = board.copy()
    start = material(first, mover)
    for move in pv:
        first.push(move)
    if material(first, mover) - start < 2:
        return None
    return "material", 0, pv


def describe(board, pv, kind, n):
    move = pv[0]
    info = T.describe_move(board, move)
    sacrifice = False
    b = board.copy()
    before = material(b, board.turn)
    b.push(move)
    if pv[1:2]:
        b.push(pv[1])
        sacrifice = material(b, board.turn) < before - 1
    if kind == "mate":
        theme = "attack" if sacrifice or n >= 3 else "mates"
        title = f"Mate in {n}"
        idea = "Give up material to break through and mate." if sacrifice else "Every move must be a check or an unstoppable threat."
    else:
        theme = "tactics"
        if info.fork:
            title, idea = "Fork!", "One piece attacks two things at once, so your opponent can only save one."
        elif info.pin:
            title, idea = "Use the pin", "A pinned piece cannot move. Attack it again."
        elif info.discovered:
            title, idea = "Discovered attack", "Move one piece and let another one attack behind it."
        elif info.is_check:
            title, idea = "Check first", "A check forces a reply, and something is left hanging."
        else:
            title, idea = "Win material", "Find the capture or threat that wins something."
    return theme, title, idea


def main() -> None:
    global OUT, DEPTH
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--models-only", action="store_true", help="only the famous attacking games")
    parser.add_argument("--max-mate", type=int, default=3)
    parser.add_argument("--depth", type=int, default=DEPTH)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    OUT, DEPTH = args.out, args.depth
    MATE_LIMIT[0] = args.max_mate
    found, seen = [], set()
    with chess.engine.SimpleEngine.popen_uci(str(DEFAULT_ENGINE)) as engine:
        engine.configure({"Threads": 2, "Hash": 128})
        for gid, boards in games():
            if args.models_only and gid.startswith("sim"):
                continue
            counts = {t: 0 for t in PER_GAME}
            for ply, board in enumerate(boards):
                if board.is_game_over() or ply < 6:
                    continue
                infos = analyse(engine, board)
                result = mate_puzzle(board, infos) or tactic_puzzle(board, infos)
                if not result:
                    continue
                kind, n, pv = result
                theme, title, idea = describe(board, pv, kind, n)
                key = board.epd()
                if counts[theme] >= PER_GAME[theme] or key in seen:
                    continue
                seen.add(key)
                counts[theme] += 1
                san = []
                b = board.copy()
                for move in pv:
                    san.append(b.san(move))
                    b.push(move)
                found.append({
                    "id": f"mined-{gid}-{ply}", "theme": theme, "title": f"{title} ({gid.replace('sim', 'game ') if gid.startswith('sim') else gid})",
                    "idea": idea, "fen": board.fen(), "side": "white" if board.turn else "black",
                    "line": [m.uci() for m in pv], "line_san": san, "hint": "Look at forcing moves first.",
                })
                print(f"{gid} ply {ply}: {theme} {title} {' '.join(san)}", file=sys.stderr)
    OUT.write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(f"wrote {len(found)} puzzles to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

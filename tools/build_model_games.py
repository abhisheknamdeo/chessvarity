"""Build the rated model-games library from the Lichess open database (CC0).

    uv run --with zstandard python tools/build_model_games.py select      # download + pick candidates
    uv run python tools/build_model_games.py annotate --workers 8         # commentary with Stockfish
    uv run --with zstandard python tools/build_model_games.py all

Only games that are competitive, end in checkmate and contain real attacking play are kept.
Player names are never stored: a model game is just moves, ratings and commentary.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import urllib.request
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chesscoach import tactics as T  # noqa: E402
from chesscoach.commentary import annotate, game_notes  # noqa: E402
from chesscoach.engine import DEFAULT_ENGINE, Engine  # noqa: E402
from chesscoach.openings import book  # noqa: E402

SOURCE_URL = "https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst"
# Strong players are rare in 2013, so the two top bands come from the start of a later month.
STRONG_URL = "https://database.lichess.org/standard/lichess_db_standard_rated_2016-01.pgn.zst"
STRONG_CACHE = Path(tempfile.gettempdir()) / "lichess_2016-01_head.pgn.zst"
STRONG_BYTES = 160_000_000
CACHE = Path(tempfile.gettempdir()) / "lichess_2013-01.pgn.zst"
SELECTED = Path(tempfile.gettempdir()) / "model_games_selected.json"
OUT = ROOT / "src" / "chesscoach" / "data" / "model_games_lichess.json"

BANDS = [  # (key, label, low, high)
    ("under-1200", "Beginner (under 1200)", 0, 1200),
    ("1200-1499", "Improver (1200-1499)", 1200, 1500),
    ("1500-1799", "Club player (1500-1799)", 1500, 1800),
    ("1800-1999", "Strong club (1800-1999)", 1800, 2000),
    ("2000-2299", "Expert (2000-2299)", 2000, 2300),
    ("2300-plus", "Master (2300 and up)", 2300, 9999),
]
PER_BAND = 55
MAX_PER_OPENING = 5


def band_of(avg: float) -> str | None:
    return next((k for k, _, lo, hi in BANDS if lo <= avg < hi), None)


def download() -> None:
    if CACHE.exists() and CACHE.stat().st_size > 10_000_000:
        return
    print("downloading", SOURCE_URL, file=sys.stderr)
    urllib.request.urlretrieve(SOURCE_URL, CACHE)


def attack_score(game: chess.pgn.Game, winner: chess.Color) -> tuple[float, dict] | None:
    board = game.board()
    checks = sacrifice = 0
    diff_at_12 = None
    min_diff = 0
    plies = 0
    for move in game.mainline_moves():
        plies += 1
        mover = board.turn
        if mover == winner and board.gives_check(move):
            checks += 1
        board.push(move)
        diff = T.material(board, winner) - T.material(board, not winner)
        if plies == 12:
            diff_at_12 = diff
        if plies > 12:
            min_diff = min(min_diff, diff)
    if not board.is_checkmate() or board.turn == winner:
        return None
    if diff_at_12 is None or abs(diff_at_12) > 3:
        return None  # decided by an early blunder, not a fight
    if checks < 3:
        return None
    if min_diff <= -3:
        sacrifice = 1
    return min(checks, 8) + 4 * sacrifice, {"checks": checks, "sacrifice": bool(sacrifice), "plies": plies}


def select() -> list[dict]:
    import zstandard

    download()
    pools: dict[str, list[dict]] = {k: [] for k, *_ in BANDS}
    seen = 0
    with open(CACHE, "rb") as fh:
        reader = zstandard.ZstdDecompressor().stream_reader(fh)
        text = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
        while (game := chess.pgn.read_game(text)) is not None:
            seen += 1
            h = game.headers
            if h.get("Termination") != "Normal" or h.get("Result") not in ("1-0", "0-1"):
                continue
            try:
                white, black = int(h["WhiteElo"]), int(h["BlackElo"])
            except (KeyError, ValueError):
                continue
            base = h.get("TimeControl", "0+0").split("+")[0]
            if not base.isdigit() or int(base) < 180 or abs(white - black) > 250 or min(white, black) < 700:
                continue
            plies = sum(1 for _ in game.mainline_moves())
            if not 24 <= plies <= 70:
                continue
            winner = chess.WHITE if h["Result"] == "1-0" else chess.BLACK
            scored = attack_score(game, winner)
            if scored is None:
                continue
            score, info = scored
            avg = (white + black) / 2
            band = band_of(avg)
            if band is None:
                continue
            pools[band].append({
                "id": "lc-" + h.get("Site", "").rsplit("/", 1)[-1], "band": band, "avg": round(avg),
                "white_rating": white, "black_rating": black, "result": h["Result"],
                "month": h.get("UTCDate", "2013.01.01")[:7], "score": score, "src": "2013", **info,
                "moves": [m.uci() for m in game.mainline_moves()],
            })
            if seen % 20000 == 0:
                print(f"read {seen} games; candidates so far: { {k: len(v) for k, v in pools.items()} }", file=sys.stderr)
    chosen = []
    for key, *_ in BANDS:
        pool = sorted(pools[key], key=lambda g: (-g["score"], g["id"]))
        per_opening: dict[str, int] = {}
        picked = []
        for g in pool:
            board = chess.Board()
            for u in g["moves"][:6]:
                board.push_uci(u)
            eco = board.epd()
            if per_opening.get(eco, 0) >= MAX_PER_OPENING:
                continue
            per_opening[eco] = per_opening.get(eco, 0) + 1
            picked.append(g)
            if len(picked) >= PER_BAND:
                break
        print(f"{key}: {len(pools[key])} candidates -> {len(picked)} chosen", file=sys.stderr)
        chosen += picked
    SELECTED.write_text(json.dumps(chosen), encoding="utf-8")
    print(f"selected {len(chosen)} games from {seen} read", file=sys.stderr)
    return chosen


def iter_blocks(lines):
    """Raw text of each game, without parsing it."""
    block: list[str] = []
    in_moves = False
    for line in lines:
        if line.startswith("[Event ") and in_moves:
            yield "".join(block)
            block, in_moves = [], False
        block.append(line)
        if line.strip() and not line.startswith("["):
            in_moves = True
    if block:
        yield "".join(block)


def strong() -> list[dict]:
    """Add checkmate wins between strong players (2000+) from the start of a later month."""
    import re
    import zstandard

    if not (STRONG_CACHE.exists() and STRONG_CACHE.stat().st_size > 100_000_000):
        print("downloading the start of", STRONG_URL, file=sys.stderr)
        req = urllib.request.Request(STRONG_URL, headers={"Range": f"bytes=0-{STRONG_BYTES - 1}"})
        with urllib.request.urlopen(req) as resp, open(STRONG_CACHE, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    chosen = json.loads(SELECTED.read_text(encoding="utf-8"))
    chosen = [g for g in chosen if g["band"] not in ("2000-2299", "2300-plus") or g.get("src") == "2013"]
    have_2013 = {k: sum(1 for g in chosen if g["band"] == k) for k in ("2000-2299", "2300-plus")}
    pools: dict[str, list[dict]] = {"2000-2299": [], "2300-plus": []}
    elo = re.compile(r'\[(White|Black)Elo "(\d+)"\]')
    base_re = re.compile(r'\[TimeControl "(\d+)\+')
    read = 0
    try:
        with open(STRONG_CACHE, "rb") as fh:
            text = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(fh), encoding="utf-8", errors="replace")
            for block in iter_blocks(text):
                read += 1
                if "#" not in block or '[Termination "Normal"]' not in block:
                    continue
                ratings = {k: int(v) for k, v in elo.findall(block)}
                if len(ratings) != 2 or min(ratings.values()) < 1900 or sum(ratings.values()) / 2 < 2000:
                    continue
                m = base_re.search(block)
                if not m or int(m.group(1)) < 180 or abs(ratings["White"] - ratings["Black"]) > 250:
                    continue
                game = chess.pgn.read_game(io.StringIO(block))
                h = game.headers
                if h.get("Result") not in ("1-0", "0-1"):
                    continue
                plies = sum(1 for _ in game.mainline_moves())
                if not 24 <= plies <= 70:
                    continue
                scored = attack_score(game, chess.WHITE if h["Result"] == "1-0" else chess.BLACK)
                if scored is None:
                    continue
                avg = (ratings["White"] + ratings["Black"]) / 2
                band = band_of(avg)
                if band in pools:
                    pools[band].append({
                        "id": "lc-" + h.get("Site", "").rsplit("/", 1)[-1], "band": band, "avg": round(avg),
                        "white_rating": ratings["White"], "black_rating": ratings["Black"], "result": h["Result"],
                        "month": h.get("UTCDate", "2016.01.01")[:7], "score": scored[0], **scored[1],
                        "moves": [mv.uci() for mv in game.mainline_moves()],
                    })
    except Exception as err:  # the downloaded chunk ends mid-stream; that is expected
        print("stopped reading:", type(err).__name__, file=sys.stderr)
    print(f"scanned {read} game blocks", file=sys.stderr)
    for key, pool in pools.items():
        pool.sort(key=lambda g: (-g["score"], g["id"]))
        per_opening: dict[str, int] = {}
        picked = []
        for g in pool:
            board = chess.Board()
            for u in g["moves"][:6]:
                board.push_uci(u)
            eco = board.epd()
            if per_opening.get(eco, 0) >= MAX_PER_OPENING:
                continue
            per_opening[eco] = per_opening.get(eco, 0) + 1
            picked.append(g)
            if len(picked) >= PER_BAND:
                break
        print(f"{key}: {len(pool)} candidates -> {len(picked)} chosen", file=sys.stderr)
        chosen += picked
    SELECTED.write_text(json.dumps(chosen), encoding="utf-8")
    print(f"selected {len(chosen)} games in total", file=sys.stderr)
    return chosen


def classics() -> list[dict]:
    """The hand-picked famous games, annotated with the same commentary generator."""
    from chesscoach import academy

    out = []
    for g in academy.model_games():
        result = g["result"]
        out.append({"id": f"classic-{g['id']}", "band": "historic", "avg": None, "white_rating": None,
                    "black_rating": None, "result": result, "month": f"{g['year']}.01", "score": 99,
                    "moves": [m["uci"] for m in g["moves"]]})
    return out


_engine: Engine | None = None


def _annotate_one(g: dict) -> dict:
    global _engine
    if _engine is None:
        _engine = Engine(DEFAULT_ENGINE, depth=9, multipv=3, threads=1, hash_mb=16, max_seconds=3.0)
    board = chess.Board()
    boards, moves = [board.copy()], []
    for u in g["moves"]:
        m = chess.Move.from_uci(u)
        moves.append(m)
        board.push(m)
        boards.append(board.copy())
    _engine.new_game()
    evals = [_engine.analyse(b) for b in boards]
    game = chess.pgn.Game()
    node = game
    for m in moves:
        node = node.add_variation(m)
    opening, book_ply = book().detect(game)
    name = opening.name if opening else ""
    commentary = annotate(boards, moves, evals, viewpoint=None, book_ply=book_ply, opening_name=name)
    notes = game_notes(commentary, g["result"], len(moves), name)
    board = chess.Board()
    sans = []
    for m in moves:
        sans.append(board.san(m))
        board.push(m)
    return {
        "id": g["id"], "band": g["band"], "avg": g["avg"], "white_rating": g["white_rating"],
        "black_rating": g["black_rating"], "result": g["result"], "month": g["month"],
        "opening_eco": opening.eco if opening else "", "opening_name": name, "book_plies": book_ply,
        "moves": sans, "score": g["score"], **notes,
        "commentary": [{"ply": c["ply"], "text": c["text"], "tags": c["tags"]} for c in commentary],
    }


PROGRESS = Path(tempfile.gettempdir()) / "model_games_annotated.jsonl"
STALL_SECONDS = 420


def annotate_all(workers: int) -> None:
    """Annotate every selected game. Each finished game is saved at once, so a rerun resumes."""
    chosen = classics() + json.loads(SELECTED.read_text(encoding="utf-8"))
    done: dict[str, dict] = {}
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                done[item["id"]] = item
    todo = [g for g in chosen if g["id"] not in done]
    print(f"{len(done)} already done, {len(todo)} to annotate", file=sys.stderr)
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_annotate_one, g): g["id"] for g in todo}
        pending = set(futures)
        last = time.time()
        with open(PROGRESS, "a", encoding="utf-8") as log:
            while pending and time.time() - last < STALL_SECONDS:
                finished, pending = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
                for fut in finished:
                    try:
                        item = fut.result()
                    except Exception as err:
                        print(f"failed {futures[fut]}: {type(err).__name__}: {err}", file=sys.stderr)
                        continue
                    done[item["id"]] = item
                    log.write(json.dumps(item, separators=(",", ":")) + "\n")
                    log.flush()
                    last = time.time()
                    if len(done) % 10 == 0:
                        print(f"annotated {len(done)}/{len(chosen)}", file=sys.stderr)
        if pending:
            print("giving up on:", sorted(futures[f] for f in pending), file=sys.stderr)
    finally:
        for proc in list(getattr(pool, "_processes", {}).values()):
            proc.terminate()
        pool.shutdown(wait=False, cancel_futures=True)
    ordered = [done[g["id"]] for g in chosen if g["id"] in done]
    OUT.write_text(json.dumps(ordered, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(ordered)} games ({OUT.stat().st_size / 1e6:.1f} MB) to {OUT}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["select", "strong", "annotate", "all"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.stage in ("select", "all"):
        select()
    if args.stage in ("strong", "all"):
        strong()
    if args.stage in ("annotate", "all"):
        annotate_all(args.workers)


if __name__ == "__main__":
    main()

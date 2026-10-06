"""Reading games in, normalising their headers, and describing them for storage."""

from __future__ import annotations

import hashlib
import io
import time

import chess
import chess.pgn

from .analyzer import _result
from .openings import book

UNKNOWN = ("", "?", "????.??.??")
RESULTS = ("1-0", "0-1", "1/2-1/2", "*")


def split_games(text: str, limit: int) -> list[chess.pgn.Game]:
    """Every game with moves in `text`. A bare move list counts as one game."""
    handle = io.StringIO(text)
    games: list[chess.pgn.Game] = []
    while (game := chess.pgn.read_game(handle)) is not None:
        if game.errors:
            played = sum(1 for _ in game.mainline_moves())
            raise ValueError(
                f"Could not read the moves after move {played // 2 + 1} "
                f"({'White' if played % 2 == 0 else 'Black'} to move): {game.errors[0]}"
            )
        if any(True for _ in game.mainline_moves()):
            games.append(game)
        if len(games) > limit:
            raise ValueError(f"That is more than {limit} games at once. Please upload fewer.")
    if not games:
        raise ValueError("No moves were found. Paste a PGN or a list of moves like: 1. e4 e5 2. Nf3")
    return games


def find_side(game: chess.pgn.Game, names: list[str]) -> chess.Color | None:
    """The side whose name matches one of `names` (the player's name, account name, USCF name), else None.

    "Namdeo, Ayaan" matches "Ayaan Namdeo": every word of the name must appear in the header.
    """
    for name in names:
        words = [w for w in name.lower().replace(",", " ").split() if w]
        if not words:
            continue
        hits = [side for side, key in ((chess.WHITE, "White"), (chess.BLACK, "Black"))
                if all(w in game.headers.get(key, "").lower() for w in words)]
        if len(hits) == 1:
            return hits[0]
    return None


def resolve_color(game: chess.pgn.Game, player_name: str | list[str], color: str) -> chess.Color:
    if color in ("white", "black"):
        return chess.WHITE if color == "white" else chess.BLACK
    names = [player_name] if isinstance(player_name, str) else player_name
    side = find_side(game, names)
    if side is not None:
        return side
    raise ValueError(
        f"Could not tell which side {names[0]} played. Choose White or Black for this game."
    )


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def parse_date(text: str) -> tuple[int, int, int | None] | None:
    """(year, month, day-or-None) from a PGN date such as 2026.09.14 or 2026.09.??, else None.

    A date needs at least a year and a month to be useful for sorting into a monthly section.
    """
    parts = (text or "").split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    year, month = int(parts[0]), int(parts[1])
    if not (1900 <= year <= 2200 and 1 <= month <= 12):
        return None
    day = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() and 1 <= int(parts[2]) <= 31 else None
    return year, month, day


def make_date(year: int, month: int, day: int | None = None) -> str:
    return f"{year:04d}.{month:02d}.{day:02d}" if day else f"{year:04d}.{month:02d}.??"


def prepare(
    game: chess.pgn.Game,
    *,
    player_name: str,
    color: chess.Color,
    event: str = "",
    round_: str = "",
    year: int | None = None,
    month: int | None = None,
    prefer_pgn_date: bool = True,
    opponent: str = "",
    result: str = "",
    override: bool = True,
    today: tuple[int, int] | None = None,
    opponent_rating: int | None = None,
    day: int | None = None,
) -> None:
    """Fill in headers the PGN lacks. With `override`, values the user typed win over the PGN.

    Every game ends up with a year and month, so it always lands in a monthly section:
    the game's own date if it has one (and `prefer_pgn_date`), else the chosen year and month,
    else the current month.
    """
    h = game.headers
    mine, theirs = ("White", "Black") if color == chess.WHITE else ("Black", "White")
    if h.get(mine, "?") in UNKNOWN:
        h[mine] = player_name
    if opponent and (override or h.get(theirs, "?") in UNKNOWN):
        h[theirs] = opponent
    if opponent_rating:
        rating_key = f"{theirs}Elo"
        if override or h.get(rating_key, "?") in UNKNOWN or not h.get(rating_key, "").isdigit():
            h[rating_key] = str(opponent_rating)
    for key, value in (("Event", event), ("Round", round_)):
        if value and (override or h.get(key, "?") in UNKNOWN):
            h[key] = value
    if result in RESULTS and (override or h.get("Result", "*") in ("*", "")):
        h["Result"] = result

    own = parse_date(h.get("Date", ""))
    if own and prefer_pgn_date:
        h["Date"] = make_date(*own)
    else:
        now = today or (time.localtime().tm_year, time.localtime().tm_mon)
        h["Date"] = make_date(year or now[0], month or now[1], day if year and month else None)


def describe(game: chess.pgn.Game, color: chess.Color) -> dict:
    """Columns for the games table."""
    h = game.headers
    board = game.end().board()
    plies = sum(1 for _ in game.mainline_moves())
    opening, opening_ply = book().detect(game)
    theirs = "Black" if color == chess.WHITE else "White"
    return {
        "white": h.get("White", "?") if h.get("White", "?") not in UNKNOWN else "White",
        "black": h.get("Black", "?") if h.get("Black", "?") not in UNKNOWN else "Black",
        "white_elo": h.get("WhiteElo", ""),
        "black_elo": h.get("BlackElo", ""),
        "result": _result(h.get("Result", "*"), board),
        "event": "" if h.get("Event", "?") in UNKNOWN else h.get("Event", ""),
        "round": "" if h.get("Round", "?") in UNKNOWN else h.get("Round", ""),
        "date": h.get("Date", "") if parse_date(h.get("Date", "")) else "",
        "opponent": "" if h.get(theirs, "?") in UNKNOWN else h.get(theirs, ""),
        "opening_eco": opening.eco if opening else "",
        "opening_name": opening.name if opening else "",
        "opening_plies": opening_ply,
        "plies": plies,
    }


def fingerprint(game: chess.pgn.Game, color: chess.Color) -> str:
    moves = " ".join(m.uci() for m in game.mainline_moves())
    names = f"{game.headers.get('White', '')}|{game.headers.get('Black', '')}"
    return hashlib.sha1(f"{int(color)}|{names}|{moves}".encode()).hexdigest()


def export(game: chess.pgn.Game) -> str:
    return str(game)


def outcome(result: str, color: str) -> str | None:
    """'win' / 'loss' / 'draw' for the coached side, or None if the game is unfinished."""
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if color == "white" else "loss"
    if result == "0-1":
        return "win" if color == "black" else "loss"
    return None

"""Curated learning content: puzzles, attacking model games and an opening repertoire.

Positions are built by playing real move lists, and the tests replay every line to confirm
each move is legal and each claimed checkmate is one, so a typo cannot ship.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import chess

MINED = Path(__file__).parent / "data" / "academy_mined.json"

THEMES = {
    "mates": {
        "title": "Mating patterns",
        "blurb": "The classic checkmates. Learn to recognize them and you will find them in your own games.",
    },
    "attack": {
        "title": "Attack the king",
        "blurb": "Sacrifices and forcing moves that break open the enemy king. Look for checks first!",
    },
    "traps": {
        "title": "Opening traps",
        "blurb": "Tricks that win material or the game in the first few moves, for you or against you.",
    },
    "tactics": {
        "title": "Winning material",
        "blurb": "Forks, pins and double attacks. Find the forcing move that wins something.",
    },
}


def _line(setup: list[str], solution: list[str]) -> tuple[str, list[str], list[str]]:
    """Play `setup` from the start; return the FEN reached and the solution as UCI and SAN."""
    board = chess.Board()
    for san in setup:
        board.push_san(san)
    fen = board.fen()
    uci = []
    for san in solution:
        uci.append(board.push_san(san).uci())
    return fen, uci, solution


def _from_fen(fen: str, solution: list[str]) -> tuple[str, list[str], list[str]]:
    board = chess.Board(fen)
    uci = [board.push_san(san).uci() for san in solution]
    return fen, uci, solution


OPERA = ("e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 "
         "O-O-O Rd8 Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#").split()
IMMORTAL = ("e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6 d3 Nh5 Nh4 Qg5 Nf5 c6 g4 Nf6 Rg1 cxb5 h4 Qg6 "
            "h5 Qg5 Qf3 Ng8 Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1 e5 Qxa1+ Ke2 Na6 Nxg7+ Kd8 Qf6+ Nxf6 Be7#").split()
EVERGREEN = ("e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O d3 Qb3 Qf6 e5 Qg6 Re1 Nge7 Ba3 b5 Qxb5 Rb8 "
             "Qa4 Bb6 Nbd2 Bb7 Ne4 Qf5 Bxd3 Qh5 Nf6+ gxf6 exf6 Rg8 Rad1 Qxf3 Rxe7+ Nxe7 Qxd7+ Kxd7 Bf5+ Ke8 "
             "Bd7+ Kf8 Bxe7#").split()
LASKER = ("d4 e6 Nf3 f5 Nc3 Nf6 Bg5 Be7 Bxf6 Bxf6 e4 fxe4 Nxe4 b6 Ne5 O-O Bd3 Bb7 Qh5 Qe7 Qxh7+ Kxh7 "
          "Nxf6+ Kh6 Neg4+ Kg5 h4+ Kf4 g3+ Kf3 Be2+ Kg2 Rh2+ Kg1 Kd2#").split()
LEGAL = "e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5 Bxd1 Bxf7+ Ke7 Nd5#".split()


def _puzzle(pid: str, theme: str, title: str, idea: str, built: tuple, hint: str = "") -> dict:
    fen, uci, san = built
    return {
        "id": pid, "theme": theme, "title": title, "idea": idea, "fen": fen, "side": chess.Board(fen).turn and "white" or "black",
        "line": uci, "line_san": san, "hint": hint,
    }


def hand_made() -> list[dict]:
    p = []
    add = lambda *a, **k: p.append(_puzzle(*a, **k))
    add("mate-scholar", "mates", "Scholar's mate", "The f7 pawn is guarded only by the king. Queen and bishop hit it together.",
        _line("e4 e5 Bc4 Nc6 Qh5 Nf6".split(), ["Qxf7#"]), "Which square is only defended by the king?")
    add("mate-fool", "mates", "The fastest mate in chess", "Pawn moves in front of the king can open a diagonal for the queen.",
        _line("f3 e5 g4".split(), ["Qh4#"]), "Look at the long diagonal to the king.")
    add("mate-back-rank", "mates", "Back-rank mate", "A king stuck behind its own pawns can be mated by a rook on the back rank.",
        _from_fen("6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1", ["Re8#"]), "The king has no squares to run to.")
    add("mate-ladder", "mates", "Ladder mate", "Two rooks take turns pushing the king to the edge, one rank at a time.",
        _from_fen("6k1/1R6/8/8/8/8/R7/6K1 w - - 0 1", ["Ra8#"]), "One rook guards the 7th rank.")
    add("mate-arabian", "mates", "Arabian mate", "A rook next to the king, protected by a knight, with the knight covering the escape square.",
        _from_fen("7k/R7/5N2/8/8/8/8/6K1 w - - 0 1", ["Rh7#"]), "The rook needs its knight's protection.")
    add("mate-anastasia", "mates", "Anastasia's mate", "A knight covers the escape squares while a rook checks along the file.",
        _from_fen("8/4N1pk/8/8/8/8/K7/1R6 w - - 0 1", ["Rh1#"]), "The king's own pawn blocks one escape.")
    add("mate-legal", "mates", "Legal's mate: sacrifice the queen!", "Take the pawn and let them take your queen: two minor pieces then deliver checkmate.",
        _line("e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6".split(), "Nxe5 Bxd1 Bxf7+ Ke7 Nd5#".split()), "Their bishop wants your queen. Let it!")
    add("mate-smothered", "mates", "Smothered mate", "A knight checkmates a king that is boxed in by its own pieces.",
        _line("e4 e5 Nf3 Nc6 Bc4 Nd4 Nxe5 Qg5 Nxf7 Qxg2 Rf1".split(), "Qxe4+ Be2 Nf3#".split()), "Check with the queen first.")
    add("mate-opera", "mates", "The Opera Game finish", "Sacrifice the queen to drag a defender away, then mate with the rook.",
        _line(OPERA[:30], OPERA[30:]), "Their knight is the only defender of d8.")

    add("attack-immortal", "attack", "Immortal Game: rooks and queen are gone, bishops and a knight mate", "Give away almost everything to mate the king with the pieces you have left.",
        _line(IMMORTAL[:40], IMMORTAL[40:]), "Check with the knight, then with the queen.")
    add("attack-evergreen", "attack", "Evergreen Game: a rook, a queen, then a bishop", "Every sacrifice pulls a defender away from the king. Keep checking.",
        _line(EVERGREEN[:38], EVERGREEN[38:]), "Each check leaves the king only one square.")
    add("attack-lasker", "attack", "Lasker's queen sacrifice", "Capture h7 with the queen. If the king takes, a knight fork and a king hunt follow.",
        _line(LASKER[:20], LASKER[20:]), "The h7 pawn is guarded only by the king.")

    add("trap-elephant", "traps", "The Elephant Trap", "If White grabs the d5 pawn with the knight, Black wins a piece with a pin on the d-file.",
        _line("d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5 Nxd5".split(), "Nxd5 Bxd8 Bb4+ Qd2 Bxd2+ Kxd2 Kxd8".split()),
        "Their queen is on the same file as your knight's target.")
    add("trap-noah", "traps", "Noah's Ark Trap", "A bishop tucked into b3 has no way out once the c-pawn advances, so it is lost.",
        _line("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 d6 d4 b5 Bb3 Nxd4 Nxd4 exd4 Qxd4".split(), "c5 Qd5 Be6 Qc6+ Bd7 Qd5 c4".split()),
        "Attack their queen with a pawn, then trap the bishop.")
    add("trap-blackburne", "traps", "Blackburne Shilling Gambit", "Black offers a pawn. If White grabs it greedily the queen and knight deliver a smothered mate.",
        _line("e4 e5 Nf3 Nc6 Bc4 Nd4 Nxe5 Qg5 Nxf7 Qxg2 Rf1".split(), "Qxe4+ Be2 Nf3#".split()), "Look for checks, then for a knight jump.")
    return p


# -- Model games -----------------------------------------------------------------------------------

MODEL_GAMES = [
    {
        "id": "opera", "title": "The Opera Game", "white": "Paul Morphy", "black": "Duke of Brunswick & Count Isouard",
        "year": 1858, "event": "Paris Opera House", "result": "1-0", "theme": "attack", "moves": OPERA,
        "summary": "Morphy develops every piece with tempo, sacrifices a knight to open lines, then mates with a queen sacrifice.",
        "lessons": ["Develop quickly and fight for the center.", "When the enemy king is in the center, open lines against it.", "A sacrifice that removes the last defender is worth it."],
        "notes": [(10, "white", "Nxb5", "A knight sacrifice to open the b-file and keep the attack going."),
                  (12, "white", "O-O-O", "Bring the rook into the fight. Every piece joins the attack."),
                  (16, "white", "Qb8+", "The queen sacrifice: Black's only defender must take, and then Rd8 is mate.")],
    },
    {
        "id": "immortal", "title": "The Immortal Game", "white": "Adolf Anderssen", "black": "Lionel Kieseritzky",
        "year": 1851, "event": "London", "result": "1-0", "theme": "attack", "moves": IMMORTAL,
        "summary": "Anderssen gives away both rooks and his queen to mate with minor pieces.",
        "lessons": ["Development and attack can matter more than material.", "Keep making forcing threats and your opponent never gets to defend.", "Look for the mating net before you cash in a sacrifice."],
        "notes": [(11, "white", "Rg1", "Anderssen opens the g-file for the rook and starts a wild attack."),
                  (18, "white", "Bd6", "Ignoring the threat to his rooks: the bishop cuts off the king's escape."),
                  (23, "white", "Be7#", "Checkmate with a bishop and a knight, after giving up a queen and two rooks.")],
    },
    {
        "id": "evergreen", "title": "The Evergreen Game", "white": "Adolf Anderssen", "black": "Jean Dufresne",
        "year": 1852, "event": "Berlin", "result": "1-0", "theme": "attack", "moves": EVERGREEN,
        "summary": "A pawn sacrifice in the opening leads to a beautiful finish where each sacrifice deflects another defender.",
        "lessons": ["Gambit a pawn for open lines and development.", "Use sacrifices to pull defenders away.", "A queen sacrifice can be the key move."],
        "notes": [(4, "white", "b4", "The Evans Gambit: a pawn for quick development and a strong center."),
                  (20, "white", "Rxe7+", "The rook sacrifice begins a forced mate sequence."),
                  (24, "white", "Bxe7#", "The final blow, a checkmate with the bishop.")],
    },
    {
        "id": "lasker-thomas", "title": "Lasker's queen sacrifice", "white": "Edward Lasker", "black": "Sir George Thomas",
        "year": 1912, "event": "London", "result": "1-0", "theme": "attack", "moves": LASKER,
        "summary": "A queen sacrifice on h7 followed by a king hunt across the whole board.",
        "lessons": ["Bishop plus queen aimed at h7 is a classic attack.", "After a sacrifice, keep giving checks so the king cannot escape.", "Count how many pieces attack the king versus defend it."],
        "notes": [(11, "white", "Qxh7+", "The queen sacrifice: the king must capture, pulling it into the open."),
                  (12, "white", "Nxf6+", "A knight fork with check, then every move is a check."),
                  (18, "white", "Kd2#", "Only the king was left to deliver the mate, on d2, 20 squares from where it started.")],
    },
    {
        "id": "legal", "title": "Légal's mate", "white": "Saint Brie", "black": "Légal de Kermeur",
        "year": 1750, "event": "Paris", "result": "1-0", "theme": "traps", "moves": LEGAL,
        "summary": "The oldest trap in the book: sacrifice the queen and mate with two minor pieces.",
        "lessons": ["Do not grab material without checking what you leave behind.", "A pinned piece can be a target.", "Minor pieces can mate."],
        "notes": [(5, "white", "Nxe5", "Legal offers the queen, a bishop takes it."),
                  (7, "white", "Nd5#", "Checkmate with a knight, with the bishop on f7.")],
    },
]


def model_games() -> list[dict]:
    """The hand-picked classic games with FENs for every move (used by tests and the detail view)."""
    out = []
    for g in MODEL_GAMES:
        board = chess.Board()
        moves = []
        for san in g["moves"]:
            move = board.parse_san(san)
            board.push(move)
            moves.append({"san": san, "uci": move.uci(), "fen": board.fen()})
        notes = []
        for number, side, san, text in g["notes"]:
            ply = 2 * number - (1 if side == "white" else 0)
            notes.append({"ply": ply, "san": san, "text": text})
        out.append({**{k: v for k, v in g.items() if k not in ("moves", "notes")}, "start_fen": chess.STARTING_FEN,
                    "moves": moves, "notes": notes})
    return out


# -- The rated model-games library ---------------------------------------------------------------

LICHESS_GAMES = Path(__file__).parent / "data" / "model_games_lichess.json"

BANDS = [
    ("historic", "Historic masters"),
    ("under-1200", "Beginner (under 1200)"),
    ("1200-1499", "Improver (1200-1499)"),
    ("1500-1799", "Club player (1500-1799)"),
    ("1800-1999", "Strong club (1800-1999)"),
    ("2000-2299", "Expert (2000-2299)"),
    ("2300-plus", "Master (2300 and up)"),
]
BAND_ORDER = {key: n for n, (key, _) in enumerate(BANDS)}


@lru_cache(maxsize=1)
def _rated() -> dict[str, dict]:
    """Rated games (and commentary for the classics) built by tools/build_model_games.py."""
    if not LICHESS_GAMES.exists():
        return {}
    return {g["id"]: g for g in json.loads(LICHESS_GAMES.read_text(encoding="utf-8"))}


def _title(g: dict) -> str:
    winner = {"1-0": "White", "0-1": "Black"}.get(g["result"], "")
    opening = (g.get("opening_name") or "Attacking game").split(":")[0]
    return f"{opening}: {winner} mates on move {(len(g['moves']) + 1) // 2}" if winner else opening


def model_index() -> list[dict]:
    """One line per model game, cheap to send (no moves or commentary)."""
    out = []
    for g in MODEL_GAMES:
        extra = _rated().get(f"classic-{g['id']}", {})
        out.append({
            "id": g["id"], "title": g["title"], "band": "historic", "rating": None,
            "white": g["white"], "black": g["black"], "year": g["year"], "event": g["event"],
            "result": g["result"], "opening": extra.get("opening_name", ""), "summary": g["summary"],
            "themes": extra.get("themes", [g["theme"]]), "plies": len(g["moves"]),
        })
    for g in _rated().values():
        if g["id"].startswith("classic-"):
            continue
        out.append({
            "id": g["id"], "title": _title(g), "band": g["band"], "rating": g["avg"],
            "white": f"White ({g['white_rating']})", "black": f"Black ({g['black_rating']})",
            "year": int(g["month"][:4]), "event": "Online game", "result": g["result"],
            "opening": g["opening_name"], "summary": g["summary"], "themes": g["themes"], "plies": len(g["moves"]),
        })
    out.sort(key=lambda g: (BAND_ORDER[g["band"]], -(g["rating"] or 9999), g["id"]))
    return out


def model_bands() -> list[dict]:
    counts: dict[str, int] = {}
    for g in model_index():
        counts[g["band"]] = counts.get(g["band"], 0) + 1
    return [{"key": k, "label": label, "count": counts.get(k, 0)} for k, label in BANDS if counts.get(k)]


def model_detail(game_id: str) -> dict | None:
    classic = next((g for g in model_games() if g["id"] == game_id), None)
    if classic:
        extra = _rated().get(f"classic-{game_id}", {})
        return {**classic, "band": "historic", "rating": None, "commentary": extra.get("commentary", []),
                "themes": extra.get("themes", [classic["theme"]]), "opening": extra.get("opening_name", "")}
    g = _rated().get(game_id)
    if g is None:
        return None
    board = chess.Board()
    moves = []
    for san in g["moves"]:
        move = board.parse_san(san)
        board.push(move)
        moves.append({"san": san, "uci": move.uci(), "fen": board.fen()})
    return {
        "id": g["id"], "title": _title(g), "band": g["band"], "rating": g["avg"],
        "white": f"White ({g['white_rating']})", "black": f"Black ({g['black_rating']})",
        "year": int(g["month"][:4]), "event": "Online game", "result": g["result"], "theme": "attack",
        "summary": g["summary"], "lessons": g["lessons"], "themes": g["themes"], "opening": g["opening_name"],
        "start_fen": chess.STARTING_FEN, "moves": moves, "commentary": g["commentary"], "notes": [],
    }


# -- Repertoire ----------------------------------------------------------------------------------

REPERTOIRE = [
    {"id": "italian", "side": "white", "name": "Italian Game", "style": "attacking",
     "moves": "e4 e5 Nf3 Nc6 Bc4".split(),
     "idea": "Aim the bishop at f7 and build a big center with c3 and d4. Simple plans and lots of tactics.",
     "plans": ["Castle early, then play c3 and d4.", "Aim pieces at f7, the weakest square.", "Watch for the ...d5 break and keep pieces active."],
     "traps": [{"name": "Légal's trap", "moves": "e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5".split(), "note": "If Black's bishop takes the queen, Bxf7+ and Nd5 is mate."}]},
    {"id": "evans", "side": "white", "name": "Evans Gambit", "style": "attacking",
     "moves": "e4 e5 Nf3 Nc6 Bc4 Bc5 b4".split(),
     "idea": "Sacrifice a pawn for a big center and open lines toward the king. Anderssen's Evergreen Game came from here.",
     "plans": ["After ...Bxb4, play c3 and d4.", "Use the open lines for your bishops and queen.", "Attack quickly before Black consolidates."],
     "traps": []},
    {"id": "two-knights", "side": "white", "name": "Fried Liver Attack", "style": "attacking",
     "moves": "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5 Nxf7".split(),
     "idea": "Against the Two Knights Defense, a knight sacrifice on f7 drags the king into the open.",
     "plans": ["Play Ng5 and hit f7 twice.", "After ...Kxf7, Qf3+ and Nc3 with a strong attack.", "Know the safer move 6.Nc3 too."],
     "traps": []},
    {"id": "scotch", "side": "white", "name": "Scotch Game", "style": "attacking",
     "moves": "e4 e5 Nf3 Nc6 d4 exd4 Nxd4".split(),
     "idea": "Open the center right away. Your pieces get active squares and you avoid a long manoeuvring game.",
     "plans": ["Trade in the center and develop with Nc3 and Be2 or Bc4.", "Look for ideas with Nd5 and Nf5.", "Keep an eye on the e-file."],
     "traps": []},
    {"id": "vienna", "side": "white", "name": "Vienna Game", "style": "attacking",
     "moves": "e4 e5 Nc3 Nf6 f4".split(),
     "idea": "Prepare f4, an early attack on the center, with a knight on c3 keeping things safe.",
     "plans": ["Play f4 and open the f-file.", "Develop the bishop to c4.", "Castle and attack on the kingside."],
     "traps": []},
    {"id": "london", "side": "white", "name": "London System", "style": "solid",
     "moves": "d4 d5 Bf4".split(),
     "idea": "A solid set-up you can play against nearly anything. Good when you want a safe start.",
     "plans": ["Play Nf3, e3, Bd3, c3, Nbd2.", "Castle, then think about e4 or a kingside attack.", "Watch out for ...c5 hitting d4."],
     "traps": []},
    {"id": "two-knights-def", "side": "black", "name": "Two Knights Defense", "style": "attacking",
     "moves": "e4 e5 Nf3 Nc6 Bc4 Nf6".split(),
     "idea": "Counter-attack right away. Black has active pieces and real chances to strike first.",
     "plans": ["After 4.Ng5 play ...d5 and 5...Na5.", "After 4.d3 play ...Be7 and ...d5.", "Keep the king safe and hit back in the center."],
     "traps": []},
    {"id": "sicilian-dragon", "side": "black", "name": "Sicilian Dragon", "style": "attacking",
     "moves": "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6".split(),
     "idea": "The bishop on g7 looks down the long diagonal. Black gets a sharp counter-attack, often against a castled king.",
     "plans": ["Castle short, then play ...Rc8 and ...a5.", "Use the open c-file for the rooks.", "Watch out for the Yugoslav Attack with Bc4, Qd2, O-O-O and h4."],
     "traps": []},
    {"id": "qgd", "side": "black", "name": "Queen's Gambit Declined", "style": "solid",
     "moves": "d4 d5 c4 e6 Nc3 Nf6".split(),
     "idea": "A very solid way to meet 1.d4. It has been used by top players for over a hundred years.",
     "plans": ["Develop with ...Be7, ...O-O, ...c6 or ...c5.", "Free your game with ...dxc4 or ...c5.", "Avoid the Elephant Trap yourself when you are White!"],
     "traps": [{"name": "Elephant Trap", "moves": "d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5 Nxd5".split(), "note": "Black wins a piece with ...Nxd5 and ...Bb4+."}]},
    {"id": "kings-indian", "side": "black", "name": "King's Indian Defense", "style": "attacking",
     "moves": "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O".split(),
     "idea": "Let White build a big center, then attack it and go after the white king with ...f5.",
     "plans": ["Play ...e5 and ...Nc6, or ...c5.", "Push ...f5 for a kingside attack.", "Keep the bishop on g7 alive."],
     "traps": []},
]


def repertoire() -> list[dict]:
    out = []
    for r in REPERTOIRE:
        board = chess.Board()
        for san in r["moves"]:
            board.push_san(san)
        out.append({**r, "fen": board.fen()})
    return out


# -- Puzzles -------------------------------------------------------------------------------------


def _positions(puzzle: dict) -> list[str]:
    """The position before each move of the solution line, plus the final one (as EPDs)."""
    board = chess.Board(puzzle["fen"])
    out = [board.epd()]
    for uci in puzzle["line"]:
        board.push_uci(uci)
        out.append(board.epd())
    return out


def _fens(puzzle: dict) -> list[str]:
    """The FEN after each move of the solution line (so a page can show progress without chess logic)."""
    board = chess.Board(puzzle["fen"])
    out = []
    for uci in puzzle["line"]:
        board.push_uci(uci)
        out.append(board.fen())
    return out


@lru_cache(maxsize=1)
def _all_puzzles() -> tuple[dict, ...]:
    puzzles = hand_made()
    known = {epd for p in puzzles for epd in _positions(p)}
    for path in sorted(MINED.parent.glob("academy_mined*.json")):
        for mined in json.loads(path.read_text(encoding="utf-8")):
            # Skip positions the hand-made puzzles already cover, or that appear twice.
            if mined["fen"] and chess.Board(mined["fen"]).epd() not in known:
                known.update(_positions(mined))
                puzzles.append(mined)
    return tuple({**p, "fens": _fens(p)} for p in puzzles)


def puzzles(theme: str | None = None) -> list[dict]:
    return [p for p in _all_puzzles() if not theme or p["theme"] == theme]


def daily_puzzle(today: str) -> dict:
    """The puzzle of the day: the same for everyone on a given date (YYYY-MM-DD), a new one tomorrow."""
    items = [p for p in _all_puzzles() if len(p["line"]) <= 5]
    digest = sum(ord(c) * (n + 1) for n, c in enumerate(today))
    return items[digest % len(items)]


def puzzle_by_id(pid: str) -> dict | None:
    return next((p for p in _all_puzzles() if p["id"] == pid), None)

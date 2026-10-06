"""Command line: analyze PGN files and print the coaching report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import chess.pgn

from .analyzer import analyze_game, pick_colors
from .engine import Engine
from .explain import SKILL_LABEL


def read_games(path: Path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        while (game := chess.pgn.read_game(handle)) is not None:
            yield game


def print_report(result: dict, out=sys.stdout) -> None:
    g = result["game"]
    p = lambda *a: print(*a, file=out)
    you = g[g["player_color"]]
    p("=" * 72)
    p(f"{g['white']} vs {g['black']}   {g['result']}   (coaching {you}, {g['player_color']})")
    c = result["counts"]
    p(f"Accuracy {result['accuracy']}%   blunders {c['blunders']}, mistakes {c['mistakes']}, "
      f"inaccuracies {c['inaccuracies']}")
    p("=" * 72)
    p(result["summary"]["headline"])
    for prob in result["summary"]["problems"]:
        p(f"  - {prob['text']}")
    for m in result["moments"]:
        marker = "." if m["side"] == "white" else "..."
        p()
        p(f"[Move {m['move_number']}{marker}] {m['headline']}")
        for line in m["story"]:
            p(f"    {line}")
        if m["candidates"] and m["category"] != "defensive_spiral":
            shown = ", ".join(c["san"] for c in m["candidates"] if c["good"])
            if shown:
                p(f"    Candidates worth a look: {shown}")
        if m["think_message"]:
            p(f"    THINK: {m['think_message']}")
        p(f"    Ask yourself: {m['question']}")
        p(f"    Lesson: {m['lesson']}")
    p()
    p("Skills this game:")
    for key, label in SKILL_LABEL.items():
        s = result["skills"][key]
        score = "n/a" if s["score"] is None else f"{s['score']}%"
        p(f"  {label:<26} {score:>5}  ({s['handled']}/{s['opportunities']})")
    p()
    p(f"Today's lesson: {result['summary']['todays_lesson']}")
    for t in result["summary"]["training"]:
        p(f"  Practise: {t['label']} — {t['positions']} position(s) from this game")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="chesscoach", description=__doc__)
    parser.add_argument("pgn", type=Path, help="PGN file (may contain several games)")
    parser.add_argument("--player", help="player's name as written in the PGN headers")
    parser.add_argument("--color", choices=["white", "black", "both"], help="side to coach")
    parser.add_argument("--depth", type=int, default=12, help="Stockfish depth (default 12)")
    parser.add_argument("--engine", type=Path, help="path to a Stockfish binary")
    parser.add_argument("--json", type=Path, help="also write the full analysis to this file")
    args = parser.parse_args(argv)

    results = []
    with Engine(args.engine, depth=args.depth) as engine:
        for n, game in enumerate(read_games(args.pgn), 1):
            try:
                colors = pick_colors(game, args.player, args.color)
            except ValueError as err:
                print(f"Game {n}: {err}", file=sys.stderr)
                continue
            for color in colors:
                print(f"Analysing game {n}...", file=sys.stderr)
                result = analyze_game(game, engine, color, player_name=args.player if args.color and args.color != "both" else None)
                results.append(result)
                print_report(result)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())

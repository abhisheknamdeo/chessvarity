"""Opening names and a browsable variation tree, from the CC0 lichess `chess-openings` data."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import chess
import chess.pgn

DATA =Path(__file__).parent / "data" / "openings.tsv"
MAX_DETECT_PLY = 40


@dataclass
class Opening:
    eco: str
    name: str
    sans: list[str]

    @property
    def family(self) -> str:
        return self.name.split(":")[0].strip()

    @property
    def ply(self) -> int:
        return len(self.sans)


@dataclass
class _Node:
    children: dict[str, "_Node"] = field(default_factory=dict)
    opening: Opening | None = None
    descendants: int = 0


def _sans(pgn: str) -> list[str]:
    tokens = re.sub(r"\d+\.(\.\.)?", " ", pgn).split()
    return [t for t in tokens if t not in ("1-0", "0-1", "1/2-1/2", "*")]


class OpeningBook:
    def __init__(self, path: Path = DATA):
        self.openings: list[Opening] = []
        self.by_epd: dict[str, Opening] = {}
        self.root = _Node()
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                self._add(Opening(row["eco"], row["name"], _sans(row["pgn"])))

    def _add(self, opening: Opening) -> None:
        board = chess.Board()
        node = self.root
        for san in opening.sans:
            try:
                board.push_san(san)
            except ValueError:
                return  # malformed line in the source data: skip it
            node = node.children.setdefault(san, _Node())
        node.opening = opening
        self.openings.append(opening)
        epd = board.epd()
        # The same position can be reached by several lines; keep the more specific name.
        known = self.by_epd.get(epd)
        if known is None or len(opening.name) > len(known.name):
            self.by_epd[epd] = opening

    # -- detection ---------------------------------------------------------

    def detect(self, game: chess.pgn.Game) -> tuple[Opening | None, int]:
        """The deepest named opening reached, and the ply where the game left the book."""
        board = game.board()
        found, last_hit = None, 0
        for ply, move in enumerate(game.mainline_moves(), 1):
            if ply > MAX_DETECT_PLY:
                break
            board.push(move)
            hit = self.by_epd.get(board.epd())
            if hit:
                found, last_hit = hit, ply
        return found, last_hit

    # -- browsing ----------------------------------------------------------

    def _count(self, node: _Node) -> int:
        if not node.descendants:
            node.descendants = (1 if node.opening else 0) + sum(self._count(c) for c in node.children.values())
        return node.descendants

    def browse(self, sans: list[str]) -> dict | None:
        board = chess.Board()
        node = self.root
        path = []
        for ply, san in enumerate(sans, 1):
            child = node.children.get(san)
            if child is None:
                return None
            board.push_san(san)
            node = child
            if node.opening:
                path.append({"eco": node.opening.eco, "name": node.opening.name, "ply": ply})
        options = []
        for san, child in node.children.items():
            b = board.copy()
            move = b.push_san(san)
            options.append(
                {
                    "san": san,
                    "uci": move.uci(),
                    "fen": b.fen(),
                    "opening": {"eco": child.opening.eco, "name": child.opening.name} if child.opening else None,
                    "variations": self._count(child),
                }
            )
        options.sort(key=lambda o: o["variations"], reverse=True)
        return {
            "sans": sans,
            "fen": board.fen(),
            "opening": {"eco": node.opening.eco, "name": node.opening.name} if node.opening else None,
            "path": path,
            "next": options,
        }

    def families(self) -> list[dict]:
        groups: dict[str, list[Opening]] = {}
        for op in self.openings:
            groups.setdefault(op.family, []).append(op)
        out = []
        for name, lines in groups.items():
            shortest = min(lines, key=lambda o: o.ply)
            out.append(
                {
                    "name": name,
                    "eco": shortest.eco,
                    "lines": len(lines),
                    "sans": shortest.sans,
                }
            )
        out.sort(key=lambda f: (-f["lines"], f["name"]))
        return out

    def search(self, query: str, limit: int = 40) -> list[dict]:
        q = query.strip().lower()
        if len(q) < 2:
            return []
        hits = [o for o in self.openings if q in o.name.lower() or q == o.eco.lower()]
        hits.sort(key=lambda o: (o.ply, o.name))
        return [{"eco": o.eco, "name": o.name, "sans": o.sans} for o in hits[:limit]]


@lru_cache(maxsize=1)
def book() -> OpeningBook:
    return OpeningBook()

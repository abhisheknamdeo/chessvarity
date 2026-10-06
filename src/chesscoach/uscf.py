"""Read-only access to a member's public records on the USCF ratings service.

USCF records who played whom, with which color, and how each game ended. It does not record the moves
(those come from the player's scoresheet), so an import gives the tournament skeleton and the student
adds the moves to each game afterwards.

Requests happen only when the student presses a button, are spaced out, and identify this app.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .db import Database

BASE = "https://ratings-api.uschess.org"
USER_AGENT = "DukesKing/0.4 (personal chess study app; reads one member's public records on request)"
PAGE_SIZE = 100
MAX_PAGES = 10          # at most 1,000 games or sections per import
GAP_SECONDS = 1.2       # pause between requests
RESULTS = {"win": "win", "loss": "loss", "draw": "draw"}


class UscfError(Exception):
    """Something the student can act on, in plain words."""


def valid_id(text: str) -> str | None:
    digits = re.sub(r"\s+", "", text or "")
    return digits if re.fullmatch(r"\d{8}", digits) else None


def _http_get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")[:300]
    except (urllib.error.URLError, TimeoutError) as err:
        raise UscfError("Could not reach the USCF ratings service. Check your internet connection and try again.") from err


class UscfClient:
    def __init__(self, fetch: Callable[[str], tuple[int, str]] | None = None, sleep: Callable[[float], None] = time.sleep,
                 gap: float = GAP_SECONDS):
        self._fetch = fetch or _http_get
        self._sleep = sleep
        self._gap = gap
        self._last = 0.0

    def _get(self, path: str, **params) -> dict:
        wait = self._gap - (time.monotonic() - self._last)
        if wait > 0 and self._last:
            self._sleep(wait)
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        status, body = self._fetch(f"{BASE}{path}{'?' + query if query else ''}")
        self._last = time.monotonic()
        if status == 404:
            raise UscfError("USCF has no member with that ID. Check the number and try again.")
        if status == 429 or status >= 500:
            raise UscfError("The USCF ratings service is busy right now. Please try again in a few minutes.")
        if status != 200:
            raise UscfError(f"USCF answered with an unexpected error ({status}).")
        try:
            return json.loads(body)
        except json.JSONDecodeError as err:
            raise UscfError("USCF sent an answer this app could not read.") from err

    def _pages(self, path: str) -> list[dict]:
        items: list[dict] = []
        for page in range(MAX_PAGES):
            data = self._get(path, Offset=page * PAGE_SIZE, Size=PAGE_SIZE)
            items += data.get("items", [])
            if not data.get("hasNextPage"):
                break
        return items

    def member(self, uscf_id: str) -> dict:
        data = self._get(f"/api/v1/members/{uscf_id}")
        names = {"R": "regular", "Q": "quick", "B": "blitz"}
        ratings = {names[r["ratingSystem"]]: r["rating"] for r in data.get("ratings", []) if r.get("ratingSystem") in names and r.get("rating")}
        return {
            "id": str(data.get("id", uscf_id)),
            "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip().title(),
            "status": data.get("status", ""),
            "expires": data.get("expirationDate", ""),
            "ratings": ratings,
        }

    def sections(self, uscf_id: str) -> list[dict]:
        return self._pages(f"/api/v1/members/{uscf_id}/sections")

    def games(self, uscf_id: str) -> list[dict]:
        return self._pages(f"/api/v1/members/{uscf_id}/games")


# USCF rating systems: regular, quick, blitz, then the online ones.
SYSTEM_ORDER = ["R", "Q", "B", "OR", "OQ", "OB"]


def _pretty(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def apply_member(db: Database, player: dict, member: dict) -> None:
    """Remember the member's USCF name and ratings. Their USCF rating becomes the player's rating unless they
    chose another rating system on their profile (regular rating first, then quick)."""
    rating = member["ratings"].get("regular") or member["ratings"].get("quick")
    if rating and (player.get("rating_system") in ("USCF", "", None) or player.get("rating") is None):
        db.run("UPDATE players SET uscf_name = ?, uscf_ratings = ?, rating = ?, rating_system = 'USCF' WHERE id = ?",
               (member["name"], json.dumps(member["ratings"]), rating, player["id"]))
    else:
        db.run("UPDATE players SET uscf_name = ?, uscf_ratings = ? WHERE id = ?",
               (member["name"], json.dumps(member["ratings"]), player["id"]))


def ensure_member(db: Database, player: dict, client_factory) -> dict:
    """For a saved ID whose name and rating were never fetched (or whose rating was never used), fill them in.
    Asks USCF at most once per page view and only when something is missing. Returns the fresh player row."""
    if not valid_id(player.get("uscf_id", "")):
        return player
    if player.get("uscf_ratings"):
        if player.get("rating") is not None:
            return player
        apply_member(db, player, {"name": player.get("uscf_name", ""), "ratings": json.loads(player["uscf_ratings"])})
    else:
        try:
            apply_member(db, player, client_factory().member(player["uscf_id"]))
        except UscfError:
            return player
    return db.one("SELECT * FROM players WHERE id = ?", (player["id"],))


def sync(db: Database, user_id: int, player: dict, client: UscfClient) -> dict:
    """Bring this player's USCF tournaments and game results into the database. Safe to repeat."""
    uscf_id = valid_id(player.get("uscf_id", ""))
    if not uscf_id:
        raise UscfError("Save your USCF ID first.")
    member = client.member(uscf_id)
    sections = {(s["event"]["id"], s["sectionNumber"]): s for s in client.sections(uscf_id)}
    games = client.games(uscf_id)

    groups: dict[tuple[str, int], list[dict]] = {}
    for g in games:
        groups.setdefault((g["event"]["id"], g["section"]["number"]), []).append(g)

    now = time.time()
    added_events = added_games = updated_games = 0
    for (event_id, section_no), items in groups.items():
        first = items[0]
        section = sections.get((event_id, section_no), {})
        # A dual-rated event changes both the regular and the quick rating: keep them all, regular first.
        records = [r for r in section.get("ratingRecords") or [] if r.get("preRating") is not None and r.get("postRating") is not None]
        records.sort(key=lambda r: SYSTEM_ORDER.index(r.get("ratingSource")) if r.get("ratingSource") in SYSTEM_ORDER else len(SYSTEM_ORDER))
        record = records[0] if records else {}
        changes = json.dumps([{"system": r.get("ratingSource", ""), "before": r["preRating"], "after": r["postRating"]} for r in records])
        event = first["event"]
        row = db.one("SELECT id FROM events WHERE player_id = ? AND uscf_event_id = ? AND section = ?",
                     (player["id"], event_id, str(section_no)))
        fields = {
            "name": event.get("name", "USCF event"), "start_date": (event.get("startDate") or "").replace("-", "."),
            "end_date": (event.get("endDate") or "").replace("-", "."), "location": event.get("stateCode", "") or "",
            "rating_system": first.get("ratingSystem", ""), "rating_before": record.get("preRating"),
            "rating_after": record.get("postRating"), "ratings": changes,
        }
        section_name = section.get("sectionName") or first["section"].get("name") or ""
        if section_name and section_name.lower() not in fields["name"].lower():
            fields["notes"] = f"Section: {section_name}"
        if row is None:
            event_row = db.run(
                "INSERT INTO events(user_id, player_id, name, start_date, end_date, location, kind, source, uscf_event_id, "
                "section, rating_system, rating_before, rating_after, ratings, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, player["id"], fields["name"], fields["start_date"], fields["end_date"], fields["location"], "past",
                 "uscf", event_id, str(section_no), fields["rating_system"], fields["rating_before"], fields["rating_after"],
                 fields["ratings"], fields.get("notes", ""), now))
            added_events += 1
        else:
            event_row = row["id"]
            db.run("UPDATE events SET rating_system = ?, rating_before = ?, rating_after = ?, ratings = ?, location = ? WHERE id = ?",
                   (fields["rating_system"], fields["rating_before"], fields["rating_after"], fields["ratings"], fields["location"], event_row))

        existing = db.all("SELECT * FROM event_games WHERE event_id = ? AND source = 'uscf' ORDER BY seq", (event_row,))
        seen: dict[tuple, int] = {}
        by_key: dict[tuple, dict] = {}
        for r in existing:
            k = (r["opponent_uscf_id"], r["color"])
            seen[k] = seen.get(k, 0) + 1
            by_key[(*k, seen[k])] = r
        seen = {}
        for seq, g in enumerate(items, 1):
            opp = g.get("opponent", {})
            color = (g.get("player", {}).get("color") or "").lower()
            result = RESULTS.get((g.get("player", {}).get("outcome") or "").lower(), "")
            k = (str(opp.get("id", "")), color)
            seen[k] = seen.get(k, 0) + 1
            name = _pretty(f"{opp.get('firstName', '')} {opp.get('lastName', '')}")
            match = by_key.get((*k, seen[k]))
            if match:
                if match["result"] != result or match["opponent"] != name:
                    db.run("UPDATE event_games SET result = ?, opponent = ?, color = ? WHERE id = ?", (result, name, color, match["id"]))
                    updated_games += 1
            else:
                db.run("INSERT INTO event_games(event_id, user_id, player_id, seq, round, opponent, opponent_uscf_id, color, "
                       "result, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (event_row, user_id, player["id"], seq, str(seq), name, k[0], color, result, "uscf", now))
                added_games += 1

    apply_member(db, player, member)
    db.run("UPDATE players SET uscf_synced_at = ? WHERE id = ?", (now, player["id"]))
    return {"member": member, "events": len(groups), "events_added": added_events, "games_added": added_games,
            "games_updated": updated_games, "games_seen": len(games)}

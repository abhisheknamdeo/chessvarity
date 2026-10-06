"""Copy a Chess Varsity SQLite database into an empty PostgreSQL database.

    uv run --extra postgres python tools/sqlite_to_postgres.py data/chesscoach.sqlite3 "$DATABASE_URL"

The PostgreSQL tables are created first (the same way the app creates them). It refuses to run if the
target already has accounts, so it cannot mix two databases together. Ids are kept, so links between
rows survive, and the id counters are moved past the copied rows.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chesscoach.db import _ID_TABLES, Database, PostgresDatabase  # noqa: E402

# Parents before children, so every foreign key points at a row that is already there.
TABLES = ["users", "sessions", "email_tokens", "feedback", "players", "folders", "games", "puzzle_progress", "events",
          "event_games", "goals", "training", "model_progress", "goal_steps"]


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    source_path, url = Path(sys.argv[1]), sys.argv[2]
    if not source_path.exists():
        sys.exit(f"No SQLite database at {source_path}")
    Database(source_path)  # brings an older file up to the current columns
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    target = PostgresDatabase(url)
    try:
        if target.one("SELECT COUNT(*) n FROM users")["n"]:
            sys.exit("The PostgreSQL database already has accounts; refusing to copy into it.")
        with target.tx() as conn:
            for table in TABLES:
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                wanted = {r["column_name"] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s "
                    "AND table_schema = current_schema()", (table,))}
                columns = [c for c in (rows[0].keys() if rows else []) if c in wanted]
                if rows:
                    marks = ", ".join(["%s"] * len(columns))
                    with conn.cursor() as cur:
                        cur.executemany(f"INSERT INTO {table}({', '.join(columns)}) VALUES ({marks})",
                                        [tuple(row[c] for c in columns) for row in rows])
                if table in _ID_TABLES:
                    conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                                 f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)")
                print(f"{table}: {len(rows)} rows")
    finally:
        target.close()
        source.close()
    print("Done.")


if __name__ == "__main__":
    main()

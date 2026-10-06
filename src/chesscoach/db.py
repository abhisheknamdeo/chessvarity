"""Storage: SQLite by default, PostgreSQL when DATABASE_URL is set. Every query is parameterised.

The app writes SQLite-flavoured SQL; PostgresDatabase translates the few differences as each statement runs.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    email_verified_at REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rating INTEGER,
    rating_system TEXT NOT NULL DEFAULT 'USCF',
    birth_year INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    color TEXT NOT NULL,
    pgn TEXT NOT NULL,
    white TEXT NOT NULL,
    black TEXT NOT NULL,
    white_elo TEXT NOT NULL DEFAULT '',
    black_elo TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '*',
    event TEXT NOT NULL DEFAULT '',
    round TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT '',
    opponent TEXT NOT NULL DEFAULT '',
    opening_eco TEXT NOT NULL DEFAULT '',
    opening_name TEXT NOT NULL DEFAULT '',
    opening_plies INTEGER NOT NULL DEFAULT 0,
    plies INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    accuracy REAL,
    analysis TEXT,
    fingerprint TEXT NOT NULL DEFAULT '',
    folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    created_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS games_unique ON games(player_id, fingerprint);
CREATE INDEX IF NOT EXISTS games_by_player ON games(player_id, event);
CREATE INDEX IF NOT EXISTS games_by_user ON games(user_id);
CREATE TABLE IF NOT EXISTS puzzle_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    puzzle_id TEXT NOT NULL,
    solved_at REAL NOT NULL,
    PRIMARY KEY (player_id, puzzle_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'past',
    source TEXT NOT NULL DEFAULT 'manual',
    uscf_event_id TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT '',
    rating_system TEXT NOT NULL DEFAULT '',
    rating_before INTEGER,
    rating_after INTEGER,
    time_control TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_player ON events(player_id, start_date);
CREATE TABLE IF NOT EXISTS event_games (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL DEFAULT 0,
    round TEXT NOT NULL DEFAULT '',
    opponent TEXT NOT NULL DEFAULT '',
    opponent_uscf_id TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    game_id INTEGER REFERENCES games(id) ON DELETE SET NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS event_games_by_event ON event_games(event_id, seq);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    horizon TEXT NOT NULL DEFAULT 'short',
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    metric TEXT NOT NULL DEFAULT 'manual',
    baseline REAL,
    target REAL,
    due_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at REAL NOT NULL,
    done_at REAL
);
CREATE TABLE IF NOT EXISTS training (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'class',
    start_date TEXT NOT NULL,
    start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    coach TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    recurrence TEXT NOT NULL DEFAULT 'none',
    weekdays TEXT NOT NULL DEFAULT '',
    until TEXT NOT NULL DEFAULT '',
    skips TEXT NOT NULL DEFAULT '[]',
    done TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS training_by_player ON training(player_id, start_date);
CREATE TABLE IF NOT EXISTS model_progress (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    game_id TEXT NOT NULL,
    seen TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    PRIMARY KEY (player_id, game_id)
);
-- One-time links sent by email ('verify' or 'reset'). Only a hash of the token is stored.
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_at REAL
);
CREATE INDEX IF NOT EXISTS email_tokens_by_user ON email_tokens(user_id, purpose);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'idea',
    message TEXT NOT NULL,
    page TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
-- Sign-ins through Google or Apple: which outside account belongs to which user.
CREATE TABLE IF NOT EXISTS user_identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (provider, subject)
);
CREATE INDEX IF NOT EXISTS user_identities_by_user ON user_identities(user_id);
-- A sign-in with Google or Apple in progress (ten minutes at most). Only a hash of the state is stored.
CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    nonce TEXT NOT NULL,
    verifier TEXT NOT NULL DEFAULT '',
    link_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
-- Photos of a paper scoresheet, kept with a tournament round or with a game. The image is in storage (disk or S3).
CREATE TABLE IF NOT EXISTS scoresheets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    round_id INTEGER REFERENCES event_games(id) ON DELETE CASCADE,
    game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
    storage_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    bytes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS scoresheets_by_round ON scoresheets(round_id);
-- Admins added from the dashboard (the ones in CHESSCOACH_ADMIN_EMAILS are permanent and not listed here).
CREATE TABLE IF NOT EXISTS admins (
    email TEXT PRIMARY KEY,
    added_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at REAL NOT NULL
);
-- The community: games people chose to make public, with an optional question, and the conversation about them.
CREATE TABLE IF NOT EXISTS shares (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,
    question TEXT NOT NULL DEFAULT '',
    show_opponent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'public',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS shares_by_time ON shares(status, updated_at);
CREATE TABLE IF NOT EXISTS share_comments (
    id INTEGER PRIMARY KEY,
    share_id INTEGER NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ply INTEGER,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'visible',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS share_comments_by_share ON share_comments(share_id, id);
CREATE TABLE IF NOT EXISTS share_likes (
    share_id INTEGER NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (share_id, user_id)
);
-- "Helpful" marks on comments (they earn the commenter community points).
CREATE TABLE IF NOT EXISTS comment_likes (
    comment_id INTEGER NOT NULL REFERENCES share_comments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (comment_id, user_id)
);
-- Scoresheet photos saved before the moves are entered ("enter the moves later"). The photos point here
-- (scoresheets.notation_id) until the game is added; then they move to the game and this row goes.
CREATE TABLE IF NOT EXISTS notations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    played_on TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
-- Private share links: anyone with the token can replay the game, without an account.
CREATE TABLE IF NOT EXISTS game_links (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,
    show_opponent INTEGER NOT NULL DEFAULT 0,
    views INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
-- The roadmap: how far the student has got with each topic (kept when their level changes).
CREATE TABLE IF NOT EXISTS roadmap_progress (
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (player_id, topic)
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE TABLE IF NOT EXISTS goal_steps (
    id INTEGER PRIMARY KEY,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
"""

# Optional contact details on the account (private: shown to the person and to admins only).
USER_COLUMNS = {
    "phone": "TEXT NOT NULL DEFAULT ''",
    "state": "TEXT NOT NULL DEFAULT ''",
}

# An admin's reply to a feedback or contact message.
FEEDBACK_COLUMNS = {
    "reply": "TEXT NOT NULL DEFAULT ''",
    "replied_at": "REAL",
    "replied_by": "TEXT NOT NULL DEFAULT ''",
}

PLAYER_COLUMNS = {
    "uscf_id": "TEXT NOT NULL DEFAULT ''",
    "uscf_name": "TEXT NOT NULL DEFAULT ''",
    "uscf_ratings": "TEXT NOT NULL DEFAULT ''",
    "uscf_synced_at": "REAL",
}

# A session an admin opened to see the app as another user (read-only): who opened it.
SESSION_COLUMNS = {"impersonator_id": "INTEGER"}
# A scoresheet photo can belong to a saved notation (moves still to be entered).
SCORESHEET_COLUMNS = {"notation_id": "INTEGER"}

# Planning details for upcoming tournaments. The four checklist items hold 'todo', 'done' or 'na' (not needed).
EVENT_COLUMNS = {
    "address": "TEXT NOT NULL DEFAULT ''",
    "website": "TEXT NOT NULL DEFAULT ''",
    "entry_fee": "TEXT NOT NULL DEFAULT ''",
    "reg_deadline": "TEXT NOT NULL DEFAULT ''",
    "attending": "TEXT NOT NULL DEFAULT 'maybe'",
    "reg_status": "TEXT NOT NULL DEFAULT 'todo'",
    "paid_status": "TEXT NOT NULL DEFAULT 'todo'",
    "hotel_status": "TEXT NOT NULL DEFAULT 'todo'",
    "travel_status": "TEXT NOT NULL DEFAULT 'todo'",
    "reg_confirmation": "TEXT NOT NULL DEFAULT ''",
    "hotel_name": "TEXT NOT NULL DEFAULT ''",
    "hotel_checkin": "TEXT NOT NULL DEFAULT ''",
    "hotel_checkout": "TEXT NOT NULL DEFAULT ''",
    "hotel_confirmation": "TEXT NOT NULL DEFAULT ''",
    # Every rating change USCF lists for the event (JSON: [{"system": "R", "before": 1443, "after": 1405}, ...]).
    "ratings": "TEXT NOT NULL DEFAULT ''",
    # Preparation steps ticked by hand for an upcoming tournament (JSON list of step keys).
    "prep_done": "TEXT NOT NULL DEFAULT ''",
}


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.tx() as conn:
            old_sheets = [r["name"] for r in conn.execute("PRAGMA table_info(scoresheets)")]
            rebuild = bool(old_sheets) and "game_id" not in old_sheets
            if rebuild:
                conn.execute("DROP INDEX IF EXISTS scoresheets_by_round")
                conn.execute("ALTER TABLE scoresheets RENAME TO scoresheets_old")
            conn.executescript(SCHEMA)
            if rebuild:
                conn.execute("INSERT INTO scoresheets(id, user_id, round_id, storage_key, content_type, bytes, created_at) "
                             "SELECT id, user_id, round_id, storage_key, content_type, bytes, created_at FROM scoresheets_old")
                conn.execute("DROP TABLE scoresheets_old")
                conn.execute("CREATE INDEX IF NOT EXISTS scoresheets_by_round ON scoresheets(round_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS scoresheets_by_game ON scoresheets(game_id)")
            # Databases made before folders existed get the new column.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
            if "folder_id" not in columns:
                conn.execute("ALTER TABLE games ADD COLUMN folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL")
            # ...and databases made before email verification: their existing accounts count as verified.
            have = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            if "email_verified_at" not in have:
                conn.execute("ALTER TABLE users ADD COLUMN email_verified_at REAL")
                conn.execute("UPDATE users SET email_verified_at = created_at")
            have = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            for column, definition in USER_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            have = {row["name"] for row in conn.execute("PRAGMA table_info(feedback)")}
            for column, definition in FEEDBACK_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE feedback ADD COLUMN {column} {definition}")
            # ...and databases made before the USCF connection get its columns on the players table.
            have = {row["name"] for row in conn.execute("PRAGMA table_info(players)")}
            for column, definition in PLAYER_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE players ADD COLUMN {column} {definition}")
            have = {row["name"] for row in conn.execute("PRAGMA table_info(scoresheets)")}
            for column, definition in SCORESHEET_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE scoresheets ADD COLUMN {column} {definition}")
            have = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
            for column, definition in SESSION_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} {definition}")
            # ...and databases made before the tournament planner get its columns on the events table.
            have = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
            for column, definition in EVENT_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE events ADD COLUMN {column} {definition}")

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def run(self, sql: str, params: tuple | dict = ()) -> int:
        """Execute a write; returns the new row id (or affected row count for updates)."""
        with self.tx() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self._conn().execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        row = self._conn().execute(sql, params).fetchone()
        return dict(row) if row else None


def _pg_types(ddl: str) -> str:
    """SQLite column types -> PostgreSQL. REAL must become 8-byte: it holds Unix timestamps."""
    ddl = ddl.replace("INTEGER PRIMARY KEY", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
    ddl = re.sub(r"\bINTEGER\b", "BIGINT", ddl)
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", ddl)


# Tables with an `id` identity column; an INSERT into one of them returns the new id, as SQLite's lastrowid does.
_ID_TABLES = frozenset(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(\s*id INTEGER PRIMARY KEY", SCHEMA))
_INSERT_TABLE = re.compile(r"\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", re.IGNORECASE)


def _pg_sql(sql: str) -> str:
    """Translate the SQLite dialect the app uses into PostgreSQL."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    sql = re.sub(r"(\w+) COLLATE NOCASE", r"LOWER(\1)", sql)
    if re.match(r"\s*INSERT\s+OR\s+IGNORE\b", sql, re.IGNORECASE):
        sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", sql, count=1, flags=re.IGNORECASE) + " ON CONFLICT DO NOTHING"
    return sql


class PostgresDatabase(Database):
    """PostgreSQL storage with the same interface as Database. Connections come from a small pool."""

    def __init__(self, url: str):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.path = None
        self._pool = ConnectionPool(url, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
        with self.tx() as conn:
            users_columns = {r["column_name"] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'users'")}
            # Databases made before email verification: their existing accounts count as verified.
            if users_columns and "email_verified_at" not in users_columns:
                conn.execute("ALTER TABLE users ADD COLUMN email_verified_at DOUBLE PRECISION")
                conn.execute("UPDATE users SET email_verified_at = created_at")
            sheets = {r["column_name"] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                "AND table_name = 'scoresheets'")}
            if sheets and "game_id" not in sheets:
                conn.execute("ALTER TABLE scoresheets ADD COLUMN game_id BIGINT REFERENCES games(id) ON DELETE CASCADE")
                conn.execute("ALTER TABLE scoresheets ALTER COLUMN round_id DROP NOT NULL")
            conn.execute(_pg_types(SCHEMA))
            conn.execute("CREATE INDEX IF NOT EXISTS scoresheets_by_game ON scoresheets(game_id)")
            for table, columns in (("users", USER_COLUMNS), ("feedback", FEEDBACK_COLUMNS), ("players", PLAYER_COLUMNS), ("events", EVENT_COLUMNS), ("sessions", SESSION_COLUMNS), ("scoresheets", SCORESHEET_COLUMNS)):
                for column, definition in columns.items():
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {_pg_types(definition)}")

    @contextmanager
    def tx(self) -> Iterator[Any]:
        # The pool commits when the block ends and rolls back if it raises.
        with self._pool.connection() as conn:
            yield conn

    def close(self) -> None:
        self._pool.close()

    def run(self, sql: str, params: tuple | dict = ()) -> int:
        insert = _INSERT_TABLE.match(sql)
        returning = bool(insert) and insert.group(1) in _ID_TABLES and "RETURNING" not in sql.upper()
        with self.tx() as conn:
            cur = conn.execute(_pg_sql(sql) + (" RETURNING id" if returning else ""), params)
            if returning:
                row = cur.fetchone()
                return row["id"] if row else 0
            return cur.rowcount

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.tx() as conn:
            return conn.execute(_pg_sql(sql), params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self.tx() as conn:
            return conn.execute(_pg_sql(sql), params).fetchone()


def open_database(data_dir: Path, url: str | None = None) -> Database:
    """PostgreSQL when a URL is given, otherwise the SQLite file in data_dir."""
    if url:
        return PostgresDatabase(url)
    return Database(Path(data_dir) / "chesscoach.sqlite3")

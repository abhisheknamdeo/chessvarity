"""Runtime settings, read from environment variables so the app can be deployed anywhere."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("CHESSCOACH_DATA", ROOT / "data")))
    # A postgresql:// URL switches storage from the SQLite file in data_dir to PostgreSQL.
    database_url: str | None = field(default_factory=lambda: os.environ.get("DATABASE_URL") or None)
    stockfish_path: str | None = field(default_factory=lambda: os.environ.get("STOCKFISH_PATH"))
    depth: int = field(default_factory=lambda: int(os.environ.get("CHESSCOACH_DEPTH", "12")))
    # More than one thread is faster but makes results vary slightly from run to run.
    threads: int = field(default_factory=lambda: int(os.environ.get("CHESSCOACH_THREADS", "1")))
    allow_signup: bool = field(default_factory=lambda: _flag("CHESSCOACH_ALLOW_SIGNUP", True))
    # Set to true when the app is served over HTTPS so session cookies are never sent in the clear.
    cookie_secure: bool = field(default_factory=lambda: _flag("CHESSCOACH_COOKIE_SECURE", False))
    session_days: int = field(default_factory=lambda: int(os.environ.get("CHESSCOACH_SESSION_DAYS", "30")))
    # New accounts must confirm their email before they can sign in. Needs a working mail backend.
    verify_email: bool = field(default_factory=lambda: _flag("CHESSCOACH_VERIFY_EMAIL", False))
    # log (print emails to the log), ses (Amazon SES) or memory (tests). See mailer.py.
    mail_backend: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_MAIL_BACKEND", "log"))
    mail_from: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_MAIL_FROM", "Chess Varsity <no-reply@localhost>"))
    mail_region: str | None = field(default_factory=lambda: os.environ.get("AWS_REGION") or None)
    # Where feedback notifications go; empty means feedback is only saved.
    feedback_to: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_FEEDBACK_TO", ""))
    # Accounts that may open the admin dashboard (comma-separated). Their email must also be confirmed.
    admin_emails: tuple[str, ...] = field(default_factory=lambda: tuple(
        e.strip().lower() for e in os.environ.get("CHESSCOACH_ADMIN_EMAILS", "").split(",") if e.strip()))
    # Shown on the contact page; empty shows the form only. Contact messages go to feedback_to.
    contact_email: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_CONTACT_EMAIL", "").strip())
    # "Continue with Google": an OAuth client (Web application) from Google Cloud Console. Empty turns it off.
    google_client_id: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_GOOGLE_CLIENT_ID", "").strip())
    google_client_secret: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_GOOGLE_CLIENT_SECRET", "").strip())
    # "Continue with Apple": a Services ID, the team, and a Sign in with Apple key (.p8 contents). Empty turns it off.
    apple_client_id: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_APPLE_CLIENT_ID", "").strip())
    apple_team_id: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_APPLE_TEAM_ID", "").strip())
    apple_key_id: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_APPLE_KEY_ID", "").strip())
    apple_private_key: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_APPLE_PRIVATE_KEY", "").replace("\\n", "\n").strip())
    # Uploaded photos: "local" (under data_dir/uploads) or "s3" (private bucket below). See storage.py.
    storage: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_STORAGE", "local").strip())
    s3_bucket: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_S3_BUCKET", "").strip())
    # The site's public address, used in links inside emails. Empty: taken from each request.
    public_url: str = field(default_factory=lambda: os.environ.get("CHESSCOACH_PUBLIC_URL", "").rstrip("/"))
    max_games_per_upload: int = 60
    max_pgn_bytes: int = 3_000_000

    @property
    def db_path(self) -> Path:
        return self.data_dir / "chesscoach.sqlite3"

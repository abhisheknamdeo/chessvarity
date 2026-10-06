"""Passwords, sessions and login throttling, using only the standard library."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from .db import Database

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD = 8
COOKIE = "cc_session"
# Accounts made with Google or Apple start without a password; this matches no password at all.
NO_PASSWORD = "!"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    b64 = lambda raw: base64.b64encode(raw).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def has_password(stored: str) -> bool:
    return bool(stored) and stored != NO_PASSWORD


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Database, user_id: int, days: float, impersonator_id: int | None = None) -> str:
    """A random token goes to the browser; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    db.run(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at, impersonator_id) VALUES (?,?,?,?,?)",
        (_token_hash(token), user_id, now, now + days * 86400, impersonator_id),
    )
    return token


def user_for_session(db: Database, token: str | None) -> dict | None:
    if not token:
        return None
    row = db.one(
        "SELECT u.id, u.email, u.display_name, u.created_at, u.email_verified_at, s.expires_at, s.impersonator_id FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (_token_hash(token),),
    )
    if row is None:
        return None
    if row["expires_at"] < time.time():
        db.run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        return None
    return row


EMAIL_TOKEN_HOURS = {"verify": 48, "reset": 1}


def create_email_token(db: Database, user_id: int, purpose: str) -> str:
    """A single-use link token for an email. Issuing a new one cancels the older unused ones."""
    now = time.time()
    db.run("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ? AND used_at IS NULL", (user_id, purpose))
    token = secrets.token_urlsafe(32)
    db.run(
        "INSERT INTO email_tokens(token_hash, user_id, purpose, created_at, expires_at) VALUES (?,?,?,?,?)",
        (_token_hash(token), user_id, purpose, now, now + EMAIL_TOKEN_HOURS[purpose] * 3600),
    )
    return token


def use_email_token(db: Database, token: str, purpose: str) -> int | None:
    """The user id if the token is valid, unused and unexpired; marks it used so it works only once."""
    if not token or len(token) > 200:
        return None
    now = time.time()
    claimed = db.run(
        "UPDATE email_tokens SET used_at = ? WHERE token_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?",
        (now, _token_hash(token), purpose, now),
    )
    if claimed != 1:
        return None
    row = db.one("SELECT user_id FROM email_tokens WHERE token_hash = ?", (_token_hash(token),))
    return row["user_id"] if row else None


def end_all_sessions(db: Database, user_id: int) -> None:
    db.run("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def end_session(db: Database, token: str | None) -> None:
    if token:
        db.run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def end_other_sessions(db: Database, user_id: int, keep_token: str | None) -> None:
    keep = _token_hash(keep_token) if keep_token else ""
    db.run("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, keep))


class Throttle:
    """Allow `limit` failures per `window` seconds for a key; a success resets the count."""

    def __init__(self, limit: int = 8, window: float = 900.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str) -> deque[float]:
        hits = self._hits[key]
        cutoff = time.time() - self.window
        while hits and hits[0] < cutoff:
            hits.popleft()
        return hits

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._trim(key)) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._trim(key).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

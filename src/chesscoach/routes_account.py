"""Sign-up, sign-in and the student's own profile. One account is one student."""

from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .deps import get_db, is_admin, my_player, require_user
from .mailer import Message
from .security import (
    COOKIE, EMAIL_TOKEN_HOURS, MIN_PASSWORD, Throttle, create_email_token, create_session, end_all_sessions, user_for_session,
    end_other_sessions, end_session, has_password, hash_password, use_email_token, verify_password,
)
from . import oauth

router = APIRouter(prefix="/api")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
RATING_SYSTEMS = ("USCF", "FIDE", "Lichess", "Chess.com", "Other")
# US states (and DC), plus a choice for everyone else. Stored as the two-letter code.
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "XX": "Outside the US",
}
PHONE = re.compile(r"^\+?[0-9 ().-]{7,24}$")


def _clean_phone(raw: str) -> str:
    """Empty, or a phone number of 7 to 15 digits written with the usual symbols (+, spaces, dashes, brackets, dots)."""
    phone = " ".join(raw.split())
    if not phone:
        return ""
    digits = sum(ch.isdigit() for ch in phone)
    if not PHONE.match(phone) or not 7 <= digits <= 15:
        raise HTTPException(400, "That phone number doesn't look right. Use digits, with + for a country code if you like.")
    return phone


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class Register(Credentials):
    display_name: str = Field(min_length=1, max_length=60)


class EmailOnly(BaseModel):
    email: str = Field(max_length=254)


class TokenOnly(BaseModel):
    token: str = Field(max_length=200)


class PasswordReset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=200)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    rating: int | None = Field(default=None, ge=0, le=3500)
    rating_system: str = "USCF"
    # Optional; left out means "keep what is saved".
    phone: str | None = Field(default=None, max_length=30)
    state: str | None = Field(default=None, max_length=2)


class PasswordChange(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class DeleteAccount(BaseModel):
    password: str = Field(max_length=200)


def _public(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"],
            "email_verified": bool(user.get("email_verified_at"))}


def _link(request: Request, page: str, token: str) -> str:
    # The token sits after '#', so it never reaches server logs or other sites' Referer headers.
    base = request.app.state.settings.public_url or str(request.base_url).rstrip("/")
    return f"{base}/#/{page}?token={token}"


def _send_verification(request: Request, user_id: int, email: str, name: str) -> None:
    token = create_email_token(get_db(request), user_id, "verify")
    request.app.state.mailer.send(Message(email, "Confirm your email for Chess Varsity", (
        f"Hi {name},\n\n"
        "Welcome to Chess Varsity! Please confirm your email address to finish creating your account:\n\n"
        f"{_link(request, 'verify', token)}\n\n"
        f"This link works once and expires in {EMAIL_TOKEN_HOURS['verify']} hours.\n\n"
        "If you did not sign up for Chess Varsity, you can ignore this email.")))


def _send_reset(request: Request, user_id: int, email: str, name: str) -> None:
    token = create_email_token(get_db(request), user_id, "reset")
    request.app.state.mailer.send(Message(email, "Reset your Chess Varsity password", (
        f"Hi {name},\n\n"
        "Someone (hopefully you) asked to reset the password for your Chess Varsity account. "
        "Choose a new password here:\n\n"
        f"{_link(request, 'reset', token)}\n\n"
        f"This link works once and expires in {EMAIL_TOKEN_HOURS['reset']} hour.\n\n"
        "If you did not ask for this, ignore this email: your password stays the same.")))


def _mail_throttled(request: Request, email: str) -> bool:
    """At most a few emails per address and per sender per hour, so the forms can't be used to spam anyone."""
    throttle: Throttle = request.app.state.mail_throttle
    ip = request.client.host if request.client else "?"
    keys = (f"ip|{ip}", f"to|{email}")
    if any(throttle.blocked(k) for k in keys):
        return True
    for k in keys:
        throttle.fail(k)
    return False


def _player(request: Request, user: dict) -> dict:
    row = my_player(request, user)
    return {k: row[k] for k in ("id", "name", "rating", "rating_system", "uscf_id", "uscf_name")}


def _set_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        COOKIE, token, max_age=settings.session_days * 86400, httponly=True,
        samesite="lax", secure=settings.cookie_secure, path="/",
    )


def _check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(400, f"Use a password with at least {MIN_PASSWORD} characters.")


@router.post("/auth/register")
def register(body: Register, request: Request, response: Response) -> dict:
    if not request.app.state.settings.allow_signup:
        raise HTTPException(403, "Sign-ups are closed on this server.")
    signups: Throttle = request.app.state.signup_throttle
    ip = request.client.host if request.client else "?"
    if signups.blocked(ip):
        raise HTTPException(429, "Too many accounts were created from this address. Please try again later.")
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(400, "That email address doesn't look right.")
    _check_password_rules(body.password)
    db = get_db(request)
    if db.one("SELECT 1 FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with that email already exists.")
    name = body.display_name.strip()
    user_id = db.run(
        "INSERT INTO users(email, display_name, password_hash, created_at) VALUES (?,?,?,?)",
        (email, name, hash_password(body.password), time.time()),
    )
    _player(request, {"id": user_id, "display_name": name})
    signups.fail(ip)  # counts this creation towards the hourly limit
    if request.app.state.settings.verify_email:
        # No session until the email is confirmed: the link in the email signs them in.
        _mail_throttled(request, email)
        _send_verification(request, user_id, email, name)
        return {"verification_required": True, "email": email}
    _set_cookie(request, response, create_session(db, user_id, request.app.state.settings.session_days))
    return {"user": {"id": user_id, "email": email, "display_name": name, "email_verified": False}}


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    email = body.email.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    throttle: Throttle = request.app.state.throttle
    if throttle.blocked(key):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
    db = get_db(request)
    row = db.one("SELECT * FROM users WHERE email = ?", (email,))
    # Hash even for unknown emails so response time does not reveal which accounts exist.
    ok = verify_password(body.password, row["password_hash"] if row else hash_password("x"))
    if not row or not ok:
        throttle.fail(key)
        raise HTTPException(401, "Email or password is not right.")
    throttle.reset(key)
    if request.app.state.settings.verify_email and not row["email_verified_at"]:
        # Only said after a correct password, so it never reveals that an address has an account.
        raise HTTPException(403, "Please confirm your email first. Check your inbox for the link we sent.")
    _set_cookie(request, response, create_session(db, row["id"], request.app.state.settings.session_days))
    return {"user": _public(row)}


@router.post("/auth/verify")
def verify_email(body: TokenOnly, request: Request, response: Response) -> dict:
    db = get_db(request)
    user_id = use_email_token(db, body.token, "verify")
    if user_id is None:
        raise HTTPException(400, "This link has expired or was already used. Sign in to get a new one.")
    db.run("UPDATE users SET email_verified_at = ? WHERE id = ? AND email_verified_at IS NULL", (time.time(), user_id))
    _set_cookie(request, response, create_session(db, user_id, request.app.state.settings.session_days))
    return {"user": _public(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))}


@router.post("/auth/resend-verification")
def resend_verification(body: EmailOnly, request: Request) -> dict:
    email = body.email.strip().lower()
    # The same answer whether or not the address has an account.
    answer = {"ok": True, "message": "If that account is waiting for confirmation, we've sent a new link."}
    if not request.app.state.settings.verify_email or _mail_throttled(request, email):
        return answer
    row = get_db(request).one("SELECT * FROM users WHERE email = ?", (email,))
    if row and not row["email_verified_at"]:
        _send_verification(request, row["id"], row["email"], row["display_name"])
    return answer


@router.post("/auth/send-verification")
def send_my_verification(request: Request) -> dict:
    """A signed-in user asks for a link to confirm their own address (works whether or not confirmation is required)."""
    user = require_user(request)
    if user["email_verified_at"]:
        return {"ok": True, "message": "Your email is already confirmed."}
    if _mail_throttled(request, user["email"]):
        raise HTTPException(429, "We sent a few links already. Please check your inbox, or try again in an hour.")
    _send_verification(request, user["id"], user["email"], user["display_name"])
    return {"ok": True, "message": f"We sent a link to {user['email']}. Open it to confirm your email."}


@router.post("/auth/forgot")
def forgot_password(body: EmailOnly, request: Request) -> dict:
    email = body.email.strip().lower()
    answer = {"ok": True, "message": "If an account uses that email, we've sent a link to reset the password."}
    if not EMAIL.match(email) or _mail_throttled(request, email):
        return answer
    row = get_db(request).one("SELECT * FROM users WHERE email = ?", (email,))
    if row:
        _send_reset(request, row["id"], row["email"], row["display_name"])
    return answer


@router.post("/auth/reset")
def reset_password(body: PasswordReset, request: Request) -> dict:
    _check_password_rules(body.password)  # before using the token, so a too-short password doesn't spend it
    db = get_db(request)
    user_id = use_email_token(db, body.token, "reset")
    if user_id is None:
        raise HTTPException(400, "This link has expired or was already used. Ask for a new one.")
    # Opening the link proves they own the address, so it also counts as confirming it.
    db.run("UPDATE users SET password_hash = ?, email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
           (hash_password(body.password), time.time(), user_id))
    end_all_sessions(db, user_id)  # sign out everywhere: whoever knew the old password is locked out
    return {"ok": True}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    end_session(get_db(request), request.cookies.get(COOKIE))
    end_session(get_db(request), request.cookies.get("cc_admin_session"))  # signing out while viewing ends both
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie("cc_admin_session", path="/")
    return {"ok": True}


@router.post("/auth/stop-viewing")
def stop_viewing(request: Request, response: Response) -> dict:
    """End an admin's read-only view of another account and go back to the admin's own session."""
    db = get_db(request)
    user = require_user(request)
    if not user.get("impersonator_id"):
        return {"ok": True}
    end_session(db, request.cookies.get(COOKIE))
    own = request.cookies.get("cc_admin_session", "")
    admin = user_for_session(db, own)
    response.delete_cookie("cc_admin_session", path="/")
    if admin and admin["id"] == user["impersonator_id"]:
        _set_cookie(request, response, own)
    else:
        response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict:
    user = require_user(request)
    db = get_db(request)
    row = db.one("SELECT password_hash, phone, state FROM users WHERE id = ?", (user["id"],))
    linked = db.all("SELECT provider, email FROM user_identities WHERE user_id = ? ORDER BY provider", (user["id"],))
    viewer = db.one("SELECT display_name FROM users WHERE id = ?", (user["impersonator_id"],)) if user.get("impersonator_id") else None
    return {"user": {**_public(user), "is_admin": is_admin(request, user), "has_password": has_password(row["password_hash"]),
                     "identities": linked, "viewed_by": viewer["display_name"] if viewer else None,
                     "phone": row["phone"], "state": row["state"]},
            "states": [{"code": k, "name": v} for k, v in US_STATES.items()],
            "player": _player(request, user), "signup_open": request.app.state.settings.allow_signup,
            "providers": oauth.enabled(request.app.state.settings)}


@router.patch("/auth/me")
def update_me(body: ProfileUpdate, request: Request) -> dict:
    user = require_user(request)
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(400, "That email address doesn't look right.")
    if body.rating_system not in RATING_SYSTEMS:
        raise HTTPException(400, "Unknown rating system.")
    db = get_db(request)
    if db.one("SELECT id FROM users WHERE email = ? AND id != ?", (email, user["id"])):
        raise HTTPException(409, "Another account already uses that email.")
    name = body.display_name.strip()
    db.run("UPDATE users SET display_name = ?, email = ? WHERE id = ?", (name, email, user["id"]))
    if body.phone is not None:
        db.run("UPDATE users SET phone = ? WHERE id = ?", (_clean_phone(body.phone), user["id"]))
    if body.state is not None:
        state = body.state.strip().upper()
        if state and state not in US_STATES:
            raise HTTPException(400, "Please choose a state from the list.")
        db.run("UPDATE users SET state = ? WHERE id = ?", (state, user["id"]))
    verification_sent = False
    if email != user["email"] and request.app.state.settings.verify_email:
        # A new address has to be confirmed too; until then, signing in again asks for it.
        db.run("UPDATE users SET email_verified_at = NULL WHERE id = ?", (user["id"],))
        _send_verification(request, user["id"], email, name)
        verification_sent = True
    player = _player(request, user)
    # The name is also how games are matched to you, so it lives in both places.
    db.run("UPDATE players SET name = ?, rating = ?, rating_system = ? WHERE id = ?",
           (name, body.rating, body.rating_system, player["id"]))
    row = db.one("SELECT * FROM users WHERE id = ?", (user["id"],))
    return {"user": {**_public(row), "phone": row["phone"], "state": row["state"]},
            "player": _player(request, user), "verification_sent": verification_sent}


@router.post("/auth/password")
def change_password(body: PasswordChange, request: Request) -> dict:
    user = require_user(request)
    db = get_db(request)
    row = db.one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    # Accounts made with Google or Apple have no password yet, so there is nothing to check the first time.
    if has_password(row["password_hash"]) and not verify_password(body.current, row["password_hash"]):
        raise HTTPException(403, "Your current password is not right.")
    _check_password_rules(body.new)
    db.run("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new), user["id"]))
    end_other_sessions(db, user["id"], request.cookies.get(COOKIE))
    return {"ok": True}


@router.post("/auth/delete")
def delete_account(body: DeleteAccount, request: Request, response: Response) -> dict:
    user = require_user(request)
    db = get_db(request)
    row = db.one("SELECT password_hash, email FROM users WHERE id = ?", (user["id"],))
    if has_password(row["password_hash"]):
        if not verify_password(body.password, row["password_hash"]):
            raise HTTPException(403, "Your password is not right.")
    elif body.password.strip().lower() != row["email"]:
        # No password to ask for (Google or Apple account), so typing the email confirms it instead.
        raise HTTPException(403, "Type your email address exactly to confirm.")
    from .routes_scoresheets import delete_stored  # photos live outside the database, so remove them first
    delete_stored(request, "user_id = ?", (user["id"],))
    db.run("DELETE FROM users WHERE id = ?", (user["id"],))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}

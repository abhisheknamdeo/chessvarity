"""Web endpoints for "Continue with Google / Apple", and connecting those accounts from the profile page."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from . import oauth
from .deps import get_db, require_user
from .oauth import PROVIDERS, OAuthError
from .routes_account import _player, _set_cookie
from .security import NO_PASSWORD, Throttle, create_session, has_password

log = logging.getLogger("chesscoach.oauth")
router = APIRouter(prefix="/api")

STATE_COOKIE = "cc_oauth"
STATE_SECONDS = 600


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _base(request: Request) -> str:
    return request.app.state.settings.public_url or str(request.base_url).rstrip("/")


def _redirect_uri(request: Request, provider: str) -> str:
    return f"{_base(request)}/api/auth/oauth/{provider}/callback"


def _check_provider(request: Request, provider: str) -> None:
    if provider not in PROVIDERS or not oauth.enabled(request.app.state.settings)[provider]:
        raise HTTPException(404, "That sign-in option is not available.")


@router.get("/auth/providers")
def providers(request: Request) -> dict:
    return oauth.enabled(request.app.state.settings)


@router.get("/auth/oauth/{provider}/start")
def start(provider: str, request: Request, link: bool = False) -> RedirectResponse:
    """Send the browser to Google or Apple. With ?link=1 (signed in), the account is connected instead of signed in."""
    _check_provider(request, provider)
    link_user = require_user(request) if link else None
    if link_user and link_user.get("impersonator_id"):
        # Starts with a GET, so the read-only check in require_user doesn't catch it: never connect the admin's
        # Google/Apple account to the account being viewed.
        raise HTTPException(403, "You're viewing as another user, so changes are switched off.")
    db = get_db(request)
    now = time.time()
    db.run("DELETE FROM oauth_states WHERE created_at < ?", (now - STATE_SECONDS,))
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(24), oauth.new_verifier()
    db.run("INSERT INTO oauth_states(state_hash, provider, nonce, verifier, link_user_id, created_at) VALUES (?,?,?,?,?,?)",
           (_hash(state), provider, nonce, verifier, link_user["id"] if link_user else None, now))
    settings = request.app.state.settings
    response = RedirectResponse(oauth.authorize_url(settings, provider, _redirect_uri(request, provider), state, nonce, verifier), 302)
    # Ties the sign-in to this browser. Apple answers with a cross-site POST, which only carries SameSite=None cookies.
    response.set_cookie(STATE_COOKIE, state, max_age=STATE_SECONDS, httponly=True, secure=settings.cookie_secure,
                        samesite="none" if settings.cookie_secure else "lax", path="/api/auth/oauth")
    return response


@router.api_route("/auth/oauth/{provider}/callback", methods=["GET", "POST"])
async def callback(provider: str, request: Request) -> RedirectResponse:
    if request.method == "POST":  # Apple (response_mode=form_post)
        body = (await request.body())[:20000].decode("utf-8", "replace")
        params = {k: v[0] for k, v in parse_qs(body).items()}
    else:
        params = dict(request.query_params)
    return await run_in_threadpool(_complete, provider, request, params)


def _complete(provider: str, request: Request, params: dict) -> RedirectResponse:
    db = get_db(request)
    settings = request.app.state.settings
    back_to = "login"
    try:
        if provider not in PROVIDERS or not oauth.enabled(settings)[provider]:
            raise OAuthError("unavailable")
        state, cookie = params.get("state", ""), request.cookies.get(STATE_COOKIE, "")
        if not state or not cookie or not secrets.compare_digest(state, cookie):
            raise OAuthError("session", "state missing or from another browser")
        row = db.one("SELECT * FROM oauth_states WHERE state_hash = ?", (_hash(state),))
        # Deleting it is what claims it, so a state can be used once even if two answers race.
        if not row or row["provider"] != provider or db.run("DELETE FROM oauth_states WHERE state_hash = ?", (_hash(state),)) != 1:
            raise OAuthError("session", "unknown or used state")
        if row["link_user_id"]:
            back_to = "profile"
        if row["created_at"] < time.time() - STATE_SECONDS:
            raise OAuthError("session", "state too old")
        if params.get("error"):
            raise OAuthError("cancelled" if params["error"] in ("access_denied", "user_cancelled_authorize") else "provider",
                             params["error"])
        if not params.get("code"):
            raise OAuthError("provider", "no code")
        profile = oauth.finish(settings, provider, params["code"], _redirect_uri(request, provider), row["nonce"],
                               row["verifier"], params.get("user", ""))
        user_id, is_new = _match_account(request, provider, profile, row["link_user_id"])
    except OAuthError as err:
        log.warning("%s sign-in refused (%s): %s", provider, err.code, err)
        response = RedirectResponse(f"{_base(request)}/#/{back_to}?error={err.code}&provider={provider}", 302)
        response.delete_cookie(STATE_COOKIE, path="/api/auth/oauth")
        return response

    if back_to == "profile":
        response = RedirectResponse(f"{_base(request)}/#/profile?linked={provider}", 302)
    else:
        response = RedirectResponse(f"{_base(request)}/#/{'add' if is_new else ''}", 302)
        _set_cookie(request, response, create_session(db, user_id, settings.session_days))
    response.delete_cookie(STATE_COOKIE, path="/api/auth/oauth")
    return response


def _add_identity(request: Request, provider: str, profile: dict, user_id: int) -> None:
    get_db(request).run("INSERT INTO user_identities(provider, subject, user_id, email, created_at) VALUES (?,?,?,?,?)",
                        (provider, profile["subject"], user_id, profile["email"], time.time()))


def _match_account(request: Request, provider: str, profile: dict, link_user_id: int | None) -> tuple[int, bool]:
    """(user id, whether the account is new). Sign in, connect, or create, in that order."""
    db = get_db(request)
    known = db.one("SELECT user_id FROM user_identities WHERE provider = ? AND subject = ?", (provider, profile["subject"]))
    if link_user_id:
        if known and known["user_id"] != link_user_id:
            raise OAuthError("taken", "identity belongs to another account")
        if not known:
            _add_identity(request, provider, profile, link_user_id)
        return link_user_id, False
    if known:
        return known["user_id"], False
    if not profile["email"]:
        raise OAuthError("no_email")
    if not profile["email_verified"]:
        raise OAuthError("unverified")
    now = time.time()
    existing = db.one("SELECT id FROM users WHERE email = ?", (profile["email"],))
    if existing:
        # The provider has checked the person owns this address, so it is safe to connect it to the account using it.
        _add_identity(request, provider, profile, existing["id"])
        db.run("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?", (now, existing["id"]))
        return existing["id"], False
    settings = request.app.state.settings
    if not settings.allow_signup:
        raise OAuthError("closed")
    signups: Throttle = request.app.state.signup_throttle
    ip = request.client.host if request.client else "?"
    if signups.blocked(ip):
        raise OAuthError("busy")
    signups.fail(ip)
    name = profile["name"] or profile["email"].split("@")[0][:60]
    user_id = db.run(
        "INSERT INTO users(email, display_name, password_hash, created_at, email_verified_at) VALUES (?,?,?,?,?)",
        (profile["email"], name, NO_PASSWORD, now, now),
    )
    _player(request, {"id": user_id, "display_name": name})
    _add_identity(request, provider, profile, user_id)
    return user_id, True


@router.post("/auth/identities/{provider}/disconnect")
def disconnect(provider: str, request: Request) -> dict:
    user = require_user(request)
    db = get_db(request)
    mine = [r["provider"] for r in db.all("SELECT provider FROM user_identities WHERE user_id = ?", (user["id"],))]
    if provider not in mine:
        raise HTTPException(404, "That account is not connected.")
    row = db.one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    if not has_password(row["password_hash"]) and len(mine) == 1:
        raise HTTPException(400, "Set a password first, so you can still sign in without it.")
    db.run("DELETE FROM user_identities WHERE user_id = ? AND provider = ?", (user["id"], provider))
    return {"ok": True}

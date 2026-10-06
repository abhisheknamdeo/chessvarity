"""Sign in with Google or Apple (OpenID Connect, authorization-code flow).

The ID token comes straight from the provider's token endpoint over TLS, so, as the OpenID Connect spec allows,
we check its issuer, audience, expiry and nonce rather than its signature. Google also gets PKCE.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    issuers: tuple[str, ...]
    scope: str
    form_post: bool  # the provider sends the result back as a POST instead of a GET
    pkce: bool


PROVIDERS = {
    "google": Provider("google", "Google", "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token",
                       ("https://accounts.google.com", "accounts.google.com"), "openid email profile", False, True),
    "apple": Provider("apple", "Apple", "https://appleid.apple.com/auth/authorize", "https://appleid.apple.com/auth/token",
                      ("https://appleid.apple.com",), "name email", True, False),
}


class OAuthError(Exception):
    """A sign-in that can't go ahead. `code` is shown to the user as a friendly message by the web app."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def enabled(settings: Settings) -> dict[str, bool]:
    return {
        "google": bool(settings.google_client_id and settings.google_client_secret),
        "apple": bool(settings.apple_client_id and settings.apple_team_id and settings.apple_key_id and settings.apple_private_key),
    }


def client_id(settings: Settings, provider: str) -> str:
    return settings.google_client_id if provider == "google" else settings.apple_client_id


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def new_verifier() -> str:
    return secrets.token_urlsafe(48)


def authorize_url(settings: Settings, provider: str, redirect_uri: str, state: str, nonce: str, verifier: str) -> str:
    p = PROVIDERS[provider]
    params = {"client_id": client_id(settings, provider), "redirect_uri": redirect_uri, "response_type": "code",
              "scope": p.scope, "state": state, "nonce": nonce}
    if p.form_post:
        params["response_mode"] = "form_post"
    if p.pkce:
        params["code_challenge"] = _b64url(hashlib.sha256(verifier.encode()).digest())
        params["code_challenge_method"] = "S256"
    if provider == "google":
        params["prompt"] = "select_account"
    return f"{p.authorize_url}?{urllib.parse.urlencode(params)}"


def _apple_client_secret(settings: Settings) -> str:
    """Apple wants a short-lived JWT signed with the team's Sign in with Apple key instead of a fixed secret."""
    import jwt  # PyJWT with cryptography: only needed when Apple is switched on

    now = int(time.time())
    return jwt.encode({"iss": settings.apple_team_id, "iat": now, "exp": now + 300, "aud": "https://appleid.apple.com",
                       "sub": settings.apple_client_id}, settings.apple_private_key, algorithm="ES256",
                      headers={"kid": settings.apple_key_id})


def post_form(url: str, data: dict) -> dict:
    """POST a form and return the JSON answer (a separate function so tests can stand in for the provider)."""
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.load(res)
    except urllib.error.HTTPError as err:
        raise OAuthError("provider", f"token endpoint said {err.code}: {err.read()[:300]!r}") from err
    except OSError as err:
        raise OAuthError("provider", f"could not reach the token endpoint: {err}") from err


def _claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as err:
        raise OAuthError("provider", "malformed ID token") from err


def finish(settings: Settings, provider: str, code: str, redirect_uri: str, nonce: str, verifier: str,
           apple_user: str = "") -> dict:
    """Swap the code for an ID token and return {subject, email, email_verified, name}."""
    p = PROVIDERS[provider]
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": client_id(settings, provider),
            "client_secret": settings.google_client_secret if provider == "google" else _apple_client_secret(settings)}
    if p.pkce:
        data["code_verifier"] = verifier
    answer = post_form(p.token_url, data)
    if "id_token" not in answer:
        raise OAuthError("provider", f"no ID token in the answer: {answer.get('error', '')}")
    claims = _claims(answer["id_token"])
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if claims.get("iss") not in p.issuers or client_id(settings, provider) not in audiences:
        raise OAuthError("provider", "ID token is for someone else")
    if float(claims.get("exp", 0)) < time.time() - 60:
        raise OAuthError("expired", "ID token expired")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OAuthError("provider", "nonce does not match")
    if not claims.get("sub"):
        raise OAuthError("provider", "no subject in the ID token")

    name = claims.get("name") or " ".join(filter(None, [claims.get("given_name"), claims.get("family_name")]))
    if provider == "apple" and apple_user:
        # Apple sends the person's name once, on their very first sign-in, outside the ID token.
        try:
            n = json.loads(apple_user).get("name") or {}
            name = name or " ".join(filter(None, [n.get("firstName"), n.get("lastName")]))
        except (ValueError, AttributeError):
            pass
    verified = claims.get("email_verified")
    return {
        "subject": str(claims["sub"]),
        "email": str(claims.get("email") or "").strip().lower(),
        "email_verified": verified is True or str(verified).lower() == "true",
        "name": " ".join(str(name).split())[:60],
    }

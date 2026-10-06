"""Continue with Google / Apple, against a stand-in provider (no network)."""

import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from chesscoach import oauth
from chesscoach.api import create_app
from chesscoach.config import Settings

APPLE_KEY = ec.generate_private_key(ec.SECP256R1()).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


def id_token(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.sig"


class FakeProvider:
    """Answers the token endpoint with whatever the test sets in `claims`, echoing the nonce from the start step."""

    def __init__(self):
        self.claims = {}
        self.nonce = None
        self.calls = []

    def __call__(self, url, data):
        self.calls.append((url, data))
        issuer = "https://accounts.google.com" if "google" in url else "https://appleid.apple.com"
        aud = data["client_id"]
        return {"id_token": id_token({"iss": issuer, "aud": aud, "exp": time.time() + 600, "nonce": self.nonce, **self.claims})}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(oauth, "post_form", fake)
    settings = Settings(data_dir=tmp_path, mail_backend="memory", public_url="http://testserver",
                        google_client_id="g-client", google_client_secret="g-secret",
                        apple_client_id="com.example.web", apple_team_id="TEAM123", apple_key_id="KEY123",
                        apple_private_key=APPLE_KEY)
    app = create_app(settings, engine_factory=lambda: None)
    with TestClient(app, follow_redirects=False) as client:
        yield app, client, fake


def begin(client, fake, provider="google", link=False):
    res = client.get(f"/api/auth/oauth/{provider}/start" + ("?link=1" if link else ""))
    assert res.status_code == 302, res.text
    query = parse_qs(urlsplit(res.headers["location"]).query)
    fake.nonce = query["nonce"][0]
    return query


def finish(client, provider, state, code="abc", **extra):
    if provider == "apple":
        return client.post("/api/auth/oauth/apple/callback", data={"state": state, "code": code, **extra})
    return client.get("/api/auth/oauth/google/callback", params={"state": state, "code": code, **extra})


def google_sign_in(client, fake, **claims):
    fake.claims = {"sub": "g-1", "email": "kid@example.com", "email_verified": True, "name": "Duke Player", **claims}
    q = begin(client, fake)
    return finish(client, "google", q["state"][0])


def test_providers_listed_only_when_configured(env, tmp_path):
    app, client, _ = env
    assert client.get("/api/auth/providers").json() == {"google": True, "apple": True}
    bare = create_app(Settings(data_dir=tmp_path / "b", mail_backend="memory"), engine_factory=lambda: None)
    with TestClient(bare) as c:
        assert c.get("/api/auth/providers").json() == {"google": False, "apple": False}
        assert c.get("/api/auth/oauth/google/start", follow_redirects=False).status_code == 404


def test_google_start_uses_pkce_state_and_nonce(env):
    _, client, fake = env
    q = begin(client, fake)
    assert q["client_id"] == ["g-client"] and q["response_type"] == ["code"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://testserver/api/auth/oauth/google/callback"]
    assert "openid" in q["scope"][0] and len(q["state"][0]) > 30 and len(q["nonce"][0]) > 20


def test_new_google_user_gets_an_account_with_a_confirmed_email(env):
    app, client, fake = env
    res = google_sign_in(client, fake)
    assert res.status_code == 302 and res.headers["location"] == "http://testserver/#/add"
    me = client.get("/api/auth/me").json()
    assert me["user"]["email"] == "kid@example.com" and me["user"]["display_name"] == "Duke Player"
    assert me["user"]["email_verified"] is True and me["user"]["has_password"] is False
    assert me["user"]["identities"] == [{"provider": "google", "email": "kid@example.com"}]
    assert fake.calls[0][1]["code_verifier"] and fake.calls[0][1]["client_secret"] == "g-secret"

    client.post("/api/auth/logout")
    again = google_sign_in(client, fake, email="changed@example.com")  # same Google account, even if its email changed
    assert again.headers["location"] == "http://testserver/#/"
    assert client.get("/api/auth/me").json()["user"]["email"] == "kid@example.com"
    assert app.state.db.one("SELECT COUNT(*) n FROM users")["n"] == 1


def test_google_connects_to_an_existing_account_with_the_same_verified_email(env):
    app, client, fake = env
    client.post("/api/auth/register", json={"email": "kid@example.com", "password": "correct horse", "display_name": "Kid"})
    client.post("/api/auth/logout")
    google_sign_in(client, fake)
    me = client.get("/api/auth/me").json()["user"]
    assert me["display_name"] == "Kid" and me["has_password"] is True and me["email_verified"] is True
    assert app.state.db.one("SELECT COUNT(*) n FROM users")["n"] == 1


def test_unverified_or_missing_email_is_refused(env):
    app, client, fake = env
    res = google_sign_in(client, fake, email_verified=False)
    assert "#/login?error=unverified" in res.headers["location"]
    res = google_sign_in(client, fake, sub="g-2", email="")
    assert "#/login?error=no_email" in res.headers["location"]
    assert app.state.db.one("SELECT COUNT(*) n FROM users")["n"] == 0


def test_state_must_come_from_this_browser_and_is_single_use(env):
    app, client, fake = env
    fake.claims = {"sub": "g-1", "email": "kid@example.com", "email_verified": True}
    q = begin(client, fake)
    other = TestClient(app, follow_redirects=False)  # a different browser: no state cookie
    assert "error=session" in finish(other, "google", q["state"][0]).headers["location"]
    assert "error=session" in finish(client, "google", "forged-state").headers["location"]
    assert client.get("/api/auth/me").status_code == 401

    q = begin(client, fake)
    first = finish(client, "google", q["state"][0])
    assert first.headers["location"] == "http://testserver/#/add"
    client.cookies.set("cc_oauth", q["state"][0], path="/api/auth/oauth")  # replaying the same answer
    assert "error=session" in finish(client, "google", q["state"][0]).headers["location"]


def test_id_token_for_another_app_or_wrong_nonce_is_refused(env, monkeypatch):
    app, client, fake = env
    fake.claims = {"sub": "g-1", "email": "kid@example.com", "email_verified": True, "aud": "someone-else"}
    q = begin(client, fake)
    assert "error=provider" in finish(client, "google", q["state"][0]).headers["location"]
    fake.claims = {"sub": "g-1", "email": "kid@example.com", "email_verified": True}
    q = begin(client, fake)
    fake.nonce = "not-the-one"
    assert "error=provider" in finish(client, "google", q["state"][0]).headers["location"]
    assert app.state.db.one("SELECT COUNT(*) n FROM users")["n"] == 0


def test_user_cancelling_at_the_provider(env):
    _, client, fake = env
    q = begin(client, fake)
    res = client.get("/api/auth/oauth/google/callback", params={"state": q["state"][0], "error": "access_denied"})
    assert "#/login?error=cancelled" in res.headers["location"]


def test_apple_form_post_with_name_on_first_sign_in(env):
    app, client, fake = env
    fake.claims = {"sub": "a-1", "email": "abc123@privaterelay.appleid.com", "email_verified": "true"}
    q = begin(client, fake, "apple")
    assert q["response_mode"] == ["form_post"] and q["scope"] == ["name email"] and "code_challenge" not in q
    res = client.post("/api/auth/oauth/apple/callback", headers={"Origin": "https://appleid.apple.com"},
                      data={"state": q["state"][0], "code": "xyz", "user": json.dumps({"name": {"firstName": "Duke", "lastName": "M"}})})
    assert res.status_code == 302 and res.headers["location"] == "http://testserver/#/add"
    me = client.get("/api/auth/me").json()["user"]
    assert me["display_name"] == "Duke M" and me["email"] == "abc123@privaterelay.appleid.com"
    # Apple gets a signed client secret, not a fixed one.
    secret = fake.calls[-1][1]["client_secret"]
    header = json.loads(base64.urlsafe_b64decode(secret.split(".")[0] + "=="))
    assert header["alg"] == "ES256" and header["kid"] == "KEY123"


def test_other_cross_site_posts_are_still_blocked(env):
    _, client, _ = env
    res = client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_connect_and_disconnect_from_the_profile(env):
    app, client, fake = env
    client.post("/api/auth/register", json={"email": "kid@example.com", "password": "correct horse", "display_name": "Kid"})
    fake.claims = {"sub": "g-9", "email": "different@gmail.com", "email_verified": True}
    q = begin(client, fake, link=True)
    res = finish(client, "google", q["state"][0])
    assert res.headers["location"] == "http://testserver/#/profile?linked=google"
    assert client.get("/api/auth/me").json()["user"]["identities"] == [{"provider": "google", "email": "different@gmail.com"}]
    assert client.post("/api/auth/identities/google/disconnect").json() == {"ok": True}
    assert client.get("/api/auth/me").json()["user"]["identities"] == []


def test_cannot_connect_a_google_account_used_by_someone_else(env):
    app, client, fake = env
    google_sign_in(client, fake)  # g-1 belongs to kid@example.com now
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "other@example.com", "password": "correct horse", "display_name": "Other"})
    fake.claims = {"sub": "g-1", "email": "kid@example.com", "email_verified": True}
    q = begin(client, fake, link=True)
    assert "#/profile?error=taken" in finish(client, "google", q["state"][0]).headers["location"]


def test_password_less_account_can_set_a_password_and_needs_one_before_disconnecting(env):
    app, client, fake = env
    google_sign_in(client, fake)
    res = client.post("/api/auth/identities/google/disconnect")
    assert res.status_code == 400 and "Set a password first" in res.json()["detail"]
    assert client.post("/api/auth/password", json={"current": "", "new": "brand new pw"}).status_code == 200
    assert client.get("/api/auth/me").json()["user"]["has_password"] is True
    assert client.post("/api/auth/identities/google/disconnect").status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": "brand new pw"}).status_code == 200


def test_password_less_account_deletes_by_typing_its_email(env):
    app, client, fake = env
    google_sign_in(client, fake)
    assert client.post("/api/auth/delete", json={"password": "wrong@example.com"}).status_code == 403
    assert client.post("/api/auth/delete", json={"password": "Kid@Example.com"}).status_code == 200
    assert app.state.db.one("SELECT COUNT(*) n FROM user_identities")["n"] == 0


def test_closed_sign_ups_still_let_existing_accounts_in(tmp_path, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(oauth, "post_form", fake)
    app = create_app(Settings(data_dir=tmp_path, mail_backend="memory", public_url="http://testserver", allow_signup=False,
                              google_client_id="g-client", google_client_secret="g-secret"), engine_factory=lambda: None)
    with TestClient(app, follow_redirects=False) as client:
        assert "error=closed" in google_sign_in(client, fake).headers["location"]

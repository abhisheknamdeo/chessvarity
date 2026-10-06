"""Email verification, forgot password and feedback, with emails captured in memory."""

import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings
from chesscoach.db import Database

PW = "correct horse"


def make_client(tmp_path, **settings):
    base = dict(data_dir=tmp_path, mail_backend="memory", verify_email=True,
                public_url="https://dukesmate.test", feedback_to="owner@dukesmate.test")
    app = create_app(Settings(**{**base, **settings}), engine_factory=lambda: None)
    return app, TestClient(app)


@pytest.fixture()
def app_client(tmp_path):
    app, client = make_client(tmp_path)
    with client:
        yield app, client


def outbox(app):
    return app.state.mailer.outbox


def token_from(message, page):
    match = re.search(rf"https://dukesmate\.test/#/{page}\?token=([\w-]+)", message.text)
    assert match, message.text
    return match.group(1)


def register(client, email="kid@example.com", name="Duke"):
    return client.post("/api/auth/register", json={"email": email, "password": PW, "display_name": name})


def test_signup_needs_email_confirmation_before_sign_in(app_client):
    app, client = app_client
    res = register(client)
    assert res.status_code == 200 and res.json() == {"verification_required": True, "email": "kid@example.com"}
    assert client.get("/api/auth/me").status_code == 401  # no session yet
    mail = outbox(app)[-1]
    assert mail.to == "kid@example.com" and "Confirm your email" in mail.subject

    blocked = client.post("/api/auth/login", json={"email": "kid@example.com", "password": PW})
    assert blocked.status_code == 403 and "confirm your email" in blocked.json()["detail"]
    # A wrong password still gets the ordinary answer, so the 403 never reveals an account.
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": "nope nope"}).status_code == 401

    token = token_from(mail, "verify")
    done = client.post("/api/auth/verify", json={"token": token})
    assert done.status_code == 200 and done.json()["user"]["email_verified"] is True
    assert client.get("/api/auth/me").json()["user"]["email_verified"] is True  # the link signed them in
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 400  # works only once
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": PW}).status_code == 200


def test_resend_cancels_the_old_link_and_answers_the_same_for_unknown_addresses(app_client):
    app, client = app_client
    register(client)
    first = token_from(outbox(app)[-1], "verify")
    same = client.post("/api/auth/resend-verification", json={"email": "kid@example.com"}).json()
    unknown = client.post("/api/auth/resend-verification", json={"email": "nobody@example.com"}).json()
    assert same == unknown
    assert len(outbox(app)) == 2  # nothing sent to the unknown address
    second = token_from(outbox(app)[-1], "verify")
    assert client.post("/api/auth/verify", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify", json={"token": second}).status_code == 200


def test_expired_verification_link_is_refused(app_client):
    app, client = app_client
    register(client)
    token = token_from(outbox(app)[-1], "verify")
    app.state.db.run("UPDATE email_tokens SET expires_at = 0")
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 400


def test_forgot_and_reset_password(app_client):
    app, client = app_client
    register(client)
    client.post("/api/auth/verify", json={"token": token_from(outbox(app)[-1], "verify")})
    other = TestClient(app)
    other.post("/api/auth/login", json={"email": "kid@example.com", "password": PW})
    assert other.get("/api/auth/me").status_code == 200

    known = client.post("/api/auth/forgot", json={"email": "Kid@Example.com "}).json()
    unknown = client.post("/api/auth/forgot", json={"email": "nobody@example.com"}).json()
    assert known == unknown  # never reveals whether an account exists
    mail = outbox(app)[-1]
    assert mail.to == "kid@example.com" and "Reset your" in mail.subject
    token = token_from(mail, "reset")

    short = client.post("/api/auth/reset", json={"token": token, "password": "short"})
    assert short.status_code == 400
    ok = client.post("/api/auth/reset", json={"token": token, "password": "a brand new one"})
    assert ok.status_code == 200
    assert client.post("/api/auth/reset", json={"token": token, "password": "another new one"}).status_code == 400
    assert other.get("/api/auth/me").status_code == 401  # every session signed out
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": PW}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": "a brand new one"}).status_code == 200


def test_reset_link_also_confirms_the_email(app_client):
    app, client = app_client
    register(client)
    client.post("/api/auth/forgot", json={"email": "kid@example.com"})
    client.post("/api/auth/reset", json={"token": token_from(outbox(app)[-1], "reset"), "password": "a brand new one"})
    assert client.post("/api/auth/login", json={"email": "kid@example.com", "password": "a brand new one"}).status_code == 200


def test_email_forms_are_rate_limited(app_client):
    app, client = app_client
    register(client)
    before = len(outbox(app))
    for _ in range(10):
        client.post("/api/auth/forgot", json={"email": "kid@example.com"})
    assert len(outbox(app)) - before <= 5


def test_changing_email_needs_confirming_the_new_address(app_client):
    app, client = app_client
    register(client)
    client.post("/api/auth/verify", json={"token": token_from(outbox(app)[-1], "verify")})
    res = client.patch("/api/auth/me", json={"display_name": "Duke", "email": "new@example.com"})
    assert res.status_code == 200 and res.json()["verification_sent"] is True
    assert outbox(app)[-1].to == "new@example.com"
    assert client.get("/api/auth/me").status_code == 401


def test_feedback_is_saved_and_emailed_to_the_owner(app_client):
    app, client = app_client
    register(client, name="Duke\nBcc: x")
    client.post("/api/auth/verify", json={"token": token_from(outbox(app)[-1], "verify")})
    res = client.post("/api/feedback", json={"category": "problem", "message": "The board flips <b>oddly</b>.", "page": "#/play"})
    assert res.status_code == 200
    row = app.state.db.one("SELECT * FROM feedback WHERE id = ?", (res.json()["id"],))
    assert row["category"] == "problem" and row["message"] == "The board flips <b>oddly</b>." and row["page"] == "#/play"
    assert row["email"] == "kid@example.com"
    mail = outbox(app)[-1]
    assert mail.to == "owner@dukesmate.test" and mail.reply_to == "kid@example.com"
    assert "\n" not in mail.subject and "Problem" in mail.subject
    assert "The board flips <b>oddly</b>." in mail.text


def test_feedback_needs_sign_in_and_a_message(app_client):
    app, client = app_client
    assert client.post("/api/feedback", json={"message": "hi"}).status_code == 401
    register(client)
    client.post("/api/auth/verify", json={"token": token_from(outbox(app)[-1], "verify")})
    assert client.post("/api/feedback", json={"message": "   "}).status_code == 400
    assert client.post("/api/feedback", json={"message": "x", "category": "spam"}).status_code == 422


def test_feedback_without_an_owner_address_is_only_saved(tmp_path):
    app, client = make_client(tmp_path, verify_email=False, feedback_to="")
    with client:
        register(client)
        assert client.post("/api/feedback", json={"message": "Nice app"}).status_code == 200
        assert outbox(app) == []
        assert app.state.db.one("SELECT COUNT(*) n FROM feedback")["n"] == 1


def test_without_verification_sign_up_signs_in_straight_away(tmp_path):
    app, client = make_client(tmp_path, verify_email=False)
    with client:
        assert register(client).json()["user"]["email"] == "kid@example.com"
        assert client.get("/api/auth/me").status_code == 200
        assert outbox(app) == []


def test_real_email_needs_a_public_url(tmp_path):
    with pytest.raises(RuntimeError, match="CHESSCOACH_PUBLIC_URL"):
        create_app(Settings(data_dir=tmp_path, mail_backend="ses", public_url=""), engine_factory=lambda: None)


def test_accounts_from_before_verification_count_as_verified(tmp_path):
    path = tmp_path / "chesscoach.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, "
                 "password_hash TEXT NOT NULL, created_at REAL NOT NULL)")
    conn.execute("INSERT INTO users VALUES (1, 'old@example.com', 'Old', 'x', 1000.0)")
    conn.commit(); conn.close()
    db = Database(path)  # opening it upgrades it in place
    assert db.one("SELECT email_verified_at FROM users WHERE id = 1")["email_verified_at"] == 1000.0

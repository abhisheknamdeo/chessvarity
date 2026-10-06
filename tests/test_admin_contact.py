"""The owner's admin dashboard and the public contact form."""

import re

import pytest
from fastapi.testclient import TestClient

from chesscoach.api import create_app
from chesscoach.config import Settings

PW = "correct horse"
ADMIN = "owner@dukesmate.test"


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mail_backend="memory", verify_email=False,
                              public_url="https://dukesmate.test", feedback_to=ADMIN,
                              admin_emails=(ADMIN,), contact_email="hello@dukesmate.test"),
                     engine_factory=lambda: None)
    with TestClient(app) as client:
        yield app, client


def sign_up(client, email, name="Someone"):
    client.cookies.clear()
    res = client.post("/api/auth/register", json={"email": email, "password": PW, "display_name": name})
    assert res.status_code == 200, res.text


def confirm_own_email(app, client):
    res = client.post("/api/auth/send-verification")
    assert res.status_code == 200, res.text
    token = re.search(r"#/verify\?token=([\w-]+)", app.state.mailer.outbox[-1].text).group(1)
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 200


def test_admin_needs_the_listed_email_and_a_confirmed_address(app_client):
    app, client = app_client
    sign_up(client, "kid@example.com")
    assert client.get("/api/admin/stats").status_code == 404
    assert client.get("/api/auth/me").json()["user"]["is_admin"] is False

    sign_up(client, ADMIN, name="Owner")
    # Signed up with the admin address but not confirmed yet: anyone could do that, so no access.
    assert client.get("/api/admin/stats").status_code == 404
    assert client.get("/api/auth/me").json()["user"]["is_admin"] is False
    confirm_own_email(app, client)
    assert client.get("/api/auth/me").json()["user"]["is_admin"] is True
    assert client.get("/api/admin/stats").status_code == 200


def test_admin_stats_count_registrations(app_client):
    app, client = app_client
    sign_up(client, "a@example.com")
    sign_up(client, "b@example.com")
    confirm_own_email(app, client)
    app.state.db.run("UPDATE users SET created_at = created_at - 10 * 86400 WHERE email = 'a@example.com'")
    sign_up(client, ADMIN, name="Owner")
    confirm_own_email(app, client)
    client.post("/api/feedback", json={"message": "Love it", "category": "praise"})

    data = client.get("/api/admin/stats").json()
    t = data["totals"]
    assert (t["accounts"], t["confirmed"], t["today"], t["last_7_days"], t["last_30_days"]) == (3, 2, 2, 2, 3)
    assert t["active_7_days"] == 3  # everyone signed in this week (sign-up starts a session)
    assert t["messages"] == {"praise": 1}
    assert len(data["per_day"]) == 30 and data["per_day"][-1]["n"] == 2 and sum(d["n"] for d in data["per_day"]) == 3
    assert [a["email"] for a in data["accounts"]] == [ADMIN, "b@example.com", "a@example.com"]
    assert data["messages"][0]["message"] == "Love it"


def test_contact_form_works_signed_out_and_emails_the_owner(app_client):
    app, client = app_client
    assert client.get("/api/contact").json() == {"email": "hello@dukesmate.test"}
    res = client.post("/api/contact", json={"name": "A  Parent", "email": "Parent@Example.com", "message": "Hello there"})
    assert res.status_code == 200 and res.json()["ok"] is True
    row = app.state.db.one("SELECT * FROM feedback ORDER BY id DESC")
    assert (row["category"], row["name"], row["email"], row["user_id"]) == ("contact", "A Parent", "parent@example.com", None)
    mail = app.state.mailer.outbox[-1]
    assert mail.to == ADMIN and mail.reply_to == "parent@example.com" and "contact" in mail.subject


def test_contact_form_links_a_signed_in_account(app_client):
    app, client = app_client
    sign_up(client, "kid@example.com")
    client.post("/api/contact", json={"name": "Kid", "email": "kid@example.com", "message": "Hi"})
    row = app.state.db.one("SELECT * FROM feedback ORDER BY id DESC")
    assert row["user_id"] is not None and "account #" in app.state.mailer.outbox[-1].text


def test_contact_form_rejects_bad_input_bots_and_floods(app_client):
    app, client = app_client
    assert client.post("/api/contact", json={"name": "X", "email": "nope", "message": "Hi"}).status_code == 400
    bot = client.post("/api/contact", json={"name": "X", "email": "x@example.com", "message": "Buy", "website": "spam.example"})
    assert bot.status_code == 200 and app.state.db.one("SELECT COUNT(*) n FROM feedback")["n"] == 0
    codes = [client.post("/api/contact", json={"name": "X", "email": "x@example.com", "message": f"m{i}"}).status_code
             for i in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


def test_send_verification_for_an_already_confirmed_account(app_client):
    app, client = app_client
    sign_up(client, "kid@example.com")
    confirm_own_email(app, client)
    before = len(app.state.mailer.outbox)
    assert "already confirmed" in client.post("/api/auth/send-verification").json()["message"]
    assert len(app.state.mailer.outbox) == before

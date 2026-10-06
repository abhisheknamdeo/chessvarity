"""Feedback from signed-in users and the public contact form: saved in the database, and emailed to the owner."""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .deps import get_db, require_user
from .routes_account import EMAIL
from .security import COOKIE, user_for_session
from .mailer import Message
from .security import Throttle

router = APIRouter(prefix="/api")

CATEGORIES = {"idea": "Idea", "problem": "Problem", "praise": "Praise", "other": "Other"}


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    message: str = Field(min_length=1, max_length=4000)
    website: str = Field(default="", max_length=200)  # hidden from people; bots fill it in


class FeedbackIn(BaseModel):
    category: Literal["idea", "problem", "praise", "other"] = "idea"
    message: str = Field(min_length=1, max_length=4000)
    page: str = Field(default="", max_length=200)


@router.post("/feedback")
def send_feedback(body: FeedbackIn, request: Request) -> dict:
    user = require_user(request)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Please write a few words first.")
    throttle: Throttle = request.app.state.feedback_throttle
    if throttle.blocked(str(user["id"])):
        raise HTTPException(429, "Thanks for all the feedback! Please try again in a little while.")
    throttle.fail(str(user["id"]))
    agent = request.headers.get("user-agent", "")[:300]
    page = body.page.strip()[:200]
    now = time.time()
    feedback_id = get_db(request).run(
        "INSERT INTO feedback(user_id, email, name, category, message, page, user_agent, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user["id"], user["email"], user["display_name"], body.category, message, page, agent, now),
    )
    owner = request.app.state.settings.feedback_to
    if owner:
        label = CATEGORIES[body.category]
        # Names come from users: keep them on one line so they cannot add lines to the subject.
        name = " ".join(user["display_name"].split())
        request.app.state.mailer.send(Message(owner, f"Chess Varsity feedback #{feedback_id}: {label} from {name}", (
            f"{label} from {name} <{user['email']}> (account #{user['id']})\n"
            f"Page: {page or '(not given)'}\n"
            f"Sent: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}\n\n"
            f"{message}\n\n"
            "Reply to this email to answer them directly."), reply_to=user["email"]))
    return {"ok": True, "id": feedback_id}


@router.get("/contact")
def contact_info(request: Request) -> dict:
    return {"email": request.app.state.settings.contact_email}


@router.post("/contact")
def contact(body: ContactIn, request: Request) -> dict:
    """The public contact form: anyone may write, signed in or not, a few times an hour."""
    answer = {"ok": True, "message": "Thanks! Your message was sent. We'll reply by email."}
    if body.website.strip():
        return answer  # a bot: pretend it worked
    email, name, message = body.email.strip().lower(), " ".join(body.name.split()), body.message.strip()
    if not EMAIL.match(email):
        raise HTTPException(400, "That email address doesn't look right, and we need it to reply.")
    if not name or not message:
        raise HTTPException(400, "Please fill in your name and a message.")
    throttle: Throttle = request.app.state.contact_throttle
    ip = request.client.host if request.client else "?"
    if throttle.blocked(ip):
        raise HTTPException(429, "Thanks for writing! Please try again in a little while.")
    throttle.fail(ip)
    user = user_for_session(get_db(request), request.cookies.get(COOKIE))
    now = time.time()
    message_id = get_db(request).run(
        "INSERT INTO feedback(user_id, email, name, category, message, page, user_agent, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user["id"] if user else None, email, name, "contact", message, "contact form",
         request.headers.get("user-agent", "")[:300], now),
    )
    owner = request.app.state.settings.feedback_to
    if owner:
        who = f"account #{user['id']} ({user['email']})" if user else "not signed in"
        request.app.state.mailer.send(Message(owner, f"Chess Varsity contact #{message_id} from {name}", (
            f"From: {name} <{email}> ({who})\n"
            f"Sent: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}\n\n"
            f"{message}\n\n"
            "Reply to this email to answer them directly."), reply_to=email))
    return answer

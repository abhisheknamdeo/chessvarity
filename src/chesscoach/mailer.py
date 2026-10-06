"""Outgoing email: verification links, password resets and feedback notices.

Backends (CHESSCOACH_MAIL_BACKEND):
  log     write each message to the log instead of sending it (the default; fine for running locally)
  ses     send with Amazon SES, using the machine's AWS credentials (on EC2, its IAM role)
  memory  keep messages in `outbox` (tests)

Messages go out on a background thread, so a slow mail service never slows a request, and the time a
request takes does not reveal whether an email was sent (which would tell a stranger an account exists).
"""

from __future__ import annotations

import html
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

log = logging.getLogger("chesscoach.mail")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    reply_to: str | None = None


class Mailer:
    def __init__(self, backend: str = "log", sender: str = "Chess Varsity <no-reply@localhost>",
                 region: str | None = None):
        if backend not in ("log", "ses", "memory"):
            raise ValueError(f"Unknown mail backend {backend!r}; use log, ses or memory.")
        self.backend, self.sender, self.region = backend, sender, region
        self.outbox: list[Message] = []
        self._pool = None if backend == "memory" else ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail")
        self._ses = None

    def send(self, message: Message) -> None:
        if self._pool is None:
            self.outbox.append(message)
        else:
            self._pool.submit(self._deliver, message)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True)

    def _deliver(self, message: Message) -> None:
        try:
            if self.backend == "log":
                log.warning("Email (not sent; CHESSCOACH_MAIL_BACKEND=log)\nTo: %s\nSubject: %s\n\n%s",
                            message.to, message.subject, message.text)
                return
            if self._ses is None:
                import boto3
                self._ses = boto3.client("sesv2", region_name=self.region)
            self._ses.send_email(
                FromEmailAddress=self.sender,
                Destination={"ToAddresses": [message.to]},
                ReplyToAddresses=[message.reply_to] if message.reply_to else [],
                Content={"Simple": {
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": message.text, "Charset": "UTF-8"},
                             "Html": {"Data": as_html(message.text), "Charset": "UTF-8"}},
                }},
            )
            log.info("Email sent to %s: %s", message.to, message.subject)
        except Exception:  # a failed email must never take the app down; the user can ask again
            log.exception("Could not send email to %s (%s)", message.to, message.subject)


def as_html(text: str) -> str:
    """The plain-text body as simple HTML: escaped, with links clickable and paragraphs kept."""
    paragraphs = []
    for block in text.strip().split("\n\n"):
        lines = []
        for line in block.split("\n"):
            safe = html.escape(line)
            if line.startswith(("https://", "http://")) and " " not in line:
                safe = f'<a href="{safe}">{safe}</a>'
            lines.append(safe)
        paragraphs.append("<p>" + "<br>".join(lines) + "</p>")
    return ('<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;font-size:15px;'
            'line-height:1.5;color:#1b2333;max-width:560px">' + "".join(paragraphs) + "</div>")

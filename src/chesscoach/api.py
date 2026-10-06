"""Application factory.

Run with:  uv run chesscoach-serve            (or)   uvicorn chesscoach.api:create_app --factory
"""

from __future__ import annotations

import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import routes_account, routes_admin, routes_community, routes_events, routes_feedback, routes_links, routes_oauth, routes_roadmap, routes_scoresheets, routes_games, routes_insights, routes_library, routes_plan, routes_play, routes_training
from .config import Settings
from .db import PostgresDatabase, open_database
from .engine import Engine
from .mailer import Mailer
from .storage import make_storage
from .play import PlayEngine, opening_book
from .uscf import UscfClient
from .security import Throttle
from .worker import AnalysisWorker

STATIC_DIR = Path(__file__).parent / "static"

# Windows can map .js to text/plain through its registry, which browsers refuse for ES modules.
for _ext, _type in ((".js", "text/javascript"), (".css", "text/css"), (".svg", "image/svg+xml"), (".woff2", "font/woff2")):
    mimetypes.add_type(_type, _ext)


def create_app(
    settings: Settings | None = None,
    *,
    engine_factory: Callable[[], Engine] | None = None,
    close_engine: bool = True,
    uscf_factory: Callable[[], UscfClient] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if settings.mail_backend == "ses" and not settings.public_url:
        # Links in emails must not be built from the request's Host header, which a stranger can set.
        raise RuntimeError("Set CHESSCOACH_PUBLIC_URL (e.g. https://chessvarsity.com) when sending real email.")
    mailer = Mailer(settings.mail_backend, settings.mail_from, settings.mail_region)
    db = open_database(settings.data_dir, settings.database_url)
    factory = engine_factory or (lambda: Engine(settings.stockfish_path, depth=settings.depth, threads=settings.threads))
    worker = AnalysisWorker(db, factory, close_engine=close_engine)

    play = PlayEngine(settings.stockfish_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker.start()
        # Build the computer's opening book now, so the first game against it doesn't wait for it.
        threading.Thread(target=opening_book, name="opening-book", daemon=True).start()
        yield
        # Shutting down: an engine that has already stopped must not turn a clean exit into an error.
        for stop in (worker.stop, play.close):
            try:
                stop()
            except Exception as err:  # noqa: BLE001
                logging.getLogger("chesscoach").warning("while shutting down: %s", err)
        mailer.close()
        if isinstance(db, PostgresDatabase):
            db.close()

    app = FastAPI(title="Chess Varsity", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = db
    app.state.worker = worker
    app.state.play = play
    app.state.uscf_factory = uscf_factory or UscfClient
    app.state.throttle = Throttle()
    app.state.signup_throttle = Throttle(limit=10, window=3600.0)  # accounts created per address per hour
    app.state.mailer = mailer
    app.state.storage = make_storage(settings.storage, settings.data_dir, settings.s3_bucket, settings.mail_region)
    app.state.community_throttle = Throttle(limit=20, window=3600.0)  # comments per account per hour
    app.state.mail_throttle = Throttle(limit=5, window=3600.0)  # emails per recipient and per sender per hour
    app.state.feedback_throttle = Throttle(limit=10, window=3600.0)  # feedback messages per account per hour
    app.state.contact_throttle = Throttle(limit=5, window=3600.0)  # contact-form messages per address per hour

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Defence in depth on top of SameSite cookies: a browser-sent Origin must match this host.
        # Apple posts its sign-in answer from appleid.apple.com; that endpoint checks its own one-time state instead.
        if request.method in ("POST", "PATCH", "PUT", "DELETE") and request.url.path != "/api/auth/oauth/apple/callback":
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            # Check back every time (a cheap 304 when unchanged), so a deploy shows up on the next reload
            # instead of browsers guessing how long to keep old scripts.
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    for module in (routes_account, routes_admin, routes_community, routes_events, routes_feedback, routes_links, routes_oauth, routes_roadmap, routes_scoresheets, routes_games, routes_insights, routes_library, routes_plan, routes_play, routes_training):
        app.include_router(module.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app

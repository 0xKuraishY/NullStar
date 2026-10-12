"""Application entrypoint: wiring, lifespan, scheduler, error handling."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .collector import pipeline
from .collector.known import TIER_LABELS
from .collector.seeds import seed_sources
from .config import settings
from .db import SessionLocal, init_db
from .deps import RedirectToLogin, redirect, render, templates
from .routers import admin, api, auth, feed, library
from .i18n import ago_words
from .readme import plain as plain_text
from .readme import render as render_readme
from .scoring import band, band_label
from .taxonomy import category_accent, category_label

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("nullstar")

scheduler: BackgroundScheduler | None = None


def _rolling_cycle() -> None:
    result = pipeline.run_rolling_cycle()
    if result.get("status") not in ("skipped",):
        log.info("rolling cycle: %s", result)


def _scheduled_run() -> None:
    log.info("full sweep starting")
    result = pipeline.run_collection(trigger="schedule")
    log.info("full sweep finished: %s", result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    init_db()
    db = SessionLocal()
    try:
        added = seed_sources(db)
        if added:
            log.info("seeded %s default discovery sources", added)

        # A run interrupted by a restart never reaches its own finally block, so
        # it would sit in "running" forever and make the admin view lie.
        from sqlalchemy import update

        from .models import CollectionRun

        orphaned = db.execute(
            update(CollectionRun)
            .where(CollectionRun.status == "running")
            .values(status="interrupted", finished_at=datetime.now(timezone.utc),
                    error="Interrupted by an application restart.")
        ).rowcount
        db.commit()
        if orphaned:
            log.info("marked %s interrupted collection run(s)", orphaned)
    finally:
        db.close()

    if settings.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone="UTC")
        if settings.rolling_enabled:
            scheduler.add_job(
                _rolling_cycle, "interval",
                seconds=max(20, settings.rolling_interval_seconds),
                id="rolling", max_instances=1, coalesce=True,
                next_run_time=datetime.now(timezone.utc),
            )
            log.info("rolling collector: %s sources every %ss",
                     settings.rolling_batch_size, settings.rolling_interval_seconds)
        # A periodic full sweep still runs, so a source that keeps erroring out
        # cannot silently fall out of the rotation forever.
        scheduler.add_job(
            _scheduled_run, "interval",
            minutes=max(30, settings.collect_interval_minutes * 4),
            id="sweep", max_instances=1, coalesce=True,
        )
        scheduler.start()
    else:
        log.info("scheduler disabled (SCHEDULER_ENABLED=false)")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Nullstar",
    description="Cybersecurity GitHub discovery radar",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router, tags=["auth"])
app.include_router(feed.router, tags=["feed"])
app.include_router(library.router, tags=["library"])
app.include_router(admin.router, tags=["admin"])
app.include_router(api.router, tags=["api"])
app.include_router(api.feeds, tags=["api"])


# template globals
# Anything a macro in templates/ needs must live here, not in a view's context:
# macros imported with {% from %} do not inherit the calling context.
templates.env.globals.update(
    app_name=settings.app_name,
    app_tagline=settings.app_tagline,
    category_label=category_label,
    category_accent=category_accent,
    tier_labels=TIER_LABELS,
    band=band,
    band_label=band_label,
)


def _ago(value) -> str:
    words = ago_words()
    if value is None:
        return words["never"]
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    secs = (datetime.now(timezone.utc) - value).total_seconds()
    if secs < 0:
        return words["future"]
    if secs < 60:
        return words["just now"]
    for cutoff, step, key in ((3600, 60, "m"), (86400, 3600, "h"),
                              (2592000, 86400, "d"), (31536000, 2592000, "mo")):
        if secs < cutoff:
            return words[key].format(n=int(secs // step))
    return words["y"].format(n=int(secs // 31536000))


def _compact(value) -> str:
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(value)


def _excerpt(value) -> str:
    """READMEs arrive as raw Markdown with embedded HTML. Showing that verbatim
    puts literal <div> tags in front of the reader; rendering it as HTML would
    hand an untrusted document the page. So it is sanitised into a safe subset."""
    from markupsafe import Markup

    return Markup(render_readme(value or ""))


templates.env.filters["excerpt"] = _excerpt
templates.env.filters["plain"] = plain_text
templates.env.filters["ago"] = _ago
templates.env.filters["compact"] = _compact


# errors
@app.exception_handler(RedirectToLogin)
async def _redirect_to_login(request: Request, exc: RedirectToLogin):
    from urllib.parse import quote

    from .routers.auth import safe_next

    return redirect(f"/login?next={quote(safe_next(exc.next_url or '/'), safe='/?=&')}")


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    user = None
    try:
        from .security import resolve_session

        db = SessionLocal()
        user, _ = resolve_session(db, request)
        db.close()
    except Exception:  # noqa: BLE001
        pass
    return render(request, "error.html", user=user, title=f"Error {exc.status_code}",
                  code=exc.status_code, message=exc.detail, status_code=exc.status_code)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "internal_server_error"}, status_code=500)
    return render(
        request, "error.html", user=None, title="Error 500", code=500,
        message="Something broke while rendering this page. The details are in the server log.",
        status_code=500,
    )


@app.get("/healthz", include_in_schema=False)
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/readyz", include_in_schema=False)
def readyz():
    from sqlalchemy import text

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ready", "version": __version__,
                             "collector_running": pipeline.is_running()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "error": str(exc)}, status_code=503)
    finally:
        db.close()


# Scripts, styles, fonts and images all come from this origin: nothing is
# fetched from a CDN, so the policy can forbid every other source outright.
# 'unsafe-inline' is granted to styles only, for the inline style attributes in
# the templates; scripts get no such exemption, which is what stops injected
# markup from executing even if something slipped past escaping.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "manifest-src 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault(
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=(), interest-cohort=()",
    )
    if settings.cookie_secure:
        # Only meaningful over TLS, and actively harmful to set otherwise.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

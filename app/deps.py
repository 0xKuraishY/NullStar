"""FastAPI dependencies and template rendering helpers."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import __version__
from .config import settings
from .db import get_db
from .models import ROLE_ADMIN, ROLE_ANALYST, User
from .i18n import LANGS, current_lang
from .i18n import pick as pick_lang
from .i18n import pick_theme, translator
from .security import csrf_ok, pop_flash, resolve_api_key, resolve_session

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class RedirectToLogin(Exception):
    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


def user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user, _ = resolve_session(db, request)
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user, _ = resolve_session(db, request)
    if user is None:
        raise RedirectToLogin(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
    return user


def require_analyst(user: User = Depends(current_user)) -> User:
    if not user.at_least(ROLE_ANALYST):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Analyst role required.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.at_least(ROLE_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required.")
    return user


def api_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    raw = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("x-api-key")
    user = resolve_api_key(db, raw)
    if user is None:
        user, _ = resolve_session(db, request)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Valid API key required.")
    return user


def verify_csrf(request: Request, csrf_token: str = Form("")) -> None:
    if not csrf_ok(request, csrf_token):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired form token. Reload the page.")


def _chrome(user: User | None, ctx: dict) -> dict:
    """Bits every page needs. A view that already loaded one of these passes
    it in and we skip the query."""
    wanted = {"last_run", "saved_views", "open_registration"} - set(ctx)
    if not wanted:
        return {}

    from .db import SessionLocal
    from .models import CollectionRun, SavedView
    from .store import get_setting

    db = SessionLocal()
    try:
        extra: dict = {}
        if "last_run" in wanted:
            extra["last_run"] = db.scalar(
                select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(1))
        if "saved_views" in wanted:
            extra["saved_views"] = db.scalars(
                select(SavedView).where(SavedView.user_id == user.id).order_by(SavedView.name)
            ).all() if user else []
        if "open_registration" in wanted:
            extra["open_registration"] = bool(get_setting(db, "auth").get("allow_open_registration"))
        return extra
    finally:
        db.close()


def render(request: Request, template: str, user: User | None = None, **ctx):
    status_code = ctx.pop("status_code", 200)
    ctx = {**_chrome(user, ctx), **ctx}
    lang = pick_lang(request, user)
    current_lang.set(lang)
    theme = pick_theme(request, user)
    context = {
        "request": request,
        "user": user,
        "lang": lang,
        "langs": LANGS,
        "theme": theme,
        "t": translator(lang),
        "settings": settings,
        "version": __version__,
        "flash": pop_flash(request),
        "csrf_token": request.cookies.get("nullstar_csrf", ""),
        **ctx,
    }
    response = templates.TemplateResponse(request, template, context, status_code=status_code)
    if pop_flash(request):
        response.delete_cookie("nullstar_flash", path="/")
    return response


def redirect(url: str, code: int = status.HTTP_303_SEE_OTHER) -> RedirectResponse:
    return RedirectResponse(url, status_code=code)

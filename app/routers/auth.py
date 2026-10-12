"""Authentication: bootstrap, login, invites, self-service account page."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user, optional_user, redirect, render, user_count, verify_csrf
from ..i18n import COOKIE as LANG_COOKIE
from ..i18n import THEME_COOKIE
from ..i18n import normalise as normalise_lang
from ..i18n import normalise_theme
from ..models import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    ApiKey,
    Invite,
    Session_,
    User,
    utcnow,
)
from ..security import (
    audit,
    mark_seen,
    login_throttle,
    signup_throttle,
    client_ip,
    close_session,
    flash,
    hash_password,
    mint_api_key,
    needs_rehash,
    open_session,
    password_problems,
    token_digest,
    verify_password,
)
from ..store import get_setting

router = APIRouter()

USERNAME_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")


def safe_next(target: str) -> str:
    """Keep a redirect inside the site.

    startswith("/") is not enough. A browser reads /\host and /<tab>host as
    protocol relative, so both leave the site while looking like paths.
    """
    candidate = (target or "").strip()
    if not candidate.startswith("/"):
        return "/"
    if candidate.startswith("//"):
        return "/"
    if len(candidate) > 1 and candidate[1] in "/\\":
        return "/"
    if "\\" in candidate or ":" in candidate.split("?", 1)[0]:
        return "/"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in candidate):
        return "/"
    return candidate[:500]


def _username_problems(username: str) -> list[str]:
    """Same rule for sign-up, first run and the admin form."""
    if not USERNAME_RE.match(username or ""):
        return ["Pick a name of 3 to 32 characters: lowercase letters, digits, "
                "dash or underscore, starting with a letter or digit."]
    return []


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=__import__("datetime").timezone.utc)


# First-run bootstrap: whoever gets here first owns the instance.
@router.get("/setup")
def setup_form(request: Request, db: Session = Depends(get_db)):
    if user_count(db) > 0:
        return redirect("/login")
    return render(request, "setup.html", title="Initial setup")


@router.post("/setup")
def setup_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if user_count(db) > 0:
        return redirect("/login")

    username = username.strip().lower()
    errors = _username_problems(username)
    if password != password_confirm:
        errors.append("The two passwords do not match.")
    errors += password_problems(password)

    if errors:
        return render(request, "setup.html", title="Initial setup", errors=errors,
                      form={"username": username})

    owner = User(
        username=username,
        email="",
        display_name=username,
        password_hash=hash_password(password),
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(owner)
    db.commit()
    audit(db, "instance.bootstrap", user=owner, target=owner.username, request=request)

    response = redirect("/")
    open_session(db, owner, request, response)
    mark_seen(response)
    flash(response, "ok", "Welcome, %s. You run this instance." % owner.username)
    return response


# login / logout
@router.get("/login")
def login_form(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if user_count(db) == 0:
        return redirect("/setup")
    return render(request, "login.html", title="Sign in", next_url=safe_next(next),
                  open_registration=bool(get_setting(db, "auth").get("allow_open_registration")))


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    blocked = login_throttle(request)
    if blocked:
        audit(db, "auth.throttled", target=username[:60], request=request)
        return render(request, "login.html", title="Sign in", next_url=next,
                      errors=[blocked], form={"username": username}, status_code=429)

    ident = username.strip().lower()
    user = db.scalar(select(User).where(User.username == ident))

    generic = "Invalid credentials."
    if user is None:
        # constant-ish work factor so a missing user is not obviously faster
        hash_password(password)
        audit(db, "auth.login_failed", target=ident, request=request, reason="unknown_user")
        return render(request, "login.html", title="Sign in", next_url=next,
                      errors=[generic], form={"username": username}, status_code=401)

    locked_until = _aware(user.locked_until)
    if locked_until and locked_until > utcnow():
        mins = int((locked_until - utcnow()).total_seconds() // 60) + 1
        return render(request, "login.html", title="Sign in", next_url=next,
                      errors=[f"Account temporarily locked. Try again in {mins} minute(s)."],
                      form={"username": username}, status_code=429)

    if not user.is_active:
        audit(db, "auth.login_failed", user=user, target=ident, request=request, reason="disabled")
        return render(request, "login.html", title="Sign in", next_url=next,
                      errors=["This account is disabled. Contact an administrator."],
                      form={"username": username}, status_code=403)

    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = utcnow() + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_attempts = 0
        db.commit()
        audit(db, "auth.login_failed", user=user, target=ident, request=request, reason="bad_password")
        return render(request, "login.html", title="Sign in", next_url=next,
                      errors=[generic], form={"username": username}, status_code=401)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()

    target = safe_next(next)
    response = redirect("/account/password" if user.must_change_password else target)
    open_session(db, user, request, response)
    mark_seen(response)
    audit(db, "auth.login", user=user, target=user.username, request=request)
    if user.must_change_password:
        flash(response, "warn", "You must set a new password before continuing.")
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user),
           _: None = Depends(verify_csrf)):
    response = redirect("/login")
    close_session(db, request, response)
    audit(db, "auth.logout", user=user, request=request)
    flash(response, "ok", "Signed out.")
    return response


# Invite redemption (the only way in once the instance is bootstrapped)
@router.get("/register")
def register_form(request: Request, code: str = "", db: Session = Depends(get_db)):
    if user_count(db) == 0:
        return redirect("/setup")
    auth_cfg = get_setting(db, "auth")
    if not code and not auth_cfg.get("allow_open_registration"):
        return render(request, "register.html", title="Create account", locked=True,
                      errors=["Registration is invite-only on this instance."], status_code=403)
    return render(request, "register.html", title="Create account", code=code,
                  open_registration=bool(auth_cfg.get("allow_open_registration")))


@router.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    code: str = Form(""),
    db: Session = Depends(get_db),
):
    if user_count(db) == 0:
        return redirect("/setup")

    blocked = signup_throttle(request)
    if blocked:
        return render(request, "register.html", title="Create account", code=code,
                      errors=[blocked], status_code=429)

    auth_cfg = get_setting(db, "auth")
    invite: Invite | None = None
    role = auth_cfg.get("default_role") or ROLE_VIEWER

    if code.strip():
        invite = db.scalar(select(Invite).where(Invite.code_hash == token_digest(code.strip())))
        problem = None
        if invite is None:
            problem = "This invite code is not valid."
        elif invite.revoked:
            problem = "This invite has been revoked."
        elif invite.used_at is not None:
            problem = "This invite has already been used."
        elif _aware(invite.expires_at) < utcnow():
            problem = "This invite has expired."
        if problem:
            return render(request, "register.html", title="Create account", code=code,
                          errors=[problem], status_code=403)
        role = invite.role
    elif not auth_cfg.get("allow_open_registration"):
        return render(request, "register.html", title="Create account", locked=True,
                      errors=["Registration is invite-only on this instance."], status_code=403)

    username = username.strip().lower()
    errors = _username_problems(username)
    if password != password_confirm:
        errors.append("The two passwords do not match.")
    errors += password_problems(password)
    if db.scalar(select(User).where(User.username == username)):
        errors.append("That name is taken.")

    if errors:
        return render(request, "register.html", title="Create account", code=code, errors=errors,
                      form={"username": username})

    user = User(
        username=username,
        email="",
        display_name=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        created_by_id=invite.created_by_id if invite else None,
    )
    db.add(user)
    db.flush()
    if invite:
        invite.used_at = utcnow()
        invite.used_by_id = user.id
    db.commit()
    audit(db, "user.registered", user=user, target=user.username, request=request,
          via="invite" if invite else "open")

    response = redirect("/")
    open_session(db, user, request, response)
    mark_seen(response)
    flash(response, "ok", "Account made. Welcome, %s." % user.username)
    return response


@router.post("/lang/{code}")
def set_language(
    code: str,
    request: Request,
    back: str = Form("/"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    """Store a language choice.

    Cookie first since most visitors have no account. Signed in, it also goes
    on the account so it follows you to another machine.
    """
    lang = normalise_lang(code)
    response = redirect(safe_next(back))
    response.set_cookie(
        LANG_COOKIE, lang,
        max_age=400 * 24 * 3600,
        httponly=False,          # harmless, and lets the page read it without a round trip
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    if user is not None:
        prefs = dict(user.prefs or {})
        prefs["lang"] = lang
        user.prefs = prefs
        db.commit()
    return response


@router.post("/theme/{code}")
def set_theme(
    code: str,
    request: Request,
    back: str = Form("/"),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    theme = normalise_theme(code)
    response = redirect(safe_next(back))
    response.set_cookie(
        THEME_COOKIE, theme,
        max_age=400 * 24 * 3600,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    if user is not None:
        prefs = dict(user.prefs or {})
        prefs["theme"] = theme
        user.prefs = prefs
        db.commit()
    return response


# Account self-service
@router.get("/account")
def account(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sessions = db.scalars(
        select(Session_).where(Session_.user_id == user.id, Session_.revoked.is_(False))
        .order_by(Session_.last_seen_at.desc()).limit(20)
    ).all()
    keys = db.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked.is_(False))
        .order_by(ApiKey.created_at.desc())
    ).all()
    return render(request, "account.html", user=user, title="Account",
                  sessions=sessions, api_keys=keys, current_ip=client_ip(request))


@router.get("/account/password")
def password_form(request: Request, user: User = Depends(current_user)):
    return render(request, "password.html", user=user, title="Change password")


@router.post("/account/password")
def password_submit(
    request: Request,
    current_password: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    errors: list[str] = []
    if not verify_password(current_password, user.password_hash):
        errors.append("Your current password is incorrect.")
    if password != password_confirm:
        errors.append("The two new passwords do not match.")
    errors += password_problems(password)
    if errors:
        return render(request, "password.html", user=user, title="Change password", errors=errors)

    user.password_hash = hash_password(password)
    user.must_change_password = False
    db.commit()
    # every other session of this user is now invalid
    for row in db.scalars(select(Session_).where(Session_.user_id == user.id, Session_.revoked.is_(False))):
        row.revoked = True
    db.commit()
    audit(db, "user.password_changed", user=user, target=user.username, request=request)

    response = redirect("/account")
    open_session(db, user, request, response)
    flash(response, "ok", "Password updated. Other sessions were signed out.")
    return response


@router.post("/account/sessions/{session_id}/revoke")
def revoke_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    row = db.get(Session_, session_id)
    if row and row.user_id == user.id:
        row.revoked = True
        db.commit()
        audit(db, "user.session_revoked", user=user, target=str(session_id), request=request)
    response = redirect("/account")
    flash(response, "ok", "Session revoked.")
    return response


@router.post("/account/keys")
def create_key(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    raw = mint_api_key(db, user, name.strip() or "api key")
    audit(db, "user.api_key_created", user=user, target=name, request=request)
    sessions = db.scalars(
        select(Session_).where(Session_.user_id == user.id, Session_.revoked.is_(False))
        .order_by(Session_.last_seen_at.desc()).limit(20)
    ).all()
    keys = db.scalars(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked.is_(False))
        .order_by(ApiKey.created_at.desc())
    ).all()
    return render(request, "account.html", user=user, title="Account", sessions=sessions,
                  api_keys=keys, new_key=raw, current_ip=client_ip(request))


@router.post("/account/keys/{key_id}/revoke")
def revoke_key(
    key_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    row = db.get(ApiKey, key_id)
    if row and row.user_id == user.id:
        row.revoked = True
        db.commit()
        audit(db, "user.api_key_revoked", user=user, target=row.name, request=request)
    response = redirect("/account")
    flash(response, "ok", "API key revoked.")
    return response

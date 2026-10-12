"""Password hashing, sessions, API keys, CSRF and flash cookies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import ApiKey, AuditLog, Session_, User, utcnow

SESSION_COOKIE = "nullstar_session"
SEEN_COOKIE = "nullstar_seen"
CSRF_COOKIE = "nullstar_csrf"
FLASH_COOKIE = "nullstar_flash"

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="nullstar.session.v1")
_flash_serializer = URLSafeTimedSerializer(settings.secret_key, salt="nullstar.flash.v1")


# passwords
def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


PASSWORD_RULES = (
    "at least 12 characters",
    "one uppercase letter",
    "one lowercase letter",
    "one digit",
)


def password_problems(raw: str) -> list[str]:
    problems: list[str] = []
    if len(raw) < 12:
        problems.append("Password must be at least 12 characters long.")
    if not any(c.islower() for c in raw):
        problems.append("Password must contain a lowercase letter.")
    if not any(c.isupper() for c in raw):
        problems.append("Password must contain an uppercase letter.")
    if not any(c.isdigit() for c in raw):
        problems.append("Password must contain a digit.")
    return problems


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# sessions
def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def open_session(db: Session, user: User, request: Request, response: Response) -> Session_:
    raw = secrets.token_urlsafe(40)
    row = Session_(
        user_id=user.id,
        token_hash=token_digest(raw),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:255],
    )
    db.add(row)
    user.last_login_at = utcnow()
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    response.set_cookie(
        SESSION_COOKIE,
        _serializer.dumps(raw),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    issue_csrf(response)
    return row


def close_session(db: Session, request: Request, response: Response) -> None:
    raw = _read_session_token(request)
    if raw:
        row = db.scalar(select(Session_).where(Session_.token_hash == token_digest(raw)))
        if row:
            row.revoked = True
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _read_session_token(request: Request) -> str | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    try:
        return _serializer.loads(cookie, max_age=settings.session_ttl_hours * 3600)
    except BadSignature:
        return None


def resolve_session(db: Session, request: Request) -> tuple[User, Session_] | tuple[None, None]:
    raw = _read_session_token(request)
    if not raw:
        return None, None
    row = db.scalar(select(Session_).where(Session_.token_hash == token_digest(raw)))
    if not row or row.revoked:
        return None, None
    if _aware(row.expires_at) < utcnow():
        return None, None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None, None
    if (utcnow() - _aware(row.last_seen_at)).total_seconds() > 300:
        row.last_seen_at = utcnow()
        db.commit()
    return user, row


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# CSRF  (double-submit cookie)
def issue_csrf(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return token


def csrf_ok(request: Request, submitted: str | None) -> bool:
    expected = request.cookies.get(CSRF_COOKIE)
    return bool(expected and submitted and hmac.compare_digest(expected, submitted))


# flash messages
def mark_seen(response: Response) -> None:
    """Remember that this browser has been here, whatever it chose to do."""
    response.set_cookie(
        SEEN_COOKIE, "1",
        max_age=400 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def has_been_here(request: Request) -> bool:
    return request.cookies.get(SEEN_COOKIE) == "1"


def flash(response: Response, kind: str, message: str) -> None:
    response.set_cookie(
        FLASH_COOKIE,
        _flash_serializer.dumps({"kind": kind, "message": message}),
        max_age=30,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def pop_flash(request: Request) -> dict | None:
    cookie = request.cookies.get(FLASH_COOKIE)
    if not cookie:
        return None
    try:
        return _flash_serializer.loads(cookie, max_age=60)
    except BadSignature:
        return None


# api keys
def mint_api_key(db: Session, user: User, name: str) -> str:
    raw = "nsk_" + secrets.token_urlsafe(32)
    db.add(ApiKey(user_id=user.id, name=name[:80], prefix=raw[:12], key_hash=token_digest(raw)))
    db.commit()
    return raw


def resolve_api_key(db: Session, raw: str | None) -> User | None:
    if not raw:
        return None
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == token_digest(raw.strip())))
    if not row or row.revoked:
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    row.last_used_at = utcnow()
    db.commit()
    return user


# throttling
# Account lockout only covers one name at a time. It does nothing about the
# reverse: one common password tried against a thousand names. Hence these.
_BUCKETS: dict[str, list[float]] = defaultdict(list)
_BUCKET_LOCK = threading.Lock()


def _hit(bucket: str, key: str, limit: int, window_seconds: int) -> int:
    """Record an attempt. Returns seconds to wait, 0 if allowed."""
    now = time.monotonic()
    slot = f"{bucket}:{key}"
    with _BUCKET_LOCK:
        if len(_BUCKETS) > 4096:          # cap what a hostile client can make us hold
            _BUCKETS.clear()
        stamps = [t for t in _BUCKETS[slot] if now - t < window_seconds]
        stamps.append(now)
        _BUCKETS[slot] = stamps
        if len(stamps) > limit:
            return int(window_seconds - (now - stamps[0])) + 1
    return 0


def login_throttle(request: Request) -> str:
    wait = _hit("login", client_ip(request), limit=20, window_seconds=300)
    if wait:
        return f"Too many sign-in attempts from this address. Try again in {wait} seconds."
    return ""


def signup_throttle(request: Request) -> str:
    wait = _hit("signup", client_ip(request), limit=5, window_seconds=3600)
    if wait:
        return f"Too many accounts made from this address. Try again in {wait // 60 + 1} minutes."
    return ""


def reset_throttles() -> None:
    """For tests. The counters are process wide and leak between cases."""
    with _BUCKET_LOCK:
        _BUCKETS.clear()


# audit
def audit(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    target: str = "",
    request: Request | None = None,
    **meta,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            actor=user.username if user else "system",
            action=action,
            target=target[:200],
            ip=client_ip(request) if request else "",
            meta=meta or {},
        )
    )
    db.commit()

"""Administration: users, invites, sources, scoring, runs, audit."""
from __future__ import annotations

import secrets
import threading
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..collector import pipeline
from ..collector.seeds import seed_sources
from ..config import settings
from ..db import get_db
from ..deps import redirect, render, require_admin
from ..models import (
    ROLES,
    ROLE_ADMIN,
    ApiKey,
    AuditLog,
    CollectionRun,
    Invite,
    Repository,
    Session_,
    Source,
    User,
    utcnow,
)
from ..scoring import DEFAULT_WEIGHTS
from ..security import audit, flash, hash_password, password_problems, token_digest
from ..store import get_setting, set_setting
from ..deps import verify_csrf

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


@router.get("")
def overview(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    now = utcnow()
    stats = {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
        "repos": db.scalar(select(func.count()).select_from(Repository)) or 0,
        "repos_7d": db.scalar(select(func.count()).select_from(Repository)
                              .where(Repository.discovered_at >= now - timedelta(days=7))) or 0,
        "sources": db.scalar(select(func.count()).select_from(Source)) or 0,
        "sources_on": db.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True))) or 0,
        "sessions": db.scalar(select(func.count()).select_from(Session_).where(Session_.revoked.is_(False))) or 0,
        "pending_invites": db.scalar(
            select(func.count()).select_from(Invite)
            .where(Invite.used_at.is_(None), Invite.revoked.is_(False))) or 0,
    }
    runs = db.scalars(select(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(6)).all()
    recent_audit = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(12)).all()
    github_cfg = get_setting(db, "github")
    token_set = bool(github_cfg.get("token_override") or settings.github_token)

    return render(request, "admin/overview.html", user=user, title="Administration",
                  stats=stats, runs=runs, recent_audit=recent_audit,
                  collector_running=pipeline.is_running(), token_set=token_set,
                  scheduler_on=settings.scheduler_enabled,
                  interval=settings.collect_interval_minutes)


# users
@router.get("/users")
def users_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.scalars(select(User).order_by(User.created_at)).all()
    sessions = {
        row[0]: row[1]
        for row in db.execute(
            select(Session_.user_id, func.count())
            .where(Session_.revoked.is_(False), Session_.expires_at > utcnow())
            .group_by(Session_.user_id)
        ).all()
    }
    return render(request, "admin/users.html", user=user, title="Users",
                  users=rows, roles=ROLES, sessions=sessions)


@router.post("/users")
def create_user(
    request: Request,
    username: str = Form(...),
    role: str = Form("viewer"),
    password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    _: None = Depends(verify_csrf),
):
    from .auth import _username_problems

    username = username.strip().lower()
    errors: list[str] = []
    if role not in ROLES:
        errors.append("Unknown role.")
    errors += _username_problems(username)
    if db.scalar(select(User).where(User.username == username)):
        errors.append("That name is taken.")

    generated = ""
    if not password.strip():
        generated = secrets.token_urlsafe(14) + "A1"
        password = generated
    else:
        errors += password_problems(password)

    if errors:
        rows = db.scalars(select(User).order_by(User.created_at)).all()
        return render(request, "admin/users.html", user=user, title="Users", users=rows,
                      roles=ROLES, sessions={}, errors=errors,
                      form={"username": username, "role": role})

    created = User(
        username=username, email="", display_name=username,
        password_hash=hash_password(password), role=role, is_active=True,
        must_change_password=True, created_by_id=user.id,
    )
    db.add(created)
    db.commit()
    audit(db, "admin.user_created", user=user, target=username, request=request, role=role)

    rows = db.scalars(select(User).order_by(User.created_at)).all()
    return render(request, "admin/users.html", user=user, title="Users", users=rows, roles=ROLES,
                  sessions={}, generated_for=username, generated_password=generated)


@router.post("/users/{user_id}/role")
def change_role(user_id: int, request: Request, role: str = Form(...),
                db: Session = Depends(get_db), user: User = Depends(require_admin),
                _: None = Depends(verify_csrf)):
    target = db.get(User, user_id)
    response = redirect("/admin/users")
    if target is None or role not in ROLES:
        flash(response, "error", "Unknown user or role.")
        return response
    if target.id == user.id and role != ROLE_ADMIN:
        flash(response, "error", "You cannot demote your own account.")
        return response
    if target.role == ROLE_ADMIN and role != ROLE_ADMIN and _admin_count(db) <= 1:
        flash(response, "error", "This is the last administrator - promote someone else first.")
        return response
    target.role = role
    db.commit()
    audit(db, "admin.role_changed", user=user, target=target.username, request=request, role=role)
    flash(response, "ok", f"{target.username} is now {role}.")
    return response


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    target = db.get(User, user_id)
    response = redirect("/admin/users")
    if target is None:
        flash(response, "error", "Unknown user.")
        return response
    if target.id == user.id:
        flash(response, "error", "You cannot disable your own account.")
        return response
    if target.is_active and target.role == ROLE_ADMIN and _admin_count(db) <= 1:
        flash(response, "error", "This is the last active administrator.")
        return response
    target.is_active = not target.is_active
    if not target.is_active:
        for row in db.scalars(select(Session_).where(Session_.user_id == target.id, Session_.revoked.is_(False))):
            row.revoked = True
    db.commit()
    audit(db, "admin.user_toggled", user=user, target=target.username, request=request,
          active=target.is_active)
    flash(response, "ok", f"{target.username} {'enabled' if target.is_active else 'disabled'}.")
    return response


@router.post("/users/{user_id}/reset")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    target = db.get(User, user_id)
    if target is None:
        response = redirect("/admin/users")
        flash(response, "error", "Unknown user.")
        return response
    generated = secrets.token_urlsafe(14) + "A1"
    target.password_hash = hash_password(generated)
    target.must_change_password = True
    target.failed_attempts = 0
    target.locked_until = None
    for row in db.scalars(select(Session_).where(Session_.user_id == target.id, Session_.revoked.is_(False))):
        row.revoked = True
    db.commit()
    audit(db, "admin.password_reset", user=user, target=target.username, request=request)

    rows = db.scalars(select(User).order_by(User.created_at)).all()
    return render(request, "admin/users.html", user=user, title="Users", users=rows, roles=ROLES,
                  sessions={}, generated_for=target.username, generated_password=generated)


@router.post("/users/{user_id}/delete")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    target = db.get(User, user_id)
    response = redirect("/admin/users")
    if target is None:
        flash(response, "error", "Unknown user.")
        return response
    if target.id == user.id:
        flash(response, "error", "You cannot delete your own account.")
        return response
    if target.role == ROLE_ADMIN and _admin_count(db) <= 1:
        flash(response, "error", "This is the last administrator.")
        return response
    name = target.username
    db.delete(target)
    db.commit()
    audit(db, "admin.user_deleted", user=user, target=name, request=request)
    flash(response, "ok", f"{name} deleted.")
    return response


def _admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == ROLE_ADMIN, User.is_active.is_(True))
    ) or 0


# invites
@router.get("/invites")
def invites_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.scalars(select(Invite).order_by(desc(Invite.created_at)).limit(100)).all()
    auth_cfg = get_setting(db, "auth")
    return render(request, "admin/invites.html", user=user, title="Invites",
                  invites=rows, roles=ROLES, auth_cfg=auth_cfg, now=utcnow())


@router.post("/invites")
def create_invite(request: Request, role: str = Form("viewer"), note: str = Form(""),
                  ttl_hours: int = Form(168), db: Session = Depends(get_db),
                  user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    if role not in ROLES:
        role = "viewer"
    code = "inv_" + secrets.token_urlsafe(24)
    invite = Invite(
        code_hash=token_digest(code), hint=code[-6:], role=role, note=note.strip()[:255],
        created_by_id=user.id, expires_at=utcnow() + timedelta(hours=max(1, min(ttl_hours, 8760))),
    )
    db.add(invite)
    db.commit()
    audit(db, "admin.invite_created", user=user, target=invite.hint, request=request, role=role)

    rows = db.scalars(select(Invite).order_by(desc(Invite.created_at)).limit(100)).all()
    link = str(request.base_url).rstrip("/") + f"/register?code={code}"
    return render(request, "admin/invites.html", user=user, title="Invites", invites=rows,
                  roles=ROLES, auth_cfg=get_setting(db, "auth"), now=utcnow(),
                  new_invite=code, new_invite_link=link)


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(invite_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    row = db.get(Invite, invite_id)
    if row:
        row.revoked = True
        db.commit()
        audit(db, "admin.invite_revoked", user=user, target=row.hint, request=request)
    response = redirect("/admin/invites")
    flash(response, "ok", "Invite revoked.")
    return response


@router.post("/invites/policy")
def invite_policy(request: Request, allow_open_registration: str = Form(""),
                  default_role: str = Form("viewer"), db: Session = Depends(get_db),
                  user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    cfg = get_setting(db, "auth")
    cfg["allow_open_registration"] = allow_open_registration in ("1", "on", "true")
    cfg["default_role"] = default_role if default_role in ROLES else "viewer"
    set_setting(db, "auth", cfg)
    audit(db, "admin.auth_policy_changed", user=user, request=request, **cfg)
    response = redirect("/admin/invites")
    flash(response, "ok", "Registration policy updated.")
    return response


# sources
@router.get("/sources")
def sources_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.scalars(select(Source).order_by(Source.kind, Source.value)).all()
    return render(request, "admin/sources.html", user=user, title="Sources", sources=rows,
                  collector_running=pipeline.is_running())


@router.post("/sources")
def create_source(request: Request, kind: str = Form(...), value: str = Form(...),
                  label: str = Form(""), weight: float = Form(1.0), max_pages: int = Form(1),
                  db: Session = Depends(get_db), user: User = Depends(require_admin),
                  _: None = Depends(verify_csrf)):
    response = redirect("/admin/sources")
    if kind not in ("search", "org", "starred", "user"):
        flash(response, "error", "Unknown source kind.")
        return response
    value = value.strip()
    if not value:
        flash(response, "error", "A value is required.")
        return response
    if db.scalar(select(Source).where(Source.kind == kind, Source.value == value)):
        flash(response, "error", "That source already exists.")
        return response
    db.add(Source(kind=kind, value=value[:400], label=label.strip()[:160] or f"{kind}: {value}",
                  weight=max(0.1, min(weight, 3.0)), max_pages=max(1, min(max_pages, 5))))
    db.commit()
    audit(db, "admin.source_created", user=user, target=f"{kind}:{value}", request=request)
    flash(response, "ok", "Source added.")
    return response


@router.post("/sources/{source_id}/toggle")
def toggle_source(source_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    row = db.get(Source, source_id)
    if row:
        row.enabled = not row.enabled
        db.commit()
        audit(db, "admin.source_toggled", user=user, target=row.value, request=request,
              enabled=row.enabled)
    return redirect("/admin/sources")


@router.post("/sources/{source_id}/delete")
def delete_source(source_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    row = db.get(Source, source_id)
    if row:
        db.delete(row)
        db.commit()
        audit(db, "admin.source_deleted", user=user, target=row.value, request=request)
    response = redirect("/admin/sources")
    flash(response, "ok", "Source deleted.")
    return response


@router.post("/sources/seed")
def reseed(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin),
           _: None = Depends(verify_csrf)):
    added = seed_sources(db)
    audit(db, "admin.sources_seeded", user=user, request=request, added=added)
    response = redirect("/admin/sources")
    flash(response, "ok" if added else "warn",
          f"{added} default sources inserted." if added else "Sources already present - nothing inserted.")
    return response


@router.post("/sources/run")
def run_now(request: Request, source_id: int = Form(0), db: Session = Depends(get_db),
            user: User = Depends(require_admin), _: None = Depends(verify_csrf)):
    response = redirect("/admin/runs")
    if pipeline.is_running():
        flash(response, "warn", "A collection run is already in progress.")
        return response
    ids = [source_id] if source_id else None
    threading.Thread(target=pipeline.run_collection, args=("manual", ids), daemon=True).start()
    audit(db, "admin.collection_triggered", user=user, request=request, source_id=source_id or "all")
    flash(response, "ok", "Collection started - refresh in a moment.")
    return response


# scoring / settings
@router.get("/scoring")
def scoring_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return render(request, "admin/scoring.html", user=user, title="Scoring",
                  weights=get_setting(db, "scoring_weights"), defaults=DEFAULT_WEIGHTS,
                  collector=get_setting(db, "collector"))


@router.post("/scoring")
async def scoring_submit(request: Request, db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    form = await request.form()
    from ..security import csrf_ok
    if not csrf_ok(request, form.get("csrf_token")):
        response = redirect("/admin/scoring")
        flash(response, "error", "Invalid form token. Reload the page.")
        return response

    weights = {}
    for key, default in DEFAULT_WEIGHTS.items():
        try:
            weights[key] = max(0.0, min(100.0, float(form.get(f"w_{key}", default))))
        except (TypeError, ValueError):
            weights[key] = default
    set_setting(db, "scoring_weights", weights)

    collector = get_setting(db, "collector")
    for key in ("lookback_days", "min_score_to_keep", "enrich_top_n", "enrich_min_score",
                "search_pages", "retention_days", "max_repo_age_days"):
        try:
            collector[key] = max(0, int(float(form.get(f"c_{key}", collector.get(key, 0)))))
        except (TypeError, ValueError):
            pass
    try:
        collector["owner_lookup_min_relevance"] = max(
            0.0, min(1.0, float(form.get("c_owner_lookup_min_relevance",
                                         collector.get("owner_lookup_min_relevance", 0.25))))
        )
    except (TypeError, ValueError):
        pass
    set_setting(db, "collector", collector)
    audit(db, "admin.scoring_changed", user=user, request=request)

    response = redirect("/admin/scoring")
    flash(response, "ok", "Scoring saved. It applies to the next collection run - "
                          "use Rescore to apply it to existing records.")
    return response


@router.post("/scoring/rescore")
def rescore(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin),
            _: None = Depends(verify_csrf)):
    from ..scoring import compute_score

    weights = get_setting(db, "scoring_weights")
    rows = db.scalars(select(Repository)).all()
    for repo in rows:
        payload = {
            "name": repo.name, "description": repo.description, "topics": repo.topics or [],
            "readme_excerpt": repo.readme_excerpt, "readme_length": repo.readme_length,
            "repo_created_at": repo.repo_created_at, "repo_pushed_at": repo.repo_pushed_at,
            "owner_tier": repo.owner_tier, "owner_followers": repo.owner_followers,
            "stars": repo.stars, "license": repo.license, "homepage": repo.homepage,
            "size_kb": repo.size_kb, "is_fork": repo.is_fork, "is_archived": repo.is_archived,
        }
        score, extra = compute_score(payload, weights)
        repo.score = score
        repo.score_breakdown = extra["breakdown"]
        repo.categories = extra["categories"]
        repo.signals = extra["signals"]
        repo.star_velocity = extra["star_velocity"]
    db.commit()
    audit(db, "admin.rescored", user=user, request=request, count=len(rows))
    response = redirect("/admin/scoring")
    flash(response, "ok", f"Rescored {len(rows)} repositories.")
    return response


@router.get("/settings")
def settings_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    github_cfg = get_setting(db, "github")
    return render(request, "admin/settings.html", user=user, title="Instance settings",
                  alerts=get_setting(db, "alerts"),
                  token_override_set=bool(github_cfg.get("token_override")),
                  env_token_set=bool(settings.github_token))


@router.post("/settings")
def settings_submit(request: Request, webhook_url: str = Form(""), min_score: int = Form(80),
                    alerts_enabled: str = Form(""), github_token: str = Form(""),
                    clear_token: str = Form(""),
                    db: Session = Depends(get_db), user: User = Depends(require_admin),
                    _: None = Depends(verify_csrf)):
    alerts = get_setting(db, "alerts")
    candidate = webhook_url.strip()[:600]
    if candidate and not candidate.lower().startswith(("http://", "https://")):
        response = redirect("/admin/settings")
        flash(response, "error", "The webhook must be an http or https URL.")
        return response
    alerts["webhook_url"] = candidate
    alerts["min_score"] = max(0, min(100, min_score))
    alerts["enabled"] = alerts_enabled in ("1", "on", "true")
    set_setting(db, "alerts", alerts)

    github_cfg = get_setting(db, "github")
    if clear_token in ("1", "on", "true"):
        github_cfg["token_override"] = ""
    elif github_token.strip():
        github_cfg["token_override"] = github_token.strip()
    set_setting(db, "github", github_cfg)

    audit(db, "admin.settings_changed", user=user, request=request,
          alerts_enabled=alerts["enabled"], token_changed=bool(github_token.strip() or clear_token))
    response = redirect("/admin/settings")
    flash(response, "ok", "Settings saved.")
    return response


# runs & audit
@router.get("/runs")
def runs_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.scalars(select(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(50)).all()
    return render(request, "admin/runs.html", user=user, title="Collection runs", runs=rows,
                  collector_running=pipeline.is_running())


@router.get("/audit")
def audit_list(request: Request, action: str = "", db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    stmt = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(300)
    if action:
        stmt = select(AuditLog).where(AuditLog.action == action).order_by(desc(AuditLog.created_at)).limit(300)
    rows = db.scalars(stmt).all()
    actions = [row[0] for row in db.execute(select(AuditLog.action).distinct()).all()]
    return render(request, "admin/audit.html", user=user, title="Audit log", entries=rows,
                  actions=sorted(actions), selected=action)

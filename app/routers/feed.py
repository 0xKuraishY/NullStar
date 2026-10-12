"""The discovery feed, repository detail, dashboard and user state."""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..collections import counts_for, list_for
from ..collector import pipeline
from ..collector.known import TIER_LABELS
from ..config import settings
from ..db import SessionLocal, get_db
from ..i18n import current_lang
from ..i18n import pick as pick_lang
from ..i18n import translator
from ..deps import current_user, optional_user, redirect, render, verify_csrf
from ..models import (
    Source,
    CollectionRun,
    Follow,
    RepoEvent,
    Repository,
    SavedView,
    User,
    UserRepoState,
    utcnow,
)
from ..queries import FeedFilters, facet_options, fetch_feed, user_states
from ..scoring import band, band_label
from ..security import audit, flash, has_been_here, mark_seen
from ..store import get_setting
from ..taxonomy import CATEGORIES, category_accent, category_label

router = APIRouter()


def ticker(db: Session) -> dict:
    """Counters for the header. Cheap enough to redo each request."""
    now = utcnow()
    return {
        "indexed": db.scalar(select(func.count()).select_from(Repository)) or 0,
        "today": db.scalar(select(func.count()).select_from(Repository)
                           .where(Repository.discovered_at >= now - timedelta(days=1))) or 0,
        "hour": db.scalar(select(func.count()).select_from(Repository)
                          .where(Repository.discovered_at >= now - timedelta(hours=1))) or 0,
        "gems": db.scalar(select(func.count()).select_from(Repository)
                          .where(Repository.score >= 80, Repository.stars <= 5)) or 0,
    }


def followed_logins(db: Session, user: User | None) -> set[str]:
    if user is None:
        return set()
    return {row[0].lower() for row in db.execute(
        select(Follow.login).where(Follow.user_id == user.id)).all()}


def _common(db: Session, user: User | None) -> dict:
    last_run = db.scalar(select(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(1))
    return {
        "followed": followed_logins(db, user),
        "facets": facet_options(db),
        "last_run": last_run,
        "ticker": ticker(db),
        "pulse": pipeline.pulse_state(),
        "category_label": category_label,
        "category_accent": category_accent,
        "band": band,
        "band_label": band_label,
        "tier_labels": TIER_LABELS,
        "collections": list_for(db, user),
        "collection_counts": counts_for(db, user.id) if user else {},
        "saved_views": db.scalars(
            select(SavedView).where(SavedView.user_id == user.id).order_by(SavedView.name)
        ).all() if user else [],
    }


@router.get("/")
def feed(request: Request, db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    # First time here: show the door before the room. Only the root does this,
    # so a link to a repository or a shared collection still opens on itself.
    if user is None and not has_been_here(request) and not request.query_params:
        return redirect("/login")

    filters = FeedFilters.from_query(request.query_params)
    rows, total = fetch_feed(db, filters, user.id if user else None)
    states = user_states(db, user.id if user else None, rows)

    pages = max(1, -(-total // filters.per_page))
    return render(
        request, "feed.html", user=user, title="Feed",
        repos=rows, states=states, filters=filters, total=total, pages=pages,
        **_common(db, user),
    )


@router.get("/guest")
def guest(request: Request):
    """Chosen to read without an account. Remember it and get out of the way."""
    response = redirect("/")
    mark_seen(response)
    return response


@router.get("/gems")
def gems(request: Request, db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    """Opinionated preset: the whole reason this tool exists."""
    params = dict(request.query_params)
    params.setdefault("signal", "hidden-gem")
    params.setdefault("sort", "underrated")
    params.setdefault("window", "30d")
    filters = FeedFilters.from_query(params)
    rows, total = fetch_feed(db, filters, user.id if user else None)
    states = user_states(db, user.id if user else None, rows)
    pages = max(1, -(-total // filters.per_page))
    return render(
        request, "feed.html", user=user, title="Overlooked",
        repos=rows, states=states, filters=filters, total=total, pages=pages,
        preset="overlooked",
        **_common(db, user),
    )


@router.get("/majors")
def majors(request: Request, db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    params = dict(request.query_params)
    params.setdefault("signal", "major-publisher")
    params.setdefault("sort", "new")
    filters = FeedFilters.from_query(params)
    rows, total = fetch_feed(db, filters, user.id if user else None)
    states = user_states(db, user.id if user else None, rows)
    pages = max(1, -(-total // filters.per_page))
    return render(
        request, "feed.html", user=user, title="Major publishers",
        repos=rows, states=states, filters=filters, total=total, pages=pages,
        preset="majors",
        **_common(db, user),
    )


@router.get("/newcomers")
def newcomers(request: Request, db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    params = dict(request.query_params)
    params.setdefault("tier", "newcomer")
    params.setdefault("sort", "new")
    filters = FeedFilters.from_query(params)
    rows, total = fetch_feed(db, filters, user.id if user else None)
    states = user_states(db, user.id if user else None, rows)
    pages = max(1, -(-total // filters.per_page))
    return render(
        request, "feed.html", user=user, title="New accounts",
        repos=rows, states=states, filters=filters, total=total, pages=pages,
        preset="newcomers",
        **_common(db, user),
    )


@router.get("/bookmarks")
def bookmarks(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    params = dict(request.query_params)
    params["bookmarked"] = "1"
    params.setdefault("window", "all")
    filters = FeedFilters.from_query(params)
    rows, total = fetch_feed(db, filters, user.id if user else None)
    states = user_states(db, user.id if user else None, rows)
    pages = max(1, -(-total // filters.per_page))
    return render(
        request, "feed.html", user=user, title="Saved",
        repos=rows, states=states, filters=filters, total=total, pages=pages,
        preset="saved",
        **_common(db, user),
    )


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db),
         user: User | None = Depends(optional_user)):
    now = utcnow()
    totals = {
        "all": db.scalar(select(func.count()).select_from(Repository)) or 0,
        "7d": db.scalar(select(func.count()).select_from(Repository)
                        .where(Repository.discovered_at >= now - timedelta(days=7))) or 0,
        "24h": db.scalar(select(func.count()).select_from(Repository)
                         .where(Repository.discovered_at >= now - timedelta(days=1))) or 0,
        "high": db.scalar(select(func.count()).select_from(Repository)
                          .where(Repository.score >= 65)) or 0,
    }

    daily_rows = db.execute(
        select(func.date(Repository.discovered_at), func.count())
        .where(Repository.discovered_at >= now - timedelta(days=30))
        .group_by(func.date(Repository.discovered_at))
    ).all()
    daily = {str(row[0]): row[1] for row in daily_rows}
    timeline = []
    for offset in range(29, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        timeline.append({"day": day, "count": daily.get(day, 0)})

    tier_rows = db.execute(
        select(Repository.owner_tier, func.count())
        .where(Repository.discovered_at >= now - timedelta(days=30))
        .group_by(Repository.owner_tier).order_by(desc(func.count()))
    ).all()

    lang_rows = db.execute(
        select(Repository.language, func.count())
        .where(Repository.discovered_at >= now - timedelta(days=30), Repository.language != "")
        .group_by(Repository.language).order_by(desc(func.count())).limit(12)
    ).all()

    recent = db.scalars(
        select(Repository).where(Repository.discovered_at >= now - timedelta(days=30))
        .order_by(desc(Repository.score)).limit(400)
    ).all()
    cat_counter: Counter = Counter()
    for repo in recent:
        for slug in (repo.categories or []):
            cat_counter[slug] += 1

    top = db.scalars(
        select(Repository).where(Repository.discovered_at >= now - timedelta(days=7))
        .order_by(desc(Repository.score)).limit(8)
    ).all()
    events = db.scalars(select(RepoEvent).order_by(desc(RepoEvent.created_at)).limit(10)).all()
    runs = db.scalars(select(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(8)).all()

    return render(
        request, "dashboard.html", user=user, title="Statistics",
        totals=totals, timeline=timeline, tiers=tier_rows, languages=lang_rows,
        categories=cat_counter.most_common(12), top=top, events=events, runs=runs,
        **_common(db, user),
    )


@router.get("/how")
def how_it_works(request: Request, db: Session = Depends(get_db),
                 user: User | None = Depends(optional_user)):
    """Everything behind a rank, read off the live configuration.

    Written from the settings the collector actually uses rather than from a
    copy, so the page cannot quietly drift away from what the code does.
    """
    from ..queries import SORTS, WINDOWS
    from ..scoring import DEFAULT_WEIGHTS, TIER_WEIGHT
    from ..taxonomy import CATEGORIES, LOW_EFFORT_PATTERNS, NOISE_PATTERNS

    weights = get_setting(db, "scoring_weights")
    collector = get_setting(db, "collector")
    sources = db.execute(
        select(Source.kind, func.count()).where(Source.enabled.is_(True))
        .group_by(Source.kind)).all()

    components = [
        ("relevance", "How certain we are that this is security work at all.",
         "Topics the author set, words in the name and description, and the readme. "
         "The readme counts for about a third of a description hit: a readme mentions "
         "plenty in passing, a description states intent."),
        ("freshness", "How recently the repository appeared.",
         "Two curves. Creation date halves every 21 days, last push halves every 10. "
         "Creation carries roughly two thirds of the weight."),
        ("origin", "Who published it.",
         "A curated list of organisations, plus account age and reach for everybody "
         "else. An account opened in the last four months is treated as new rather "
         "than unknown."),
        ("substance", "Signs that work went into it.",
         "Description length, readme depth, topics, a licence, a homepage, repository size."),
        ("momentum", "Stars per day since creation.",
         "Compressed on a log scale and capped low on purpose. Without that cap, "
         "popularity would decide everything and nothing new would ever surface."),
        ("gem_bonus", "A kicker for work nobody has seen.",
         "Applies when relevance is high, the repository is recent and it has five "
         "stars or fewer. Also applies to a brand new account publishing security code."),
        ("noise_penalty", "Subtracted, not added.",
         "Link collections, course material, forks, archived repositories, and "
         "entries with no description, no topics and no readme."),
    ]

    return render(
        request, "how.html", user=user, title="How ranking works",
        weights=weights, defaults=DEFAULT_WEIGHTS, components=components,
        tier_weight=TIER_WEIGHT,          # tier_labels already comes from _common
        categories=CATEGORIES, noise=NOISE_PATTERNS[:8], low_effort=LOW_EFFORT_PATTERNS[:6],
        sorts=SORTS, windows=list(WINDOWS), collector=collector,
        sources=dict(sources), total_weight=sum(
            v for k, v in weights.items() if k != "noise_penalty"),
        **_common(db, user),
    )


@router.get("/repo/{repo_id}")
def repo_detail(repo_id: int, request: Request, db: Session = Depends(get_db),
                user: User | None = Depends(optional_user)):
    repo = db.get(Repository, repo_id)
    if repo is None:
        return render(request, "error.html", user=user, title="Not found",
                      code=404, message="That repository is not in the index.", status_code=404)

    state = None
    if user is not None:
        state = db.scalar(
            select(UserRepoState)
            .where(UserRepoState.user_id == user.id, UserRepoState.repo_id == repo.id)
        )
        if state is None:
            state = UserRepoState(user_id=user.id, repo_id=repo.id, seen=True)
            db.add(state)
        else:
            state.seen = True
        db.commit()

    siblings = db.scalars(
        select(Repository).where(Repository.owner == repo.owner, Repository.id != repo.id)
        .order_by(desc(Repository.score)).limit(6)
    ).all()
    events = db.scalars(
        select(RepoEvent).where(RepoEvent.repo_id == repo.id)
        .order_by(desc(RepoEvent.created_at)).limit(20)
    ).all()

    from ..collections import membership

    return render(request, "repo.html", user=user, title=repo.full_name, repo=repo, state=state,
                  siblings=siblings, events=events, categories_meta=CATEGORIES,
                  filed_in=membership(db, user, repo.id), **_common(db, user))


# per-user state
def _state_for(db: Session, user: User, repo_id: int) -> UserRepoState:
    state = db.scalar(
        select(UserRepoState).where(UserRepoState.user_id == user.id, UserRepoState.repo_id == repo_id)
    )
    if state is None:
        state = UserRepoState(user_id=user.id, repo_id=repo_id)
        db.add(state)
        db.flush()
    return state


@router.post("/repo/{repo_id}/bookmark")
def toggle_bookmark(repo_id: int, request: Request, back: str = Form("/"),
                    db: Session = Depends(get_db), user: User = Depends(current_user),
                    _: None = Depends(verify_csrf)):
    state = _state_for(db, user, repo_id)
    state.bookmarked = not state.bookmarked
    db.commit()
    return redirect(back if back.startswith("/") else "/")


@router.post("/repo/{repo_id}/dismiss")
def dismiss(repo_id: int, request: Request, back: str = Form("/"),
            db: Session = Depends(get_db), user: User = Depends(current_user),
            _: None = Depends(verify_csrf)):
    state = _state_for(db, user, repo_id)
    state.dismissed = True
    state.seen = True
    db.commit()
    return redirect(back if back.startswith("/") else "/")


@router.post("/repo/{repo_id}/note")
def save_note(repo_id: int, request: Request, note: str = Form(""),
              db: Session = Depends(get_db), user: User = Depends(current_user),
              _: None = Depends(verify_csrf)):
    state = _state_for(db, user, repo_id)
    state.note = note[:4000]
    state.seen = True
    db.commit()
    response = redirect(f"/repo/{repo_id}")
    flash(response, "ok", "Note saved.")
    return response


@router.post("/views")
def save_view(request: Request, name: str = Form(...), query: str = Form(""),
              db: Session = Depends(get_db), user: User = Depends(current_user),
              _: None = Depends(verify_csrf)):
    db.add(SavedView(user_id=user.id, name=name.strip()[:80] or "View", query=query[:600]))
    db.commit()
    audit(db, "view.saved", user=user, target=name, request=request)
    response = redirect(f"/?{query}" if query else "/")
    flash(response, "ok", f"View '{name}' saved.")
    return response


@router.post("/views/{view_id}/delete")
def delete_view(view_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user), _: None = Depends(verify_csrf)):
    row = db.get(SavedView, view_id)
    if row and row.user_id == user.id:
        db.delete(row)
        db.commit()
    return redirect("/")


# Live wire (Server-Sent Events)
def _render_row(csrf_token: str, repo: Repository, state: UserRepoState | None = None,
                user: User | None = None, lang: str = "en") -> str:
    """Render one entry with the macro the page itself uses.

    Pushing rendered HTML instead of JSON avoids keeping a second copy of this
    markup in JavaScript, which would drift.
    """
    from ..deps import templates

    current_lang.set(lang)
    macro = templates.get_template("_entry.html").module.entry
    return str(macro(repo, state, csrf_token, "/", user, translator(lang)))


def _fetch_since(user_id: int | None, since) -> list[Repository]:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(Repository).where(Repository.discovered_at > since)
            .order_by(Repository.discovered_at.asc()).limit(25)
        ).all()
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


@router.get("/stream")
async def stream(request: Request, user: User | None = Depends(optional_user)):
    """One connection per open tab. It polls rather than piping a queue out of
    the collector thread, which is simpler and survives a restart."""
    since = utcnow()
    csrf = request.cookies.get("nullstar_csrf", "")
    lang = pick_lang(request, user)

    async def events():
        nonlocal since
        yield "retry: 5000\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                rows = await run_in_threadpool(_fetch_since, user.id if user else None, since)
                for repo in rows:
                    since = max(since, _aware(repo.discovered_at))
                    payload = {"id": repo.id, "html": _render_row(csrf, repo, None, user, lang),
                               "score": round(repo.score, 1), "name": repo.full_name}
                    yield f"event: repo\ndata: {json.dumps(payload)}\n\n"
                pulse = pipeline.pulse_state()
                pulse["seen"] = len(rows)
                yield f"event: pulse\ndata: {json.dumps(pulse)}\n\n"
            except Exception as exc:  # noqa: BLE001 - a stream must not 500 the page
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(max(2, settings.stream_poll_seconds))

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


def _aware(dt):
    from datetime import timezone as _tz

    return dt if dt.tzinfo else dt.replace(tzinfo=_tz.utc)

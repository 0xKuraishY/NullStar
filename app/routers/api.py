"""Read-only JSON API and Atom feed, authenticated by API key or session."""
from __future__ import annotations

from datetime import timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..collector.known import TIER_LABELS
from ..db import get_db
from ..deps import api_user
from ..models import Repository, User, utcnow
from ..queries import FeedFilters, fetch_feed
from ..scoring import band
from ..taxonomy import CATEGORIES, category_label

router = APIRouter(prefix="/api/v1")


def serialise(repo: Repository, *, full: bool = False) -> dict:
    data = {
        "id": repo.id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "name": repo.name,
        "url": repo.html_url,
        "description": repo.description,
        "language": repo.language,
        "topics": repo.topics or [],
        "license": repo.license,
        "stars": repo.stars,
        "forks": repo.forks,
        "star_velocity": round(repo.star_velocity or 0, 3),
        "score": round(repo.score, 1),
        "band": band(repo.score),
        "categories": repo.categories or [],
        "category_labels": [category_label(c) for c in (repo.categories or [])],
        "signals": repo.signals or [],
        "owner_tier": repo.owner_tier,
        "owner_tier_label": TIER_LABELS.get(repo.owner_tier, repo.owner_tier),
        "owner_followers": repo.owner_followers,
        "repo_created_at": _iso(repo.repo_created_at),
        "repo_pushed_at": _iso(repo.repo_pushed_at),
        "discovered_at": _iso(repo.discovered_at),
        "discovered_via": repo.discovered_via,
    }
    if full:
        data["score_breakdown"] = repo.score_breakdown
        data["readme_excerpt"] = repo.readme_excerpt
        data["homepage"] = repo.homepage
        data["is_fork"] = repo.is_fork
        data["is_archived"] = repo.is_archived
    return data


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


@router.get("/repos")
def list_repos(request: Request, db: Session = Depends(get_db), user: User = Depends(api_user)):
    filters = FeedFilters.from_query(request.query_params)
    rows, total = fetch_feed(db, filters, user.id)
    return JSONResponse({
        "total": total,
        "page": filters.page,
        "per_page": filters.per_page,
        "filters": {
            "q": filters.q, "category": filters.category, "tier": filters.tier,
            "language": filters.language, "signal": filters.signal,
            "window": filters.window, "sort": filters.sort,
            "min_score": filters.min_score, "max_stars": filters.max_stars,
        },
        "results": [serialise(r) for r in rows],
    })


@router.get("/repos/{repo_id}")
def get_repo(repo_id: int, db: Session = Depends(get_db), user: User = Depends(api_user)):
    repo = db.get(Repository, repo_id)
    if repo is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(serialise(repo, full=True))


@router.get("/taxonomy")
def taxonomy(user: User = Depends(api_user)):
    return JSONResponse({
        "categories": [
            {"slug": slug, "label": meta["label"], "accent": meta["accent"], "weight": meta["weight"]}
            for slug, meta in CATEGORIES.items()
        ],
        "tiers": [{"slug": slug, "label": label} for slug, label in TIER_LABELS.items()],
    })


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(api_user)):
    from sqlalchemy import func

    return JSONResponse({
        "repositories": db.scalar(select(func.count()).select_from(Repository)) or 0,
        "high_interest": db.scalar(
            select(func.count()).select_from(Repository).where(Repository.score >= 65)) or 0,
        "generated_at": utcnow().isoformat(),
    })


# Atom feed - point any RSS reader at it with ?key=<api key>
feeds = APIRouter()


@feeds.get("/feed.atom")
def atom(request: Request, db: Session = Depends(get_db), user: User = Depends(api_user)):
    filters = FeedFilters.from_query(request.query_params)
    filters.per_page = min(filters.per_page, 50)
    rows, _ = fetch_feed(db, filters, user.id)
    base = str(request.base_url).rstrip("/")
    updated = _iso(utcnow())

    entries = []
    for repo in rows:
        summary = (
            f"Score {repo.score:.0f} | {TIER_LABELS.get(repo.owner_tier, repo.owner_tier)} | "
            f"{repo.stars} stars | {', '.join(category_label(c) for c in (repo.categories or []))}\n\n"
            f"{repo.description or ''}"
        )
        entries.append(f"""  <entry>
    <title>{escape(repo.full_name)}</title>
    <link href="{escape(repo.html_url)}"/>
    <id>tag:nullstar,2026:repo/{repo.id}</id>
    <updated>{_iso(repo.discovered_at)}</updated>
    <author><name>{escape(repo.owner)}</name></author>
    <summary type="text">{escape(summary)}</summary>
  </entry>""")

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Nullstar - cybersecurity GitHub radar</title>
  <link href="{escape(base)}/"/>
  <link rel="self" href="{escape(str(request.url))}"/>
  <id>tag:nullstar,2026:feed</id>
  <updated>{updated}</updated>
{chr(10).join(entries)}
</feed>
"""
    return Response(body, media_type="application/atom+xml")


@feeds.get("/export.json")
def export_json(request: Request, db: Session = Depends(get_db), user: User = Depends(api_user)):
    filters = FeedFilters.from_query(request.query_params)
    filters.per_page = 500
    rows, total = fetch_feed(db, filters, user.id)
    return JSONResponse(
        {"exported_at": utcnow().isoformat(), "total": total,
         "results": [serialise(r, full=True) for r in rows]},
        headers={"Content-Disposition": 'attachment; filename="nullstar-export.json"'},
    )

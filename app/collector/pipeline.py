"""The collection pipeline: fetch -> normalise -> enrich -> score -> persist."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import CollectionRun, RepoEvent, Repository, Source, utcnow
from ..scoring import compute_score
from ..store import get_setting
from ..taxonomy import classify
from .github import BudgetExhausted, GitHubClient, RateLimited, normalise_repo
from .known import (
    TIER_INDIE,
    TIER_LABELS,
    TIER_NEWCOMER,
    TIER_UNKNOWN,
    tier_for_login,
)

log = logging.getLogger("nullstar.pipeline")

_run_lock = threading.Lock()
_state = {"running": False, "current_run_id": None, "last_pulse": None, "cycle": 0}

KEEP_RUNS = 400


def is_running() -> bool:
    return _state["running"]


def pulse_state() -> dict:
    """When the collector last did anything."""
    return {
        "running": _state["running"],
        "last_pulse": _state["last_pulse"].isoformat() if _state["last_pulse"] else None,
        "cycle": _state["cycle"],
    }


def run_rolling_cycle() -> dict:
    """Poll the few sources we have not looked at in the longest.

    Small batches often beats everything once an hour: results trickle in
    rather than landing in a lump, and the API quota is spent evenly instead
    of in a burst that trips GitHub's secondary limiter.
    """
    if _state["running"]:
        return {"status": "skipped", "reason": "a run is already in progress"}

    db = SessionLocal()
    try:
        batch = int(settings.rolling_batch_size)
        rows = db.scalars(
            select(Source).where(Source.enabled.is_(True))
            .order_by(Source.last_run_at.is_(None).desc(), Source.last_run_at.asc())
            .limit(max(1, batch))
        ).all()
        ids = [r.id for r in rows]
    finally:
        db.close()

    if not ids:
        return {"status": "skipped", "reason": "no enabled sources"}

    _state["cycle"] += 1
    result = run_collection(trigger="rolling", source_ids=ids)
    _state["last_pulse"] = datetime.now(timezone.utc)
    return result


# owner tiering
NEWCOMER_MAX_AGE_DAYS = 120


def tier_owner(client: GitHubClient, login: str, owner_type: str, cache: dict,
               *, allow_lookup: bool = True) -> dict:
    """Work out an owner's tier.

    The curated lists cost nothing. Anything else is an API call, so the caller
    decides with allow_lookup. Cached for the length of a run.
    """
    if login in cache:
        return cache[login]

    tier, label = tier_for_login(login)
    info = {
        "owner_tier": tier or TIER_UNKNOWN,
        "owner_label": label,
        "owner_followers": 0,
        "owner_public_repos": 0,
        "owner_created_at": None,
    }

    if tier:
        cache[login] = info
        return info
    if not allow_lookup:
        # not cached: a later, more relevant repo from this owner still deserves
        # a proper lookup.
        return info

    profile = client.get_user(login)
    if profile:
        from .github import parse_dt

        created = parse_dt(profile.get("created_at"))
        followers = profile.get("followers") or 0
        public_repos = profile.get("public_repos") or 0
        info["owner_followers"] = followers
        info["owner_public_repos"] = public_repos
        info["owner_created_at"] = created

        age_days = None
        if created:
            age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400.0

        if age_days is not None and age_days <= NEWCOMER_MAX_AGE_DAYS:
            info["owner_tier"] = TIER_NEWCOMER
            info["owner_label"] = f"Account created {int(age_days)}d ago"
        elif followers >= 500 or (owner_type == "Organization" and followers >= 100):
            info["owner_tier"] = TIER_INDIE
            info["owner_label"] = f"{followers} followers"
        else:
            info["owner_tier"] = TIER_INDIE
            info["owner_label"] = TIER_LABELS[TIER_INDIE]

    cache[login] = info
    return info


# persistence
def upsert_repo(db: Session, payload: dict, discovered_via: str) -> tuple[Repository, bool]:
    row = db.scalar(select(Repository).where(Repository.github_id == payload["github_id"]))
    created = False
    if row is None:
        row = Repository(github_id=payload["github_id"], discovered_via=discovered_via[:160])
        db.add(row)
        created = True

    previous_stars = row.stars
    previous_score = row.score

    for field, value in payload.items():
        if field in ("github_id",):
            continue
        if hasattr(row, field) and value is not None:
            setattr(row, field, value)

    row.last_seen_at = utcnow()
    if created:
        row.discovered_at = utcnow()
        row.stars_at_discovery = payload.get("stars", 0)
    else:
        if discovered_via and discovered_via not in (row.discovered_via or ""):
            combined = f"{row.discovered_via}, {discovered_via}" if row.discovered_via else discovered_via
            row.discovered_via = combined[:160]
        if previous_stars and payload.get("stars", 0) >= previous_stars * 3 and payload.get("stars", 0) >= 15:
            db.add(RepoEvent(repo_id=row.id, kind="star_surge",
                             detail=f"{previous_stars} -> {payload['stars']} stars"))
        if previous_score and payload.get("score", 0) - previous_score >= 15:
            db.add(RepoEvent(repo_id=row.id, kind="score_jump",
                             detail=f"{previous_score:.0f} -> {payload['score']:.0f}"))

    return row, created


def send_alert(repo: Repository, cfg: dict) -> None:
    url = (cfg.get("webhook_url") or settings.alert_webhook_url or "").strip()
    if not url:
        return
    text = (
        f"*{repo.full_name}* - score {repo.score:.0f}\n"
        f"{repo.description or 'no description'}\n"
        f"{repo.html_url}"
    )
    body = {"text": text, "content": text, "repo": repo.full_name,
            "score": repo.score, "url": repo.html_url}
    try:
        httpx.post(url, json=body, timeout=10.0)
    except httpx.HTTPError as exc:
        log.warning("alert webhook failed: %s", exc)


# the run
def run_collection(trigger: str = "schedule", source_ids: list[int] | None = None) -> dict:
    """One full pass over the sources. Safe to call from a thread."""
    if not _run_lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "a collection run is already in progress"}

    _state["running"] = True
    db: Session = SessionLocal()
    run = CollectionRun(trigger=trigger, status="running")
    db.add(run)
    db.commit()
    _state["current_run_id"] = run.id

    logbook: list[str] = []
    cfg = get_setting(db, "collector")
    weights = get_setting(db, "scoring_weights")
    alerts = get_setting(db, "alerts")
    token = (get_setting(db, "github") or {}).get("token_override") or settings.github_token

    lookback = int(cfg.get("lookback_days") or settings.collect_lookback_days)
    since = (datetime.now(timezone.utc) - timedelta(days=lookback)).date().isoformat()
    min_keep = float(cfg.get("min_score_to_keep") or 0)
    enrich_top = int(cfg.get("enrich_top_n") or 0)
    enrich_min = float(cfg.get("enrich_min_score") or 100)

    client = GitHubClient(token=token)
    owner_cache: dict = {}
    seen = new = updated = 0
    quota_hit = False
    max_repo_age = int(cfg.get("max_repo_age_days") or 60)
    owner_lookup_floor = float(cfg.get("owner_lookup_min_relevance") or 0.25)
    candidates: list[tuple[Repository, dict]] = []

    try:
        query = select(Source).where(Source.enabled.is_(True)).order_by(Source.kind, Source.id)
        if source_ids:
            query = select(Source).where(Source.id.in_(source_ids), Source.enabled.is_(True))
        sources = list(db.scalars(query))

        if not client.authenticated:
            logbook.append("No GitHub token configured - running on the 60 req/h anonymous quota.")

        for source in sources:
            try:
                items = _fetch_source(client, source, since, cfg)
            except RateLimited as exc:
                logbook.append(f"Rate limit hit on {source.kind}:{source.value}; stopping early.")
                run.error = str(exc)
                break
            except BudgetExhausted as exc:
                logbook.append(f"API budget exhausted at {source.kind}:{source.value}.")
                run.error = str(exc)
                break
            except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
                source.last_status = f"error: {exc}"[:255]
                source.last_run_at = utcnow()
                logbook.append(f"{source.kind}:{source.value} -> error: {exc}")
                db.commit()
                continue

            found = 0
            fresh = 0
            for item in items:
                payload = normalise_repo(item)
                if not payload.get("github_id") or not payload.get("full_name"):
                    continue
                if _too_old(payload, max_repo_age, source.kind):
                    continue

                seen += 1
                found += 1

                # cheap check first, most search hits are not security work
                _, relevance_hint, _ = classify(
                    payload.get("description", ""), payload.get("topics") or [], payload.get("name", "")
                )
                try:
                    owner_info = tier_owner(
                        client, payload["owner"], payload["owner_type"], owner_cache,
                        allow_lookup=relevance_hint >= owner_lookup_floor,
                    )
                except (RateLimited, BudgetExhausted) as exc:
                    logbook.append(f"Quota reached while profiling owners: {exc}")
                    run.error = str(exc)
                    quota_hit = True
                    break
                payload.update(owner_info)

                score, extra = compute_score(payload, weights)
                payload["score"] = score
                payload["score_breakdown"] = extra["breakdown"]
                payload["categories"] = extra["categories"]
                payload["signals"] = extra["signals"]
                payload["star_velocity"] = extra["star_velocity"]

                if score < min_keep:
                    continue

                via = f"{source.kind}:{source.value}"[:160]
                row, created = upsert_repo(db, payload, via)
                db.flush()
                if created:
                    new += 1
                    fresh += 1
                else:
                    updated += 1
                candidates.append((row, payload))

            source.last_run_at = utcnow()
            source.last_status = f"ok - {found} items, {fresh} new"
            source.total_found = (source.total_found or 0) + found
            source.total_new = (source.total_new or 0) + fresh
            run.sources_run += 1
            db.commit()
            logbook.append(f"{source.kind}:{source.value} -> {found} items, {fresh} new")

            if quota_hit:
                logbook.append("Stopping early: GitHub quota exhausted. "
                               "Collected results are kept; the next run resumes.")
                break

        # ---- second pass: deep-enrich the most promising finds ------------- #
        enriched = 0
        candidates.sort(key=lambda pair: pair[1].get("score", 0), reverse=True)
        for row, payload in candidates:
            if enriched >= enrich_top:
                break
            if payload.get("score", 0) < enrich_min:
                continue
            if row.enriched_at and (utcnow() - _aware(row.enriched_at)).days < 14:
                continue
            try:
                readme = client.get_readme(row.full_name)
            except (RateLimited, BudgetExhausted):
                logbook.append("Stopped enrichment: API quota reached.")
                break
            except Exception:  # noqa: BLE001
                continue
            if readme:
                payload["readme_excerpt"] = readme[:4000]
                payload["readme_length"] = len(readme)
                row.readme_excerpt = payload["readme_excerpt"]
                row.readme_length = payload["readme_length"]
                score, extra = compute_score(payload, weights)
                row.score = score
                row.score_breakdown = extra["breakdown"]
                row.categories = extra["categories"]
                row.signals = extra["signals"]
            row.enriched_at = utcnow()
            enriched += 1
            db.commit()
        if enriched:
            logbook.append(f"Deep-enriched {enriched} repositories with their README.")

        # ---- alerts --------------------------------------------------------- #
        if alerts.get("enabled"):
            threshold = float(alerts.get("min_score") or settings.alert_min_score)
            for row, _ in candidates:
                if row.score >= threshold and not row.alerted:
                    send_alert(row, alerts)
                    row.alerted = True
            db.commit()

        # ---- retention ------------------------------------------------------ #
        retention = int(cfg.get("retention_days") or 0)
        if retention:
            cutoff = utcnow() - timedelta(days=retention)
            stale = db.scalars(
                select(Repository).where(Repository.discovered_at < cutoff, Repository.score < 40)
            ).all()
            for row in stale:
                db.delete(row)
            if stale:
                logbook.append(f"Pruned {len(stale)} low-score records older than {retention} days.")
            db.commit()

        # Rolling mode writes a run row every cycle, so the history is capped.
        keep_ids = [
            row[0] for row in db.execute(
                select(CollectionRun.id).order_by(CollectionRun.started_at.desc()).limit(KEEP_RUNS)
            ).all()
        ]
        if len(keep_ids) >= KEEP_RUNS:
            db.query(CollectionRun).filter(~CollectionRun.id.in_(keep_ids)).delete(
                synchronize_session=False)
            db.commit()

        run.status = "ok" if not run.error else "partial"

    except Exception as exc:  # noqa: BLE001
        log.exception("collection run failed")
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        logbook.append(f"FATAL: {exc}")
    finally:
        run.finished_at = utcnow()
        run.repos_seen = seen
        run.repos_new = new
        run.repos_updated = updated
        run.api_calls = client.calls
        run.rate_remaining = client.rate_remaining
        run.log = logbook[-200:]
        db.commit()
        result = {
            "status": run.status,
            "run_id": run.id,
            "seen": seen,
            "new": new,
            "updated": updated,
            "api_calls": client.calls,
            "rate_remaining": client.rate_remaining,
        }
        client.close()
        db.close()
        _state["running"] = False
        _state["current_run_id"] = None
        _state["last_pulse"] = datetime.now(timezone.utc)
        _run_lock.release()

    return result


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _too_old(payload: dict, max_age_days: int, kind: str) -> bool:
    """Is this repo too old to count as a new one.

    Org and starred sources hand back a whole listing, most of it years old.
    An earlier version kept anything with a recent push, which filled the index
    with long-running projects that had merely received a commit. The point
    here is repos that did not exist last month, so creation date is the only
    thing that decides.
    """
    if kind == "search":
        return False          # the query already carries created:>...
    created = payload.get("repo_created_at")
    if created is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, max_age_days))
    return _aware(created) < cutoff


def _fetch_source(client: GitHubClient, source: Source, since: str, cfg: dict) -> list[dict]:
    pages = max(1, min(source.max_pages or 1, int(cfg.get("search_pages") or 1) + 2))
    if source.kind == "search":
        query = source.value.replace("{since}", since)
        return client.search_repositories(query, sort="updated", per_page=50, pages=pages)
    if source.kind == "org":
        return client.list_org_repos(source.value, per_page=30, pages=pages)
    if source.kind == "starred":
        return client.list_user_starred(source.value, per_page=30, pages=pages)
    if source.kind == "user":
        return client.list_org_repos(source.value, per_page=30, pages=pages)
    return []

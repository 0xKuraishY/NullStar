"""Ranking.

Sorting by stars is useless here, GitHub already does it and anything published
today sits at the bottom. So relevance and age carry most of the weight and
popularity barely counts. A repo with no stars can come out above a famous one.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .collector.known import (
    TIER_BIG_TECH,
    TIER_COMMUNITY,
    TIER_GOVERNMENT,
    TIER_INDIE,
    TIER_KNOWN_RESEARCHER,
    TIER_NEWCOMER,
    TIER_RESEARCH_LAB,
    TIER_SECURITY_VENDOR,
    TIER_UNKNOWN,
)
from .taxonomy import classify, noise_penalty

DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 42.0,      # how certainly this is a cybersecurity project
    "freshness": 20.0,      # how recently it appeared / was pushed
    "origin": 16.0,         # who published it (big tech ... brand-new account)
    "substance": 12.0,      # readme, license, topics, description quality
    "momentum": 10.0,       # star velocity, capped hard on purpose
    "gem_bonus": 12.0,      # low-visibility but high-relevance kicker
    "noise_penalty": 30.0,  # link farms, courses, forks of forks
}

TIER_WEIGHT = {
    TIER_BIG_TECH: 1.00,
    TIER_SECURITY_VENDOR: 0.95,
    TIER_RESEARCH_LAB: 0.90,
    TIER_GOVERNMENT: 0.90,
    TIER_COMMUNITY: 0.80,
    TIER_KNOWN_RESEARCHER: 0.85,
    TIER_NEWCOMER: 0.62,
    TIER_INDIE: 0.45,
    TIER_UNKNOWN: 0.35,
}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_since(dt: datetime | None, now: datetime) -> float | None:
    dt = _utc(dt)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def _half_life(days: float | None, half_life_days: float) -> float:
    """1.0 today, 0.5 after `half_life_days`, asymptotically 0."""
    if days is None:
        return 0.0
    return 0.5 ** (days / half_life_days)


def compute_score(repo: dict, weights: dict[str, float] | None = None, now: datetime | None = None) -> tuple[float, dict]:
    """Score a normalised repo dict.

    Returns (score, breakdown). The breakdown is stored and shown on the repo
    page so a rank can always be explained.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    now = now or datetime.now(timezone.utc)

    categories, relevance, matched = classify(
        repo.get("description", "") or "",
        repo.get("topics") or [],
        repo.get("name", "") or "",
        repo.get("readme_excerpt", "") or "",
    )

    created_days = _days_since(repo.get("repo_created_at"), now)
    pushed_days = _days_since(repo.get("repo_pushed_at"), now)

    # being new counts for more than having been touched recently
    birth = _half_life(created_days, 21.0)
    activity = _half_life(pushed_days, 10.0)
    freshness = 0.65 * birth + 0.35 * activity

    # who published it
    tier = repo.get("owner_tier") or TIER_UNKNOWN
    origin = TIER_WEIGHT.get(tier, 0.35)
    followers = repo.get("owner_followers") or 0
    if followers:
        # someone we have not tiered but who clearly has reach
        origin = max(origin, min(0.8, 0.35 + math.log10(followers + 1) / 6.0))

    # signs of actual work
    substance = 0.0
    desc = (repo.get("description") or "").strip()
    if len(desc) >= 40:
        substance += 0.25
    elif desc:
        substance += 0.1
    topics = repo.get("topics") or []
    substance += min(0.25, len(topics) * 0.05)
    readme_len = repo.get("readme_length") or 0
    if readme_len > 4000:
        substance += 0.3
    elif readme_len > 1200:
        substance += 0.22
    elif readme_len > 300:
        substance += 0.12
    if repo.get("license"):
        substance += 0.1
    if repo.get("homepage"):
        substance += 0.05
    if (repo.get("size_kb") or 0) > 150:
        substance += 0.05
    substance = min(1.0, substance)

    # compressed on a log scale, otherwise popularity swamps everything else
    stars = repo.get("stars") or 0
    velocity = 0.0
    if created_days and created_days > 0.5:
        velocity = stars / created_days
    momentum = min(1.0, math.log10(velocity * 10 + 1) / 2.0)

    # relevant + invisible + recent is the case nobody else surfaces
    gem = 0.0
    gem_reason = ""
    if stars <= 5 and relevance >= 0.45 and (created_days is None or created_days <= 45):
        gem = 1.0
        gem_reason = "fresh, relevant, effectively invisible (<=5 stars)"
    elif stars <= 25 and relevance >= 0.6 and (created_days is None or created_days <= 60):
        gem = 0.6
        gem_reason = "relevant and still under the radar (<=25 stars)"
    if tier == TIER_NEWCOMER and relevance >= 0.4:
        gem = max(gem, 0.75)
        gem_reason = gem_reason or "brand-new account shipping security code"

    # things that drag a result down
    penalty, penalty_reasons = noise_penalty(desc, repo.get("name", ""), topics)
    if repo.get("is_fork"):
        penalty = min(1.0, penalty + 0.35)
        penalty_reasons.append("fork of another repository")
    if repo.get("is_archived"):
        penalty = min(1.0, penalty + 0.5)
        penalty_reasons.append("archived")
    if not desc and not topics and readme_len < 200:
        penalty = min(1.0, penalty + 0.25)
        penalty_reasons.append("no description, no topics, no readme")

    raw = (
        w["relevance"] * relevance
        + w["freshness"] * freshness
        + w["origin"] * origin
        + w["substance"] * substance
        + w["momentum"] * momentum
        + w["gem_bonus"] * gem
        - w["noise_penalty"] * penalty
    )
    total = max(0.0, min(100.0, raw))

    signals: list[str] = []
    if gem >= 0.9:
        signals.append("hidden-gem")
    elif gem > 0:
        signals.append("under-the-radar")
    if tier == TIER_NEWCOMER:
        signals.append("new-account")
    if tier in (TIER_BIG_TECH, TIER_SECURITY_VENDOR, TIER_RESEARCH_LAB, TIER_GOVERNMENT):
        signals.append("major-publisher")
    if created_days is not None and created_days <= 3:
        signals.append("just-created")
    if velocity >= 5:
        signals.append("trending")
    if relevance >= 0.75:
        signals.append("high-relevance")
    if penalty >= 0.4:
        signals.append("noisy")

    breakdown = {
        "total": round(total, 1),
        "components": {
            "relevance": {"value": round(relevance, 3), "weight": w["relevance"],
                          "points": round(w["relevance"] * relevance, 1)},
            "freshness": {"value": round(freshness, 3), "weight": w["freshness"],
                          "points": round(w["freshness"] * freshness, 1)},
            "origin": {"value": round(origin, 3), "weight": w["origin"],
                       "points": round(w["origin"] * origin, 1)},
            "substance": {"value": round(substance, 3), "weight": w["substance"],
                          "points": round(w["substance"] * substance, 1)},
            "momentum": {"value": round(momentum, 3), "weight": w["momentum"],
                         "points": round(w["momentum"] * momentum, 1)},
            "gem_bonus": {"value": round(gem, 3), "weight": w["gem_bonus"],
                          "points": round(w["gem_bonus"] * gem, 1), "reason": gem_reason},
            "noise_penalty": {"value": round(penalty, 3), "weight": w["noise_penalty"],
                              "points": -round(w["noise_penalty"] * penalty, 1),
                              "reasons": penalty_reasons},
        },
        "matched_terms": {k: v for k, v in list(matched.items())[:6]},
        "age_days": round(created_days, 1) if created_days is not None else None,
        "pushed_days": round(pushed_days, 1) if pushed_days is not None else None,
        "star_velocity": round(velocity, 3),
    }

    return total, {
        "breakdown": breakdown,
        "categories": categories,
        "signals": signals,
        "relevance": relevance,
        "star_velocity": velocity,
    }


def band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def band_label(score: float) -> str:
    return {"critical": "Must see", "high": "Strong", "medium": "Worth a look", "low": "Background"}[band(score)]

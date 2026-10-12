"""Feed query construction - shared by the HTML views, the JSON API and feeds."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, aliased

from .collector.known import TIER_LABELS
from .models import Repository, UserRepoState, utcnow
from .taxonomy import CATEGORIES

SORTS = {
    "score": ("Interest score", Repository.score.desc(), Repository.discovered_at.desc()),
    "new": ("Newest discovery", Repository.discovered_at.desc(), Repository.score.desc()),
    "created": ("Repo creation date", Repository.repo_created_at.desc(), Repository.score.desc()),
    "pushed": ("Last push", Repository.repo_pushed_at.desc(), Repository.score.desc()),
    "stars": ("Stars", Repository.stars.desc(), Repository.score.desc()),
    "velocity": ("Star velocity", Repository.star_velocity.desc(), Repository.score.desc()),
    "underrated": ("Most underrated", Repository.score.desc(), Repository.stars.asc()),
}

WINDOWS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 0}


@dataclass
class FeedFilters:
    q: str = ""
    category: str = ""
    tier: str = ""
    language: str = ""
    signal: str = ""
    window: str = "30d"
    sort: str = "score"
    min_score: int = 0
    max_stars: int = 0
    page: int = 1
    per_page: int = 30
    bookmarked: bool = False
    unseen: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_query(cls, params) -> "FeedFilters":
        def _int(name: str, default: int, *, low: int = 0, high: int = 1_000_000) -> int:
            """Parse and clamp. These end up in a SQL comparison or a slice,
            and SQLite raises OverflowError past 2**63."""
            raw = params.get(name, default)
            try:
                value = int(str(raw).strip() or default)
            except (TypeError, ValueError):
                return default
            return max(low, min(high, value))

        return cls(
            q=(params.get("q") or "").strip()[:120],
            category=(params.get("category") or "").strip(),
            tier=(params.get("tier") or "").strip(),
            language=(params.get("language") or "").strip()[:40],
            signal=(params.get("signal") or "").strip(),
            window=(params.get("window") or "30d") if (params.get("window") or "30d") in WINDOWS else "30d",
            sort=(params.get("sort") or "score") if (params.get("sort") or "score") in SORTS else "score",
            min_score=_int("min_score", 0, high=100),
            max_stars=_int("max_stars", 0, high=10_000_000),
            page=_int("page", 1, low=1, high=100_000),
            per_page=_int("per_page", 30, low=10, high=100),
            bookmarked=params.get("bookmarked") in ("1", "true", "on"),
            unseen=params.get("unseen") in ("1", "true", "on"),
        )

    def querystring(self, **overrides) -> str:
        base = {
            "q": self.q, "category": self.category, "tier": self.tier, "language": self.language,
            "signal": self.signal, "window": self.window, "sort": self.sort,
            "min_score": self.min_score or "", "max_stars": self.max_stars or "",
            "page": self.page, "per_page": self.per_page,
            "bookmarked": "1" if self.bookmarked else "", "unseen": "1" if self.unseen else "",
        }
        base.update(overrides)
        parts = [f"{k}={v}" for k, v in base.items() if v not in ("", None, 0) or k == "page"]
        return "&".join(parts)

    @property
    def is_filtered(self) -> bool:
        return bool(self.q or self.category or self.tier or self.language or self.signal
                    or self.min_score or self.max_stars or self.bookmarked or self.unseen)


def build_query(filters: FeedFilters, user_id: int | None) -> Select:
    """The SQL half. Category and signal live in JSON arrays and get filtered
    in Python after, so this works on both Postgres and SQLite."""
    state = aliased(UserRepoState)
    stmt = select(Repository)

    if user_id:
        stmt = stmt.outerjoin(
            state,
            (state.repo_id == Repository.id) & (state.user_id == user_id),
        )
        stmt = stmt.where(or_(state.dismissed.is_(False), state.id.is_(None)))
        if filters.bookmarked:
            stmt = stmt.where(state.bookmarked.is_(True))
        if filters.unseen:
            stmt = stmt.where(or_(state.seen.is_(False), state.id.is_(None)))

    days = WINDOWS.get(filters.window, 30)
    if days:
        stmt = stmt.where(Repository.discovered_at >= utcnow() - timedelta(days=days))

    if filters.q:
        like = f"%{filters.q.lower()}%"
        stmt = stmt.where(
            or_(
                Repository.full_name.ilike(like),
                Repository.description.ilike(like),
                Repository.owner.ilike(like),
                Repository.readme_excerpt.ilike(like),
            )
        )
    if filters.tier:
        stmt = stmt.where(Repository.owner_tier == filters.tier)
    if filters.language:
        stmt = stmt.where(Repository.language == filters.language)
    if filters.min_score:
        stmt = stmt.where(Repository.score >= filters.min_score)
    if filters.max_stars:
        stmt = stmt.where(Repository.stars <= filters.max_stars)

    _, primary, secondary = SORTS[filters.sort]
    return stmt.order_by(primary, secondary)


def apply_python_filters(rows: list[Repository], filters: FeedFilters) -> list[Repository]:
    out = rows
    if filters.category:
        out = [r for r in out if filters.category in (r.categories or [])]
    if filters.signal:
        out = [r for r in out if filters.signal in (r.signals or [])]
    return out


# Ceiling on rows pulled before the Python-side filtering. Far past any real
# page depth, and it stops a bad filter walking a year of history.
SCAN_LIMIT = 4000


def fetch_feed(db: Session, filters: FeedFilters, user_id: int | None) -> tuple[list[Repository], int]:
    """Returns (rows for this page, total matches)."""
    stmt = build_query(filters, user_id).limit(SCAN_LIMIT)
    rows = list(db.scalars(stmt).unique())
    rows = apply_python_filters(rows, filters)
    total = len(rows)
    start = (filters.page - 1) * filters.per_page
    return rows[start:start + filters.per_page], total


def user_states(db: Session, user_id: int | None, repos: list[Repository]) -> dict[int, UserRepoState]:
    if not user_id or not repos:
        return {}
    ids = [r.id for r in repos]
    rows = db.scalars(
        select(UserRepoState).where(UserRepoState.user_id == user_id, UserRepoState.repo_id.in_(ids))
    ).all()
    return {row.repo_id: row for row in rows}


def facet_options(db: Session) -> dict:
    languages = [
        row[0]
        for row in db.execute(
            select(Repository.language).where(Repository.language != "").distinct().limit(200)
        )
        if row[0]
    ]
    return {
        "categories": [(slug, meta["label"], meta["accent"]) for slug, meta in CATEGORIES.items()],
        "tiers": list(TIER_LABELS.items()),
        "languages": sorted(languages),
        "sorts": [(key, meta[0]) for key, meta in SORTS.items()],
        "windows": list(WINDOWS.keys()),
        "signals": [
            ("hidden-gem", "Hidden gem"),
            ("under-the-radar", "Under the radar"),
            ("new-account", "New account"),
            ("major-publisher", "Major publisher"),
            ("just-created", "Just created"),
            ("trending", "Trending"),
            ("high-relevance", "High relevance"),
        ],
    }

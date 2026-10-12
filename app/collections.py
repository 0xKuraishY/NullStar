"""Collections. Folders of saved repos, plus the share links."""
from __future__ import annotations

import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Collection, CollectionItem, Repository, User

COLOURS = {
    "mint": "Mint", "amber": "Amber", "rose": "Rose",
    "iris": "Iris", "sky": "Sky", "ink-3": "Grey",
}

SORTS = {
    "added": "Order added",
    "manual": "My own order",
    "score": "Interest score",
    "stars": "Stars",
    "fresh": "Repository age",
    "name": "Name",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    slug = _SLUG_STRIP.sub("-", (name or "").lower()).strip("-")
    return (slug or "folder")[:90]


def unique_slug(db: Session, user_id: int, name: str, exclude_id: int | None = None) -> str:
    base = slugify(name)
    candidate, n = base, 2
    while True:
        stmt = select(Collection.id).where(
            Collection.user_id == user_id, Collection.slug == candidate)
        if exclude_id:
            stmt = stmt.where(Collection.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{n}"[:90]
        n += 1


def new_share_token() -> str:
    return secrets.token_urlsafe(18)


def counts_for(db: Session, user_id: int) -> dict[int, int]:
    rows = db.execute(
        select(CollectionItem.collection_id, func.count())
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user_id)
        .group_by(CollectionItem.collection_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def list_for(db: Session, user: User | None) -> list[Collection]:
    if user is None:
        return []
    return list(db.scalars(
        select(Collection).where(Collection.user_id == user.id)
        .order_by(Collection.position, Collection.name)))


def membership(db: Session, user: User | None, repo_id: int) -> set[int]:
    """Which of this user's collections already contain the repo."""
    if user is None:
        return set()
    rows = db.execute(
        select(CollectionItem.collection_id)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user.id, CollectionItem.repo_id == repo_id)
    ).all()
    return {row[0] for row in rows}


def items_sorted(db: Session, collection: Collection, sort: str = "added") -> list[CollectionItem]:
    order = {
        "added": CollectionItem.added_at.desc(),
        "manual": CollectionItem.position.asc(),
        "score": Repository.score.desc(),
        "stars": Repository.stars.desc(),
        "fresh": Repository.repo_created_at.desc(),
        "name": Repository.full_name.asc(),
    }.get(sort, CollectionItem.added_at.desc())

    return list(db.scalars(
        select(CollectionItem)
        .join(Repository, Repository.id == CollectionItem.repo_id)
        .where(CollectionItem.collection_id == collection.id)
        .order_by(order)
    ))

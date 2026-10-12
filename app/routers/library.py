"""A reader's own library: collections, follows, and public shares."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..collections import (
    COLOURS,
    SORTS,
    counts_for,
    items_sorted,
    list_for,
    new_share_token,
    unique_slug,
)
from ..collector.known import TIER_LABELS
from ..db import get_db
from ..deps import current_user, optional_user, redirect, render, verify_csrf
from ..models import Collection, CollectionItem, Follow, Repository, User, UserRepoState, utcnow
from ..scoring import band, band_label
from ..security import audit, flash
from ..taxonomy import category_accent, category_label

router = APIRouter()


def _chrome(db: Session, user: User | None) -> dict:
    return {
        "category_label": category_label,
        "category_accent": category_accent,
        "band": band,
        "band_label": band_label,
        "tier_labels": TIER_LABELS,
        "collections": list_for(db, user),
        "collection_counts": counts_for(db, user.id) if user else {},
        "colours": COLOURS,
        "sorts": SORTS,
    }


def _owned(db: Session, user: User, collection_id: int) -> Collection | None:
    row = db.get(Collection, collection_id)
    return row if row and row.user_id == user.id else None


# library
@router.get("/library")
def library(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    kept = db.scalar(
        select(func.count()).select_from(UserRepoState)
        .where(UserRepoState.user_id == user.id, UserRepoState.bookmarked.is_(True))) or 0
    unfiled = db.scalar(
        select(func.count()).select_from(UserRepoState)
        .where(UserRepoState.user_id == user.id, UserRepoState.bookmarked.is_(True),
               UserRepoState.repo_id.notin_(
                   select(CollectionItem.repo_id)
                   .join(Collection, Collection.id == CollectionItem.collection_id)
                   .where(Collection.user_id == user.id)))) or 0
    follows = db.scalars(
        select(Follow).where(Follow.user_id == user.id).order_by(Follow.login)).all()
    notes = db.scalar(
        select(func.count()).select_from(UserRepoState)
        .where(UserRepoState.user_id == user.id, UserRepoState.note != "")) or 0

    return render(request, "library.html", user=user, title="Library",
                  kept=kept, unfiled=unfiled, follows=follows, notes=notes,
                  **_chrome(db, user))


@router.post("/collections")
def create_collection(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    colour: str = Form("mint"),
    back: str = Form("/library"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    name = name.strip()[:80]
    response = redirect(back if back.startswith("/") and not back.startswith("//") else "/library")
    if not name:
        flash(response, "error", "A collection needs a name.")
        return response
    if db.scalar(select(func.count()).select_from(Collection)
                 .where(Collection.user_id == user.id)) >= 100:
        flash(response, "error", "One hundred collections is enough for anybody.")
        return response

    row = Collection(
        user_id=user.id, name=name, slug=unique_slug(db, user.id, name),
        description=description.strip()[:400],
        colour=colour if colour in COLOURS else "mint",
        position=db.scalar(select(func.count()).select_from(Collection)
                           .where(Collection.user_id == user.id)) or 0,
    )
    db.add(row)
    db.commit()
    audit(db, "collection.created", user=user, target=name, request=request)
    flash(response, "ok", f"Collection '{name}' made.")
    return response


@router.get("/collections/{collection_id}")
def view_collection(collection_id: int, request: Request, sort: str = "added",
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    collection = _owned(db, user, collection_id)
    if collection is None:
        return render(request, "error.html", user=user, title="Not found", code=404,
                      message="No such collection.", status_code=404)
    sort = sort if sort in SORTS else "added"
    items = items_sorted(db, collection, sort)
    share_url = (str(request.base_url).rstrip("/") + f"/shared/{collection.share_token}"
                 if collection.is_public and collection.share_token else "")
    return render(request, "collection.html", user=user, title=collection.name,
                  collection=collection, items=items, sort=sort, share_url=share_url,
                  **_chrome(db, user))


@router.post("/collections/{collection_id}/edit")
def edit_collection(
    collection_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    colour: str = Form("mint"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    collection = _owned(db, user, collection_id)
    response = redirect(f"/collections/{collection_id}")
    if collection is None:
        return redirect("/library")
    name = name.strip()[:80]
    if name:
        if name != collection.name:
            collection.slug = unique_slug(db, user.id, name, exclude_id=collection.id)
        collection.name = name
    collection.description = description.strip()[:400]
    collection.colour = colour if colour in COLOURS else "mint"
    db.commit()
    flash(response, "ok", "Saved.")
    return response


@router.post("/collections/{collection_id}/share")
def toggle_share(collection_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(current_user), _: None = Depends(verify_csrf)):
    collection = _owned(db, user, collection_id)
    response = redirect(f"/collections/{collection_id}")
    if collection is None:
        return redirect("/library")
    collection.is_public = not collection.is_public
    if collection.is_public and not collection.share_token:
        collection.share_token = new_share_token()
    db.commit()
    audit(db, "collection.share_toggled", user=user, target=collection.name,
          request=request, public=collection.is_public)
    flash(response, "ok",
          "Anybody with the link can read it now." if collection.is_public
          else "The link no longer works.")
    return response


@router.post("/collections/{collection_id}/reshare")
def reshare(collection_id: int, request: Request, db: Session = Depends(get_db),
            user: User = Depends(current_user), _: None = Depends(verify_csrf)):
    """New link, the old one stops working."""
    collection = _owned(db, user, collection_id)
    response = redirect(f"/collections/{collection_id}")
    if collection is None:
        return redirect("/library")
    collection.share_token = new_share_token()
    db.commit()
    flash(response, "ok", "A new link was made. The old one is dead.")
    return response


@router.post("/collections/{collection_id}/delete")
def delete_collection(collection_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(current_user), _: None = Depends(verify_csrf)):
    collection = _owned(db, user, collection_id)
    response = redirect("/library")
    if collection is None:
        return response
    name = collection.name
    db.delete(collection)
    db.commit()
    audit(db, "collection.deleted", user=user, target=name, request=request)
    flash(response, "ok", f"'{name}' is gone. The repositories themselves are untouched.")
    return response


# filing
@router.post("/repo/{repo_id}/file")
def file_repo(
    repo_id: int,
    request: Request,
    collection_id: int = Form(...),
    back: str = Form("/"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _: None = Depends(verify_csrf),
):
    """Add or remove one repo from one collection."""
    response = redirect(back if back.startswith("/") and not back.startswith("//") else "/")
    collection = _owned(db, user, collection_id)
    repo = db.get(Repository, repo_id)
    if collection is None or repo is None:
        flash(response, "error", "That collection is not yours.")
        return response

    existing = db.scalar(select(CollectionItem).where(
        CollectionItem.collection_id == collection.id, CollectionItem.repo_id == repo.id))
    if existing:
        db.delete(existing)
        message = f"Removed from {collection.name}."
    else:
        db.add(CollectionItem(
            collection_id=collection.id, repo_id=repo.id,
            position=db.scalar(select(func.count()).select_from(CollectionItem)
                               .where(CollectionItem.collection_id == collection.id)) or 0))
        # filing something implies keeping it
        state = db.scalar(select(UserRepoState).where(
            UserRepoState.user_id == user.id, UserRepoState.repo_id == repo.id))
        if state is None:
            db.add(UserRepoState(user_id=user.id, repo_id=repo.id, bookmarked=True, seen=True))
        else:
            state.bookmarked = True
        message = f"Filed under {collection.name}."
    collection.updated_at = utcnow()
    db.commit()
    flash(response, "ok", message)
    return response


@router.post("/collections/{collection_id}/items/{item_id}/note")
def item_note(collection_id: int, item_id: int, request: Request, note: str = Form(""),
              db: Session = Depends(get_db), user: User = Depends(current_user),
              _: None = Depends(verify_csrf)):
    collection = _owned(db, user, collection_id)
    item = db.get(CollectionItem, item_id)
    if collection and item and item.collection_id == collection.id:
        item.note = note[:500]
        db.commit()
    return redirect(f"/collections/{collection_id}")


@router.post("/collections/{collection_id}/items/{item_id}/move")
def item_move(collection_id: int, item_id: int, request: Request, direction: str = Form("up"),
              db: Session = Depends(get_db), user: User = Depends(current_user),
              _: None = Depends(verify_csrf)):
    collection = _owned(db, user, collection_id)
    item = db.get(CollectionItem, item_id)
    if not (collection and item and item.collection_id == collection.id):
        return redirect("/library")
    rows = items_sorted(db, collection, "manual")
    index = next((i for i, r in enumerate(rows) if r.id == item.id), None)
    if index is not None:
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(rows):
            rows[index], rows[target] = rows[target], rows[index]
            for position, row in enumerate(rows):
                row.position = position
            db.commit()
    return redirect(f"/collections/{collection_id}?sort=manual")


# follows
@router.post("/follows")
def add_follow(request: Request, login: str = Form(...), back: str = Form("/library"),
               db: Session = Depends(get_db), user: User = Depends(current_user),
               _: None = Depends(verify_csrf)):
    login = login.strip().lstrip("@")[:120]
    response = redirect(back if back.startswith("/") and not back.startswith("//") else "/library")
    if not login:
        return response
    if db.scalar(select(Follow).where(Follow.user_id == user.id, Follow.login == login)):
        flash(response, "warn", f"You already follow {login}.")
        return response
    db.add(Follow(user_id=user.id, login=login))
    db.commit()
    flash(response, "ok", f"Following {login}.")
    return response


@router.post("/follows/{follow_id}/delete")
def drop_follow(follow_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user), _: None = Depends(verify_csrf)):
    row = db.get(Follow, follow_id)
    if row and row.user_id == user.id:
        db.delete(row)
        db.commit()
    return redirect("/library")


# public share
@router.get("/shared/{token}")
def shared(token: str, request: Request, sort: str = "added",
           db: Session = Depends(get_db), viewer: User | None = Depends(optional_user)):
    collection = db.scalar(select(Collection).where(
        Collection.share_token == token, Collection.is_public.is_(True)))
    if collection is None or not token:
        return render(request, "error.html", user=viewer, title="Not found", code=404,
                      message="This link is dead, or the collection was made private again.",
                      status_code=404)
    sort = sort if sort in SORTS else "added"
    items = items_sorted(db, collection, sort)
    owner = db.get(User, collection.user_id)
    return render(request, "shared.html", user=viewer, title=collection.name,
                  collection=collection, items=items, sort=sort,
                  owner_name=(owner.display_name or owner.username) if owner else "somebody",
                  **_chrome(db, viewer))

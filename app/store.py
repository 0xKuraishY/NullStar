"""Key/value settings stored in the database (editable from the admin UI)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import Setting
from .scoring import DEFAULT_WEIGHTS

DEFAULTS: dict[str, Any] = {
    "scoring_weights": DEFAULT_WEIGHTS,
    "collector": {
        "lookback_days": 10,
        "min_score_to_keep": 18,
        "enrich_top_n": 60,
        "enrich_min_score": 40,
        "search_pages": 1,
        "retention_days": 365,
        "owner_lookup_min_relevance": 0.25,
        "max_repo_age_days": 60,
    },
    "auth": {
        "allow_open_registration": True,
        "invite_ttl_hours": 168,
        "default_role": "viewer",
    },
    "alerts": {
        "webhook_url": "",
        "min_score": 80,
        "enabled": False,
    },
    "github": {
        "token_override": "",
    },
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return _clone(DEFAULTS.get(key))
    default = DEFAULTS.get(key)
    if isinstance(default, dict) and isinstance(row.value, dict):
        merged = _clone(default)
        merged.update(row.value)
        return merged
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def _clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(v) for v in value]
    return value

"""Thin, rate-limit-aware GitHub REST client."""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone

import httpx

from ..config import settings

log = logging.getLogger("nullstar.github")


class RateLimited(Exception):
    def __init__(self, reset_at: float):
        self.reset_at = reset_at
        super().__init__(f"GitHub rate limit exhausted until {reset_at}")


class BudgetExhausted(Exception):
    pass


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubClient:
    """One instance per collection run; tracks its own call budget."""

    def __init__(self, token: str | None = None, budget: int | None = None):
        self.token = (token if token is not None else settings.github_token) or ""
        self.budget = budget if budget is not None else settings.max_api_calls_per_run
        self.calls = 0
        self.rate_remaining = -1
        self.search_remaining = -1
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nullstar-radar/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(base_url=settings.github_api, headers=headers, timeout=25.0)

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: dict | None = None, *, search: bool = False) -> httpx.Response | None:
        if self.calls >= self.budget:
            raise BudgetExhausted(f"API call budget of {self.budget} reached")

        for attempt in range(3):
            self.calls += 1
            try:
                resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                log.warning("GET %s failed (%s), attempt %s", path, exc, attempt + 1)
                time.sleep(1.5 * (attempt + 1))
                continue

            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining is not None:
                if search:
                    self.search_remaining = int(remaining)
                else:
                    self.rate_remaining = int(remaining)

            if resp.status_code == 200:
                return resp
            if resp.status_code in (403, 429):
                reset = float(resp.headers.get("x-ratelimit-reset", 0) or 0)
                if resp.headers.get("x-ratelimit-remaining") == "0":
                    raise RateLimited(reset)
                retry_after = float(resp.headers.get("retry-after", 2) or 2)
                time.sleep(min(retry_after, 10))
                continue
            if resp.status_code in (404, 451):
                return None
            if resp.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            log.warning("GET %s -> HTTP %s: %s", path, resp.status_code, resp.text[:200])
            return None
        return None

    # ------------------------------------------------------------------ #
    def search_repositories(self, query: str, *, sort: str = "updated", per_page: int = 50,
                            pages: int = 1) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max(1, pages) + 1):
            resp = self._get(
                "/search/repositories",
                {"q": query, "sort": sort, "order": "desc", "per_page": per_page, "page": page},
                search=True,
            )
            if resp is None:
                break
            items = resp.json().get("items", [])
            out.extend(items)
            if len(items) < per_page:
                break
            # the search endpoint allows 30 req/min; stay well inside it
            time.sleep(2.0)
        return out

    def list_org_repos(self, org: str, *, per_page: int = 30, pages: int = 1) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max(1, pages) + 1):
            resp = self._get(f"/orgs/{org}/repos",
                             {"sort": "created", "direction": "desc", "per_page": per_page, "page": page})
            if resp is None:
                resp = self._get(f"/users/{org}/repos",
                                 {"sort": "created", "direction": "desc", "per_page": per_page, "page": page})
            if resp is None:
                break
            items = resp.json()
            if not isinstance(items, list):
                break
            out.extend(items)
            if len(items) < per_page:
                break
        return out

    def list_user_starred(self, login: str, *, per_page: int = 30, pages: int = 1) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max(1, pages) + 1):
            resp = self._get(f"/users/{login}/starred", {"per_page": per_page, "page": page})
            if resp is None:
                break
            items = resp.json()
            if not isinstance(items, list):
                break
            out.extend(items)
            if len(items) < per_page:
                break
        return out

    def get_user(self, login: str) -> dict | None:
        resp = self._get(f"/users/{login}")
        return resp.json() if resp else None

    def get_repo(self, full_name: str) -> dict | None:
        resp = self._get(f"/repos/{full_name}")
        return resp.json() if resp else None

    def get_readme(self, full_name: str, *, max_chars: int = 8000) -> str:
        resp = self._get(f"/repos/{full_name}/readme")
        if resp is None:
            return ""
        payload = resp.json()
        if payload.get("encoding") != "base64":
            return ""
        try:
            raw = base64.b64decode(payload.get("content", ""))
            return raw.decode("utf-8", errors="replace")[:max_chars]
        except Exception:  # noqa: BLE001 - a malformed readme must never break a run
            return ""

    def rate_limit(self) -> dict:
        resp = self._get("/rate_limit")
        return resp.json() if resp else {}


def normalise_repo(item: dict) -> dict:
    """Map the GitHub repo payload onto our internal shape."""
    owner = item.get("owner") or {}
    licence = item.get("license") or {}
    return {
        "github_id": item.get("id"),
        "full_name": item.get("full_name", ""),
        "owner": owner.get("login", ""),
        "name": item.get("name", ""),
        "html_url": item.get("html_url", ""),
        "description": (item.get("description") or "")[:2000],
        "homepage": (item.get("homepage") or "")[:400],
        "language": (item.get("language") or "")[:60],
        "topics": item.get("topics") or [],
        "license": (licence.get("spdx_id") or "")[:60] if licence else "",
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "watchers": item.get("subscribers_count") or item.get("watchers_count") or 0,
        "open_issues": item.get("open_issues_count") or 0,
        "size_kb": item.get("size") or 0,
        "is_fork": bool(item.get("fork")),
        "is_archived": bool(item.get("archived")),
        "is_template": bool(item.get("is_template")),
        "repo_created_at": parse_dt(item.get("created_at")),
        "repo_pushed_at": parse_dt(item.get("pushed_at")),
        "repo_updated_at": parse_dt(item.get("updated_at")),
        "owner_type": owner.get("type", "User"),
        "owner_avatar": (owner.get("avatar_url") or "")[:400],
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

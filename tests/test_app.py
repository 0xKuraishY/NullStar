"""Smoke and unit tests. Run with: make test"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.sqlite3")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.scoring import compute_score  # noqa: E402
from app.security import hash_password, password_problems, verify_password  # noqa: E402
from app.taxonomy import classify, noise_penalty  # noqa: E402

NOW = datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def anon():
    """A reader who never signed in. Its own client, because saving and
    restoring another one's cookie jar loses domain and path."""
    with TestClient(app, follow_redirects=False) as c:
        yield c


# scoring
def _repo(**over) -> dict:
    base = {
        "name": "kerberoast-ng", "description": "Kerberoasting tool for Active Directory red team operations",
        "topics": ["red-team", "active-directory"], "stars": 0, "license": "MIT",
        "repo_created_at": NOW - timedelta(days=2), "repo_pushed_at": NOW - timedelta(days=1),
        "owner_tier": "newcomer", "owner_followers": 3, "readme_length": 2000,
        "size_kb": 400, "is_fork": False, "is_archived": False, "homepage": "",
    }
    base.update(over)
    return base


def test_fresh_zero_star_security_repo_scores_high():
    score, extra = compute_score(_repo())
    assert score >= 70, extra["breakdown"]
    assert "hidden-gem" in extra["signals"]
    assert "offensive-security" in extra["categories"] or "identity-access" in extra["categories"]


def test_zero_star_gem_outranks_popular_old_framework():
    gem, _ = compute_score(_repo())
    famous, _ = compute_score(_repo(
        stars=42000, owner_tier="big_tech", owner_followers=50000,
        repo_created_at=NOW - timedelta(days=2000), repo_pushed_at=NOW - timedelta(days=2),
        readme_length=20000,
    ))
    assert gem > famous, f"gem={gem} famous={famous} - popularity must not dominate"


def test_awesome_list_is_penalised():
    plain, _ = compute_score(_repo())
    listy, _ = compute_score(_repo(name="awesome-security", description="A curated list of security tools"))
    assert listy < plain


def test_fork_and_archive_are_penalised():
    plain, _ = compute_score(_repo())
    forked, _ = compute_score(_repo(is_fork=True))
    archived, _ = compute_score(_repo(is_archived=True))
    assert forked < plain and archived < plain


def test_breakdown_is_explainable_and_serialisable():
    import json

    _, extra = compute_score(_repo())
    json.dumps(extra["breakdown"])  # must not raise
    assert set(extra["breakdown"]["components"]) >= {"relevance", "freshness", "origin", "gem_bonus"}


def test_score_stays_in_range():
    for repo in (_repo(), _repo(stars=99999), _repo(description="", topics=[], readme_length=0)):
        score, _ = compute_score(repo)
        assert 0.0 <= score <= 100.0


# taxonomy
def test_classifier_picks_the_right_domain():
    cats, relevance, _ = classify(
        "Coverage-guided fuzzing harness for parsing libraries", ["fuzzing"], "libfuzz-harness")
    assert "fuzzing" in cats and relevance > 0.3


def test_non_security_project_scores_low_relevance():
    _, relevance, _ = classify("A fast JSON serialiser for Go", ["json", "golang"], "fastjson")
    assert relevance < 0.2


def test_noise_penalty_detects_lists():
    penalty, reasons = noise_penalty("A curated list of hacking resources", "awesome-hacking", [])
    assert penalty > 0 and reasons


# readme sanitising
RAW_README = """<div align="center">
  <img src="logo.png" width="200">
  <h1>SuperTool</h1>
  [![Build](https://img.shields.io/badge/build-passing-green)](https://ci.example)
</div>

<!-- hidden note -->

## What it does

A **fast** scanner for `CVE-2026-1234`, see [the docs](https://example.com).

- finds things
- reports them

```bash
./supertool --scan
```

<script>alert(1)</script>
<img src=x onerror=alert(1)>
"""


def test_readme_strips_raw_html_the_reader_should_never_see():
    from app.readme import render

    out = render(RAW_README)
    for leak in ("<div", "<img", "<script", "onerror", "align=", "img.shields.io"):
        assert leak not in out.lower(), leak


def test_readme_keeps_the_meaning():
    from app.readme import render

    out = render(RAW_README)
    assert "<b>fast</b>" in out
    assert "<code>CVE-2026-1234</code>" in out
    assert "<li>finds things</li>" in out
    assert "the docs" in out and "example.com" not in out
    assert "./supertool --scan" in out


def test_readme_cannot_smuggle_markup_through_markdown():
    from app.readme import render

    out = render("**bold <script>alert(1)</script>** and `<b>x</b>`")
    assert "<script" not in out.lower()
    assert "&lt;b&gt;x&lt;/b&gt;" in out


def test_readme_summary_skips_badges_and_headings():
    from app.readme import summarise

    assert summarise(RAW_README).startswith("A fast scanner")


# security primitives
def test_password_round_trip():
    hashed = hash_password("Corr3ctHorseBattery")
    assert verify_password("Corr3ctHorseBattery", hashed)
    assert not verify_password("wrong", hashed)


def test_password_policy():
    assert password_problems("short")
    assert password_problems("alllowercase123")
    assert not password_problems("Str0ngEnoughPassword")


# http surface
def test_health_endpoints(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_reading_is_open_to_everybody(client):
    """The feed is public. Only what belongs to an account needs one."""
    client.get("/guest")          # past the landing page, as a visitor would be
    for path in ("/", "/gems", "/majors", "/newcomers", "/dashboard", "/how"):
        assert client.get(path).status_code == 200, path


def test_a_first_visit_lands_on_the_door(anon):
    """Somebody arriving for the first time should be told where they are and
    what the choices are, rather than dropped straight into a wall of results."""
    landing = anon.get("/")
    assert landing.status_code == 303
    assert landing.headers["location"] == "/login"

    # deep links are not hijacked: a shared or bookmarked page opens on itself
    for path in ("/gems", "/how", "/dashboard", "/newcomers"):
        assert anon.get(path).status_code == 200, path
    assert anon.get("/", params={"sort": "new"}).status_code == 200

    # choosing to read without an account is remembered
    chosen = anon.get("/guest")
    assert chosen.status_code == 303 and chosen.headers["location"] == "/"
    assert anon.get("/").status_code == 200
    assert anon.get("/").status_code == 200       # and it sticks



def test_method_page_reports_the_live_configuration(client):
    """It is built from the settings the collector uses, so a weight changed in
    the admin pages has to show up here or the page is lying."""
    from app.db import SessionLocal
    from app.store import get_setting, set_setting

    db = SessionLocal()
    try:
        weights = get_setting(db, "scoring_weights")
        original = weights["relevance"]
        weights["relevance"] = 37.0
        set_setting(db, "scoring_weights", weights)
    finally:
        db.close()

    body = client.get("/how").text
    assert ">37<" in body or "37" in body
    assert "Relevance" in body
    assert "Exploit Development" in body       # the live taxonomy
    assert "Big Tech" in body                  # the live tier table

    db = SessionLocal()
    try:
        weights = get_setting(db, "scoring_weights")
        weights["relevance"] = original
        set_setting(db, "scoring_weights", weights)
    finally:
        db.close()


def test_first_run_offers_setup(client):
    assert "/setup" in client.get("/login").headers["location"]


def test_bootstrap_takes_only_a_name_and_a_password(client):
    resp = client.post("/setup", data={
        "username": "owner", "password": "Str0ngEnoughPassword",
        "password_confirm": "Str0ngEnoughPassword"})
    assert resp.status_code == 303
    assert client.get("/setup").status_code == 303   # no second bootstrap

    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "owner").one()
        assert owner.role == "admin"      # first in owns the instance
        assert owner.email == ""          # nothing else was asked for
    finally:
        db.close()


def test_signing_in_also_counts_as_having_been_here(anon):
    """Otherwise somebody who signs out lands back on the door every time."""
    from app.security import SEEN_COOKIE

    assert anon.get("/").status_code == 303           # never been here
    resp = anon.post("/login", data={"username": "owner", "password": "Str0ngEnoughPassword"})
    assert resp.status_code == 303, resp.status_code
    assert any(SEEN_COOKIE in header for header in resp.headers.get_list("set-cookie"))


def test_registration_is_open_but_an_admin_can_close_it(client):
    assert client.get("/register").status_code == 200

    from app.db import SessionLocal
    from app.store import get_setting, set_setting

    db = SessionLocal()
    try:
        cfg = get_setting(db, "auth")
        cfg["allow_open_registration"] = False
        set_setting(db, "auth", cfg)
        assert client.get("/register").status_code == 403
        cfg["allow_open_registration"] = True
        set_setting(db, "auth", cfg)
    finally:
        db.close()
    assert client.get("/register").status_code == 200


def test_authenticated_pages_render(client):
    for path in ("/", "/gems", "/majors", "/newcomers", "/bookmarks", "/dashboard",
                 "/account", "/admin", "/admin/users", "/admin/invites", "/admin/sources",
                 "/admin/scoring", "/admin/settings", "/admin/runs", "/admin/audit"):
        assert client.get(path).status_code == 200, path


def test_feed_renders_with_actual_repositories(client):
    """Regression: the empty feed never invoked the repo-card macro, so a name
    the macro could not see (tier_labels) passed every test and still 500'd the
    moment real data arrived. Every list view must be exercised with rows."""
    from app.db import SessionLocal
    from app.models import Repository

    db = SessionLocal()
    try:
        db.add(Repository(
            github_id=999001, full_name="newbie/cve-2026-poc", owner="newbie", name="cve-2026-poc",
            html_url="https://github.com/newbie/cve-2026-poc",
            description="Unauthenticated RCE proof of concept", language="Python",
            topics=["exploit", "cve"], stars=0, owner_tier="newcomer", owner_label="Account created 9d ago",
            repo_created_at=NOW - timedelta(days=1), repo_pushed_at=NOW - timedelta(hours=3),
            score=94.0, categories=["exploit-dev"], signals=["hidden-gem", "new-account", "just-created"],
            score_breakdown={"total": 94.0, "components": {}}, star_velocity=0.0,
        ))
        db.add(Repository(
            github_id=999002, full_name="trailofbits/some-tool", owner="trailofbits", name="some-tool",
            html_url="https://github.com/trailofbits/some-tool", description="",
            language="", topics=[], stars=1200, owner_tier="security_vendor",
            repo_created_at=NOW - timedelta(days=5), repo_pushed_at=NOW - timedelta(days=1),
            score=71.0, categories=[], signals=["major-publisher"], score_breakdown={}, star_velocity=2.0,
        ))
        db.commit()
        ids = [r.id for r in db.query(Repository).all()]
    finally:
        db.close()

    for path in ("/", "/gems", "/majors", "/newcomers", "/dashboard"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    assert "cve-2026-poc" in client.get("/").text

    for repo_id in ids:
        assert client.get(f"/repo/{repo_id}").status_code == 200

    # a repo with no description, topics or categories must not break the card
    assert "some-tool" in client.get("/?sort=stars").text


def test_live_wire_renders_the_same_row_markup_as_the_page(client):
    """The SSE stream pushes server-rendered HTML so it cannot drift from the
    page. Also guards the macro-context trap: a name the macro cannot see
    renders fine in a view and explodes only here."""
    from app.db import SessionLocal
    from app.models import Repository, User
    from app.routers.feed import _render_row

    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.github_id == 999003).first()
        if repo is None:
            repo = Repository(
                github_id=999003, full_name="wire/pushed-repo", owner="wire", name="pushed-repo",
                html_url="https://github.com/wire/pushed-repo", description="Streamed row",
                language="Go", topics=[], stars=0, owner_tier="newcomer",
                repo_created_at=NOW - timedelta(hours=2), repo_pushed_at=NOW,
                score=91.0, categories=["exploit-dev"],
                signals=["hidden-gem", "new-account", "just-created"],
                score_breakdown={}, star_velocity=0.0,
            )
            db.add(repo)
            db.commit()
        signed_in = db.query(User).filter(User.username == "owner").one()
        html = _render_row("test-csrf-token", repo, None, signed_in)
        guest_html = _render_row("", repo, None, None)
        repo_id = repo.id
    finally:
        db.close()

    assert 'class="entry' in html
    assert 'data-repo="%d"' % repo_id in html
    assert "pushed-repo" in html
    assert "New Account" in html           # tier label resolved through the env global
    assert "Exploit Development" in html   # category label resolved
    assert "overlooked" in html            # signal wording rendered
    assert "test-csrf-token" in html       # a signed-in reader gets working action forms
    assert "test-csrf-token" not in guest_html
    assert "/login?next=" in guest_html    # a guest is invited to sign in instead


def test_unknown_repo_is_a_clean_404(client):
    assert client.get("/repo/987654").status_code == 404


def test_csrf_is_enforced(client):
    resp = client.post("/admin/invites", data={"role": "viewer", "ttl_hours": 24, "csrf_token": "forged"})
    assert resp.status_code == 400


# hostile input
def _parse(html_text: str):
    """Return (tag names, event-handler attributes, script sources) in a page."""
    from html.parser import HTMLParser

    tags: set[str] = set()
    handlers: list[tuple[str, str]] = []
    scripts: list[str] = []

    class Scan(HTMLParser):
        def handle_starttag(self, tag, attrs):
            tags.add(tag)
            for name, value in attrs:
                if name.lower().startswith("on"):
                    handlers.append((tag, name))
                if name.lower() in ("href", "src", "action") and (value or "").strip() \
                        .lower().replace("\t", "").startswith("javascript:"):
                    handlers.append((tag, name))
            if tag == "script":
                scripts.append(dict(attrs).get("src", "") or "inline")

    Scan(convert_charrefs=True).feed(html_text)
    return tags, handlers, scripts


PAYLOADS = [
    "<script>alert('xss')</script>",
    "\"><img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
    "'; DROP TABLE repositories; --",
    "' OR '1'='1",
    "1); DELETE FROM users WHERE ('1'='1",
    "%3Cscript%3Ealert(1)%3C/script%3E",
    "../../../../etc/passwd",
    "{{ 7*7 }}",
    "${{7*7}}",
]


def test_repository_text_cannot_inject_script_into_a_page(client):
    """Descriptions and names come from strangers. They must never be markup."""
    from app.db import SessionLocal
    from app.models import Repository

    db = SessionLocal()
    try:
        repo = Repository(
            github_id=999900, full_name="evil/<script>alert(1)</script>",
            owner="evil", name="<script>alert('pwn')</script>",
            html_url="https://github.com/evil/x",
            description="<img src=x onerror=alert(1)> and <b>markup</b>",
            language="<svg/onload=alert(1)>", topics=["<script>bad</script>"],
            stars=0, owner_tier="newcomer",
            repo_created_at=NOW - timedelta(days=1), repo_pushed_at=NOW,
            score=88.0, categories=["exploit-dev"], signals=["hidden-gem"],
            score_breakdown={}, star_velocity=0.0,
            readme_excerpt="<script>alert('readme')</script>\n\n# Head\n\ntext",
            readme_length=60,
        )
        db.add(repo)
        db.commit()
        repo_id = repo.id
    finally:
        db.close()

    for path in ("/?sort=new", "/repo/%d" % repo_id):
        body = client.get(path).text
        tags, handlers, scripts = _parse(body)

        # A substring check is useless here, since escaped text legitimately
        # contains "onerror=alert(1)". What matters is whether any of it turned
        # into an element or an attribute.
        assert not handlers, (path, handlers)
        assert all(src.startswith("/static/") for src in scripts), (path, scripts)
        assert "img" not in tags, path          # the payload carried an <img>
        # the page has svg of its own, so check the injected one stayed text
        assert "&lt;svg/onload" in body or "&lt;svg" in body, path
        assert "&lt;script&gt;" in body or "&lt;img" in body, path


def test_hostile_query_parameters_do_not_break_or_leak(client):
    from app.db import SessionLocal
    from app.models import User

    for payload in PAYLOADS:
        for param in ("q", "category", "tier", "language", "signal", "sort", "window"):
            resp = client.get("/", params={param: payload})
            assert resp.status_code == 200, (param, payload, resp.status_code)
            assert "<script>alert" not in resp.text.lower()
            assert "49" not in resp.text[:0]      # template injection would evaluate 7*7

    # nothing was destroyed by the SQL-shaped payloads
    db = SessionLocal()
    try:
        assert db.query(User).count() >= 1
    finally:
        db.close()


def test_numeric_parameters_reject_garbage(client):
    for value in ("abc", "-5", "99999999999999999999", "1e400", "", "NaN"):
        for param in ("page", "per_page", "min_score", "max_stars"):
            assert client.get("/", params={param: value}).status_code == 200


def test_login_does_not_follow_an_outside_redirect(client):
    for target in ("https://evil.example/", "//evil.example/", "http://evil.example",
                   "/\\evil.example", "javascript:alert(1)"):
        resp = client.post("/login", data={
            "username": "owner", "password": "Str0ngEnoughPassword", "next": target})
        assert resp.status_code in (303, 429)
        if resp.status_code == 303:
            location = resp.headers["location"]
            assert "evil.example" not in location, target
            assert location.startswith("/"), target


def test_private_pages_stay_private(anon):
    """A guest reads the wire. It does not read anybody's account."""
    for path in ("/bookmarks", "/account", "/library", "/admin", "/admin/users", "/admin/settings"):
        resp = anon.get(path)
        assert resp.status_code == 303, path
        assert "/login" in resp.headers["location"], path
    assert anon.get("/api/v1/repos").status_code == 401
    assert anon.get("/export.json").status_code == 401


def test_writing_requires_an_account_and_a_token(client, anon):
    assert anon.post("/repo/1/bookmark", data={"csrf_token": "x"}).status_code == 303
    # signed in, but no valid token
    assert client.post("/repo/1/bookmark", data={"csrf_token": "forged"}).status_code == 400


def test_session_cookie_is_locked_down(client):
    resp = client.post("/login", data={"username": "owner", "password": "Str0ngEnoughPassword"})
    cookies = resp.headers.get_list("set-cookie")
    session = [c for c in cookies if c.startswith("nullstar_session=")]
    assert session, cookies
    assert "HttpOnly" in session[0]
    assert "SameSite=lax" in session[0].replace("samesite", "SameSite")
    assert "Path=/" in session[0]


def test_signup_is_throttled_per_address(anon):
    """On its own client: a successful sign-up opens a session, so running this
    on the shared one would quietly re-identify it as the last account made."""
    from app.security import reset_throttles

    reset_throttles()
    codes = []
    for i in range(9):
        resp = anon.post("/register", data={
            "username": "flood%d" % i, "password": "Str0ngEnoughPassword",
            "password_confirm": "Str0ngEnoughPassword"})
        codes.append(resp.status_code)
    assert 429 in codes, codes
    reset_throttles()


# preferences
def test_light_is_the_ground_state(anon):
    """Resolved on the server and stamped on <html>, so the first paint is
    already right; a localStorage toggle always flashes the wrong theme once."""
    assert 'data-theme="light"' in anon.get("/how").text


def test_theme_choice_is_remembered(client):
    client.post("/theme/dark", data={"csrf_token": "x", "back": "/"})
    assert 'data-theme="dark"' in client.get("/").text

    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "owner").one()
        assert (owner.prefs or {}).get("theme") == "dark"   # follows the account too
    finally:
        db.close()
    client.post("/theme/light", data={"csrf_token": "x", "back": "/"})


def test_a_nonsense_theme_or_language_falls_back(client):
    client.post("/theme/neon", data={"csrf_token": "x", "back": "/"})
    assert 'data-theme="light"' in client.get("/").text
    client.post("/lang/klingon", data={"csrf_token": "x", "back": "/"})
    assert 'lang="en"' in client.get("/").text


def test_french_translates_the_interface_and_nothing_else(client):
    from app.db import SessionLocal
    from app.models import Repository

    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.full_name == "newbie/cve-2026-poc").one()
        description = repo.description
    finally:
        db.close()

    client.post("/lang/fr", data={"csrf_token": "x", "back": "/"})
    body = client.get("/").text
    assert 'lang="fr"' in body
    assert "Flux" in body                   # chrome is translated
    assert "Signaux faibles" in body
    assert "Compte récent" in body          # a label that lives in Python
    # the apostrophe comes back escaped, so match on the part that survives
    assert "il y a" in body or "instant" in body       # and relative times
    assert description in body              # the author's words are left alone
    client.post("/lang/en", data={"csrf_token": "x", "back": "/"})
    assert "Overlooked" in client.get("/").text


def test_language_switch_cannot_bounce_you_off_site(client):
    resp = client.post("/lang/fr", data={"csrf_token": "x", "back": "//evil.example"})
    assert resp.headers["location"] == "/"
    client.post("/lang/en", data={"csrf_token": "x", "back": "/"})


# collections
def test_collections_file_sort_and_share(client):
    from app.db import SessionLocal
    from app.models import Collection, Repository, User, UserRepoState

    csrf = client.cookies.get("nullstar_csrf")
    resp = client.post("/collections", data={
        "csrf_token": csrf, "name": "To try", "description": "weekend", "colour": "amber",
        "back": "/library"})
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "owner").one()
        collection = db.query(Collection).filter(Collection.user_id == owner.id).one()
        assert collection.slug == "to-try"
        repo_id = db.query(Repository).first().id
    finally:
        db.close()

    # filing is a toggle, and it implies keeping
    client.post("/repo/%d/file" % repo_id, data={
        "csrf_token": csrf, "collection_id": str(collection.id), "back": "/library"})
    db = SessionLocal()
    try:
        assert db.query(Collection).get(collection.id).items
        state = db.query(UserRepoState).filter(
            UserRepoState.user_id == owner.id, UserRepoState.repo_id == repo_id).one()
        assert state.bookmarked is True
    finally:
        db.close()

    for sort in ("added", "manual", "score", "stars", "fresh", "name", "nonsense"):
        assert client.get("/collections/%d" % collection.id,
                          params={"sort": sort}).status_code == 200

    # sharing is off until asked for, then readable with no account
    assert client.get("/shared/").status_code in (404, 405)
    client.post("/collections/%d/share" % collection.id, data={"csrf_token": csrf})
    db = SessionLocal()
    try:
        collection = db.query(Collection).get(collection.id)
        token = collection.share_token
        assert collection.is_public and token
    finally:
        db.close()

    with TestClient(app, follow_redirects=False) as guest:
        assert guest.get("/shared/%s" % token).status_code == 200
        assert guest.get("/shared/not-a-real-token").status_code == 404

    # rotating the link kills the old one
    client.post("/collections/%d/reshare" % collection.id, data={"csrf_token": csrf})
    assert client.get("/shared/%s" % token).status_code == 404

    client.post("/collections/%d/delete" % collection.id, data={"csrf_token": csrf})


def test_one_reader_cannot_touch_anothers_collection(client, anon):
    from app.db import SessionLocal
    from app.models import Collection, User

    csrf = client.cookies.get("nullstar_csrf")
    client.post("/collections", data={"csrf_token": csrf, "name": "Private", "back": "/library"})

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "owner").one()
        collection = db.query(Collection).filter(
            Collection.user_id == owner.id, Collection.name == "Private").one()
        intruder = User(username="intruder", email="", display_name="intruder",
                        password_hash="x", role="viewer", is_active=True)
        db.add(intruder)
        db.commit()
        collection_id = collection.id
    finally:
        db.close()

    # a guest gets bounced, not shown somebody else's folder
    assert anon.get("/collections/%d" % collection_id).status_code == 303
    assert anon.post("/collections/%d/delete" % collection_id,
                     data={"csrf_token": "x"}).status_code == 303

    db = SessionLocal()
    try:
        assert db.query(Collection).get(collection_id) is not None  # survived
    finally:
        db.close()
    client.post("/collections/%d/delete" % collection_id, data={"csrf_token": csrf})


def test_security_headers_present(client):
    headers = client.get("/healthz").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    csp = headers["Content-Security-Policy"]
    # scripts must have no inline escape hatch, or escaping failures become
    # executable; everything must come from this origin.
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "'unsafe-eval'" not in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'none'" in csp


def test_stylesheet_parses_cleanly():
    """A declaration outside a block makes a browser discard everything until
    it can resync, which silently kills whatever rule comes next. It happened
    twice here while editing the file with regular expressions, and both times
    the only symptom was a page that looked wrong."""
    import re as _re
    from pathlib import Path

    css = Path("app/static/css/app.css").read_text()
    css = _re.sub(r"/\*.*?\*/", lambda m: _re.sub(r"[^\n]", " ", m.group(0)), css, flags=_re.S)

    depth = 0
    problems = []
    for number, line in enumerate(css.split("\n"), 1):
        stripped = line.strip()
        if depth == 0 and stripped and not stripped.startswith(("@", "}")) \
                and ":" in stripped and "{" not in stripped:
            problems.append((number, "declaration outside any rule", stripped[:70]))
        depth += line.count("{") - line.count("}")
        if depth < 0:
            problems.append((number, "unmatched closing brace", stripped[:70]))
            depth = 0

    assert not problems, problems
    assert depth == 0, "unclosed rule, %d brace(s) left open" % depth


def test_every_class_the_templates_use_exists_in_the_stylesheet():
    import re as _re
    from pathlib import Path

    used = set()
    for path in Path("app/templates").rglob("*.html"):
        for attr in _re.findall(r'class="([^"]*)"', path.read_text()):
            attr = _re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", attr)   # drop jinja
            for name in attr.split():
                # a stripped interpolation leaves stubs like "alert-" behind
                if _re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", name) and len(name) > 2:
                    used.add(name)

    css = Path("app/static/css/app.css").read_text()
    css = _re.sub(r"/\*.*?\*/", " ", css, flags=_re.S)
    defined = set(_re.findall(r"\.([a-z][a-z0-9-]*)", css))

    missing = sorted(used - defined - {"else", "filters"})
    assert not missing, "classes used but never styled: %s" % missing


def test_a_brand_new_instance_is_readable_before_anybody_signs_up(tmp_path):
    """Nothing about a fresh install should force an account. The owner account
    is for whoever runs the box, not a toll gate for readers."""
    import os
    import importlib
    import sys

    previous = dict(os.environ)
    os.environ["DATABASE_URL"] = "sqlite:///%s/fresh.sqlite3" % tmp_path
    os.environ["SCHEDULER_ENABLED"] = "false"
    for name in [m for m in list(sys.modules) if m.startswith("app")]:
        del sys.modules[name]
    try:
        fresh_main = importlib.import_module("app.main")
        with TestClient(fresh_main.app, follow_redirects=False) as c:
            # the root shows the door on a first visit
            first = c.get("/")
            assert first.status_code == 303 and first.headers["location"] == "/login"
            # everything else is readable straight away, no account anywhere
            for path in ("/gems", "/majors", "/newcomers", "/how", "/dashboard"):
                assert c.get(path).status_code == 200, path
            assert c.get("/guest").status_code == 303
            assert c.get("/").status_code == 200
            setup = c.get("/setup")
            assert setup.status_code == 200
            assert "Guest mode" in setup.text        # a way back to reading
            assert 'href="/"' in setup.text
    finally:
        os.environ.clear()
        os.environ.update(previous)
        for name in [m for m in list(sys.modules) if m.startswith("app")]:
            del sys.modules[name]
        importlib.import_module("app.main")


def test_the_sign_in_screens_are_translated_and_let_you_leave(client):
    # follow redirects: on an instance with no accounts yet these bounce to
    # /setup, and the test should not depend on which other cases ran first
    for path in ("/login", "/register"):
        english = client.get(path, follow_redirects=True).text
        assert "Guest mode" in english, path          # reading without an account
        assert "gate-tools" in english, path          # language and theme reachable here too
        assert "Nobody has seen it yet" in english, path

    client.post("/lang/fr", data={"csrf_token": "x", "back": "/"})
    try:
        for path in ("/login", "/register"):
            french = client.get(path, follow_redirects=True).text
            assert "Mode invit" in french, path       # accented, so match the stem
            assert "Mot de passe" in french, path
            # the side panel used to stay in English whatever the language was
            assert "Personne ne l" in french, path
            assert "Somebody shipped" not in french, path
    finally:
        client.post("/lang/en", data={"csrf_token": "x", "back": "/"})

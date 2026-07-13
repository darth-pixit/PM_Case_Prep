"""Tests for the multi-experiment expansion: shared auth, the arena case bank,
per-experiment routes, and the recruiter knowledge base. Offline — no network,
no real Google/Resend/Anthropic calls."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep import rubric  # noqa: E402
from pmcaseprep.case_loader import (  # noqa: E402
    arena_case_by_id,
    arena_case_paths,
    arena_catalog,
    arena_categories,
    load_case,
)
from pmcaseprep.recruiter_kb import GUIDE, recruiter_guide, recruiter_system_prompt  # noqa: E402


# --- Auth codes -----------------------------------------------------------------

def test_auth_codes_lifecycle(tmp_path):
    from pmcaseprep.web.auth import CODE_MAX_ATTEMPTS, AuthCodes

    db = tmp_path / "auth.db"
    codes = AuthCodes(db)
    code = codes.issue("p@example.com")
    assert len(code) == 6 and code.isdigit()

    # Wrong guesses burn attempts but not the code…
    for _ in range(CODE_MAX_ATTEMPTS - 1):
        assert not codes.verify("p@example.com", "000000")
    # …the right code still works, once, then it's gone.
    assert codes.verify("p@example.com", code)
    assert not codes.verify("p@example.com", code)

    # Too many wrong guesses burn the code entirely.
    code2 = codes.issue("p@example.com")
    for _ in range(CODE_MAX_ATTEMPTS):
        codes.verify("p@example.com", "000000")
    assert not codes.verify("p@example.com", code2)

    # A reissue replaces the old code.
    a = codes.issue("q@example.com")
    b = codes.issue("q@example.com")
    if a != b:  # randomly equal is possible but astronomically unlikely
        assert not codes.verify("q@example.com", a)
        codes.issue("q@example.com")  # burned by the failed check above? re-issue
    codes.close()


def test_auth_codes_expire(tmp_path, monkeypatch):
    from pmcaseprep.web import auth as auth_mod

    codes = auth_mod.AuthCodes(tmp_path / "auth.db")
    code = codes.issue("p@example.com")
    real_time = time.time
    monkeypatch.setattr(auth_mod.time, "time", lambda: real_time() + auth_mod.CODE_TTL_S + 1)
    assert not codes.verify("p@example.com", code)
    codes.close()


def test_google_verify_off_without_client_id():
    from pmcaseprep.web.auth import verify_google_token

    # No PMCP_GOOGLE_CLIENT_ID in the test env -> the door is simply closed.
    assert verify_google_token("some-jwt") is None
    assert verify_google_token("") is None


def test_google_verify_fails_closed_and_never_raises(monkeypatch):
    """With a client id set but the verifier unavailable (no
    google-auth[requests] on the box) OR a bogus token, verification must fail
    CLOSED — return None, never raise — so the endpoint answers 401, not 500."""
    from pmcaseprep.web import auth as auth_mod

    monkeypatch.setattr(auth_mod, "GOOGLE_CLIENT_ID", "fake.apps.googleusercontent.com")
    assert auth_mod.verify_google_token("not-a-real-token") is None


def test_email_validation():
    from pmcaseprep.web.auth import valid_email

    assert valid_email("a@b.co")
    assert not valid_email("nope")
    assert not valid_email("a@b")
    assert not valid_email("a" * 250 + "@b.co")


# --- Arena case bank --------------------------------------------------------------

def test_arena_bank_is_stocked():
    """5 categories x 5 cases, every one valid, complete, and original-schema."""
    cats = arena_categories()
    assert len(cats) == 5, "the arena promises exactly 5 PM tracks"
    keys = [c["key"] for c in cats]
    assert len(set(keys)) == 5
    for c in cats:
        assert c["name"] and c["blurb"] and c["icon"]
        # Grading must go through a tuned lens for every track.
        assert c["key"] in rubric.ARCHETYPE_WEIGHTS, f"no rubric tilt for {c['key']}"

    paths = arena_case_paths()
    assert len(paths) == 25, f"expected 25 arena cases, found {len(paths)}"
    seen_ids = set()
    per_cat: dict[str, int] = {}
    for p in paths:
        case = load_case(p)
        assert case.id not in seen_ids, f"duplicate case id {case.id}"
        seen_ids.add(case.id)
        per_cat[case.archetype] = per_cat.get(case.archetype, 0) + 1
        # Every case must be fully playable AND gradable:
        assert case.archetype in keys, f"{case.id}: unknown category {case.archetype}"
        assert case.type in rubric.CATEGORY_CHECKLISTS, f"{case.id}: unknown type {case.type}"
        assert len(case.prompt) > 100, f"{case.id}: prompt too thin"
        assert len(case.hidden_facts) >= 5, f"{case.id}: interviewer needs hidden facts"
        assert len(case.ideal_answer_notes) >= 5, f"{case.id}: grader needs ideal notes"
        assert case.anchors is not None, f"{case.id}: grading needs anchors"
        assert case.teaser, f"{case.id}: arena card needs a teaser"
        assert case.extra_checklist, f"{case.id}: needs case-specific checklist items"
    assert all(n == 5 for n in per_cat.values()), f"uneven categories: {per_cat}"


def test_arena_catalog_is_browser_safe():
    """The catalog JSON goes straight to the browser — it must never leak
    hidden facts, grader notes, or anchors."""
    catalog = arena_catalog()
    for cat in catalog:
        for case in cat["cases"]:
            assert set(case) == {"id", "title", "type", "teaser", "minutes"}


def test_arena_case_lookup():
    paths = arena_case_paths()
    if not paths:
        return
    first = load_case(paths[0])
    assert arena_case_by_id(first.id) is not None
    assert arena_case_by_id("no-such-case") is None
    assert arena_case_by_id("../../etc/passwd") is None


def test_arena_resource_tags_resolve():
    from pmcaseprep.resources import RESOURCES

    for p in arena_case_paths():
        case = load_case(p)
        for tag in case.resource_tags:
            assert tag in RESOURCES, f"{case.id} tags unknown resource {tag}"


# --- Recruiter knowledge base ------------------------------------------------------

def test_recruiter_kb_shape():
    g = recruiter_guide()
    assert set(g) >= {"roles", "archetypes", "concepts", "evaluation", "resources"}
    assert g["roles"], "KB must cover at least one role family"
    assert len(g["archetypes"]) >= 8, "KB should map the real interview landscape"
    assert len(g["concepts"]) >= 12
    assert len(g["evaluation"]) >= 4
    assert len(g["resources"]) >= 20
    for a in g["archetypes"]:
        assert a["name"] and a["description"] and a["example_questions"]
        assert a["good"] and a["bad"]
    for c in g["concepts"]:
        assert c["name"] and len(c["plain_english"]) > 60, c["name"]
        assert c["why_asked"]
    for r in g["resources"]:
        assert r["url"].startswith("https://"), r
        assert r["title"] and r["why"] and r["topic"] and r["kind"] and r["time"]


def test_recruiter_system_prompt_grounded():
    p = recruiter_system_prompt()
    assert "KNOWLEDGE BASE" in p
    if GUIDE["concepts"]:
        assert GUIDE["concepts"][0]["name"] in p


# --- Web endpoints ------------------------------------------------------------------

def _client(tmp_path, monkeypatch):
    try:
        from fastapi.testclient import TestClient

        from pmcaseprep.web import app as webapp
    except ImportError:
        return None, None
    monkeypatch.setattr(webapp, "DB_PATH", str(tmp_path / "web.db"))
    monkeypatch.setenv("PMCP_DEV_DOCS", "1")  # dev email door for tests
    return TestClient(webapp.app), webapp


def test_config_exposes_auth_flags(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    cfg = client.get("/config").json()
    assert "google_client_id" in cfg and "email_login" in cfg
    assert cfg["email_login"] is True  # dev mode


def test_email_code_login_flow(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    client.get("/")  # get a uid cookie
    r = client.post("/api/auth/email/request", json={"email": "p@example.com"})
    d = r.json()
    assert d["ok"] and d.get("dev_code"), "dev mode must return the code"
    r = client.post(
        "/api/auth/email/verify", json={"email": "p@example.com", "code": d["dev_code"]}
    )
    assert r.json()["ok"]
    assert client.get("/api/me").json()["email"] == "p@example.com"
    # Wrong code must not log in.
    client.post("/api/auth/email/request", json={"email": "x@example.com"})
    r = client.post(
        "/api/auth/email/verify", json={"email": "x@example.com", "code": "000000"}
    )
    assert r.status_code == 401


def test_google_failure_message_matches_available_doors(tmp_path, monkeypatch):
    """The Google-failure message must only point to the email door when that
    door actually exists — a Google-only deploy renders no email field, so
    'try the email code instead' would be a dead end there."""
    client, webapp = _client(tmp_path, monkeypatch)
    if client is None:
        return
    monkeypatch.setattr(webapp.auth, "GOOGLE_CLIENT_ID", "fake.apps.googleusercontent.com")
    monkeypatch.setattr(webapp.auth, "RESEND_API_KEY", "")
    client.get("/arena")  # uid cookie

    # Email door ON (dev mode) -> the failure points to it.
    r = client.post("/api/auth/google", json={"credential": "not-a-real-token"})
    assert r.status_code == 401
    assert "email" in r.json()["error"].lower()

    # Email door OFF (Google-only deploy: RENDER set, no Resend key) -> the
    # message must NOT advertise a door the widget never rendered.
    monkeypatch.setenv("RENDER", "1")
    r = client.post("/api/auth/google", json={"credential": "not-a-real-token"})
    assert r.status_code == 401
    assert "email" not in r.json()["error"].lower()
    assert "google sign-in failed" in r.json()["error"].lower()


def test_arena_room_is_login_gated(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    paths = arena_case_paths()
    if not paths:
        return
    case_id = load_case(paths[0]).id
    client.get("/arena")  # uid cookie
    r = client.get(f"/arena/room?case={case_id}", follow_redirects=False)
    assert r.status_code in (302, 307) and "/arena" in r.headers["location"]
    # Bogus case ids bounce to the picker even when signed in.
    d = client.post("/api/auth/email/request", json={"email": "p@example.com"}).json()
    client.post("/api/auth/email/verify", json={"email": "p@example.com", "code": d["dev_code"]})
    r = client.get("/arena/room?case=../../evil", follow_redirects=False)
    assert r.status_code in (302, 307)
    r = client.get(f"/arena/room?case={case_id}")
    assert r.status_code == 200
    assert 'PMCP_EXPERIMENT="arena"' in r.text
    assert f'PMCP_CASE_ID="{case_id}"' in r.text


def test_legacy_login_cannot_claim_verified_account(tmp_path, monkeypatch):
    """The unverified tutor login must never hand over an EXISTING account —
    that cookie now unlocks the login-gated arena/recruiter endpoints."""
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    # Victim signs in through the verified door.
    client.get("/")
    d = client.post("/api/auth/email/request", json={"email": "victim@example.com"}).json()
    client.post(
        "/api/auth/email/verify", json={"email": "victim@example.com", "code": d["dev_code"]}
    )
    # Attacker (fresh cookies) types the victim's email at the tutor box.
    client.cookies.clear()
    client.get("/")
    r = client.post("/api/login", json={"email": "victim@example.com"})
    assert r.status_code == 409
    assert client.get("/api/me").json()["email"] is None
    # A NEW email still links fine (the "save my progress" happy path).
    r = client.post("/api/login", json={"email": "fresh@example.com"})
    assert r.json()["ok"]


def test_recruiter_chat_requires_login(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    client.get("/recruiter")
    r = client.post("/api/recruiter/chat", json={"messages": [{"role": "user", "text": "hi"}]})
    assert r.status_code == 401


def test_experiment_pages_served(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    for path, marker in (
        ("/arena", "Case Arena"),
        ("/recruiter", "Recruiter Copilot"),
        ("/referrals", "Referral Paths"),
    ):
        r = client.get(path)
        assert r.status_code == 200 and marker in r.text, path
    guide = client.get("/api/recruiter/guide").json()
    assert "archetypes" in guide


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

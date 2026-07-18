"""Tests for referral pods — the opt-in multiplayer layer of /referrals.

The privacy contract is the point of most of these tests: the server must
only ever accept hash-shaped connection rows, must drop email-shaped company
strings, must answer counts (never names — it has none by construction), and
must delete a member's rows when they leave. Offline — no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAKE_HASH = "a" * 64
OTHER_HASH = "b" * 64


# --- The store itself --------------------------------------------------------------

def test_pods_store_lifecycle(tmp_path):
    from pmcaseprep.web.pods import Pods

    p = Pods(tmp_path / "pods.db")
    pod, err = p.create("IITD job squad", "a@x.co")
    assert err is None and len(pod["code"]) == 6

    # Codes avoid lookalike characters entirely.
    assert not set(pod["code"]) & set("01OIL")

    joined, err = p.join(pod["code"].lower(), "b@x.co")  # case-insensitive
    assert err is None and joined["name"] == "IITD job squad"
    # Re-joining is idempotent, not an error.
    again, err = p.join(pod["code"], "b@x.co")
    assert err is None

    mine = p.mine("b@x.co")
    assert len(mine) == 1 and mine[0]["members"] == 2

    # Unknown code is a clean error.
    nope, err = p.join("ZZZZZZ", "c@x.co")
    assert nope is None and "no pod" in err

    # Leaving deletes membership; last one out deletes the pod row too.
    assert p.leave(pod["code"], "b@x.co")
    assert p.leave(pod["code"], "a@x.co")
    assert p.mine("a@x.co") == []
    nope, err = p.join(pod["code"], "c@x.co")
    assert nope is None  # pod is gone
    p.close()


def test_pods_graph_validation_is_the_privacy_floor(tmp_path):
    from pmcaseprep.web.pods import Pods

    p = Pods(tmp_path / "pods.db")
    pod, _ = p.create("squad", "a@x.co")
    code = pod["code"]

    # Anything that isn't a 64-hex hash is rejected outright — names, URLs,
    # emails can never be smuggled in through the hash field.
    for bad in ["Parth Dixit", "https://linkedin.com/in/x", "a" * 63, "Z" * 64, 5, None]:
        res, err = p.set_graph(code, "a@x.co", [], [{"h": bad, "c": "stripe"}])
        assert res is None and "hash" in err

    # Email-shaped company strings are dropped, valid rows kept.
    res, err = p.set_graph(
        code, "a@x.co",
        [{"company": "Flipkart", "current": True}, {"company": "leak@evil.co"}],
        [{"h": FAKE_HASH, "c": "Stripe"}, {"h": OTHER_HASH, "c": "victim@gmail.com"}],
    )
    assert err is None and res["shared"] == 2
    assert res["companies"] == 1  # the email-shaped "company" was dropped

    summary, err = p.summary(code, "a@x.co")
    me = summary["members"][0]
    assert me["companies"] == [{"company": "flipkart", "current": True}]

    # The emailish company was stored as empty, so it can't match any search.
    results, err = p.who(code, "a@x.co", "victim")
    assert err is None and results == []
    results, err = p.who(code, "a@x.co", "stripe")
    assert results == [{"display": "a", "you": True, "count": 1}]

    # Non-members can't read anything.
    nope, err = p.summary(code, "stranger@x.co")
    assert nope is None
    nope, err = p.who(code, "stranger@x.co", "stripe")
    assert nope is None
    p.close()


def test_pods_mutuals_and_reupload(tmp_path):
    from pmcaseprep.web.pods import Pods

    p = Pods(tmp_path / "pods.db")
    pod, _ = p.create("squad", "a@x.co")
    code = pod["code"]
    p.join(code, "b@x.co")

    p.set_graph(code, "a@x.co", [], [{"h": FAKE_HASH, "c": "stripe"},
                                     {"h": OTHER_HASH, "c": "notion"}])
    p.set_graph(code, "b@x.co", [], [{"h": FAKE_HASH, "c": "stripe"}])

    summary, _ = p.summary(code, "a@x.co")
    b = next(m for m in summary["members"] if m["display"] == "b")
    assert b["mutuals"] == 1  # same hash on both sides = one shared human

    # Re-upload REPLACES (not appends) the member's slice.
    p.set_graph(code, "a@x.co", [], [{"h": OTHER_HASH, "c": "notion"}])
    summary, _ = p.summary(code, "a@x.co")
    me = next(m for m in summary["members"] if m["you"])
    assert me["connections"] == 1

    # Leaving deletes the graph rows too.
    p.leave(code, "b@x.co")
    summary, _ = p.summary(code, "a@x.co")
    assert all(m["display"] != "b" for m in summary["members"])
    p.close()


def test_pods_caps(tmp_path, monkeypatch):
    from pmcaseprep.web import pods as pods_mod

    p = pods_mod.Pods(tmp_path / "pods.db")
    monkeypatch.setattr(pods_mod, "MAX_MEMBERS", 2)
    monkeypatch.setattr(pods_mod, "MAX_ROWS", 3)

    pod, _ = p.create("small", "a@x.co")
    p.join(pod["code"], "b@x.co")
    full, err = p.join(pod["code"], "c@x.co")
    assert full is None and "full" in err

    res, err = p.set_graph(pod["code"], "a@x.co", [],
                           [{"h": FAKE_HASH, "c": ""}] * 4)
    assert res is None and "too many" in err
    p.close()


# --- The endpoints ------------------------------------------------------------------

def _client(tmp_path, monkeypatch):
    try:
        from fastapi.testclient import TestClient

        from pmcaseprep.web import app as webapp
    except ImportError:
        return None, None
    monkeypatch.setattr(webapp, "DB_PATH", str(tmp_path / "web.db"))
    monkeypatch.setenv("PMCP_DEV_DOCS", "1")  # dev email door for tests
    return TestClient(webapp.app), webapp


def _login(client, email):
    client.get("/referrals")  # uid cookie
    d = client.post("/api/auth/email/request", json={"email": email}).json()
    client.post("/api/auth/email/verify", json={"email": email, "code": d["dev_code"]})


def test_pods_endpoints_require_login(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    if client is None:
        return
    client.get("/referrals")
    assert client.post("/api/pods", json={"name": "x"}).status_code == 401
    assert client.get("/api/pods/mine").status_code == 401
    assert client.post("/api/pods/graph", json={}).status_code == 401
    assert client.get("/api/pods/who?code=X&company=stripe").status_code == 401


def test_pods_end_to_end_flow(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    client, webapp = _client(tmp_path, monkeypatch)
    if client is None:
        return
    _login(client, "parth@example.com")

    # Create → code comes back.
    d = client.post("/api/pods", json={"name": "IITD squad"}).json()
    assert d["ok"] and len(d["pod"]["code"]) == 6
    code = d["pod"]["code"]

    # A second user (own cookie jar) joins and shares a hashed graph.
    client2 = TestClient(webapp.app)
    _login(client2, "rahul@example.com")
    assert client2.post("/api/pods/join", json={"code": code}).json()["ok"]
    r = client2.post("/api/pods/graph", json={
        "code": code,
        "companies": [{"company": "Razorpay", "current": True}],
        "connections": [{"h": FAKE_HASH, "c": "Stripe"}, {"h": OTHER_HASH, "c": "Stripe"}],
    }).json()
    assert r["ok"] and r["shared"] == 2

    # Both see the pod; the summary shows the exchange and counts, never names.
    d = client.get(f"/api/pods/summary?code={code}").json()
    assert d["ok"] and len(d["members"]) == 2
    rahul = next(m for m in d["members"] if m["display"] == "rahul")
    assert rahul["connections"] == 2
    assert rahul["companies"][0]["company"] == "razorpay"
    assert "email" not in rahul  # displays only — addresses aren't echoed back

    # "Who knows someone at stripe?" → per-member counts.
    d = client.get(f"/api/pods/who?code={code}&company=Stripe").json()
    assert d["ok"] and d["results"] == [{"display": "rahul", "you": False, "count": 2}]

    # Bad hash shapes are a 400, never stored.
    r = client.post("/api/pods/graph", json={
        "code": code, "companies": [],
        "connections": [{"h": "not-a-hash", "c": "Stripe"}],
    })
    assert r.status_code == 400

    # Non-member can't read the pod.
    client3 = TestClient(webapp.app)
    _login(client3, "stranger@example.com")
    assert client3.get(f"/api/pods/summary?code={code}").status_code == 404


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

"""Tests for scripts/export_user_emails.py — the signed-in-users export.

Two contracts matter here: the export must agree with SkillGraph's own
identity semantics (one row per email, the uid's LAST-linked email is
primary, activity counts mirror sessions_count), and it must be physically
unable to write to the database it reads. Offline — no network.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _card():
    from pmcaseprep.models import ChecklistItem, DimensionScore, ScoreCard

    return ScoreCard(
        dimension_scores=[
            DimensionScore(dimension="structure", score=3, justification="ok")
        ],
        category_checklist=[ChecklistItem(criterion="c", met=True, note="n")],
        red_flags=[],
        top_improvement="tighten framing",
        overall_band="hire",
        summary="solid",
    )


def _seed(db_path):
    """Two people: ada linked an email and finished 2 cases; bob linked an
    email (twice — old address then new) but hasn't finished anything."""
    from pmcaseprep.skill_graph import SkillGraph

    ada = SkillGraph(db_path, "uid-ada")
    ada.link_email("ada@example.com", "uid-ada")
    ada.record("s1", "case-a", "core", _card(), "hire")
    ada.record("s2", "case-b", "core", _card(), "hire")

    bob = SkillGraph(db_path, "uid-bob")
    bob.link_email("bob-old@example.com", "uid-bob")
    bob.link_email("bob@example.com", "uid-bob")


def test_export_matches_skillgraph_semantics(tmp_path):
    from export_user_emails import fetch_users_with_emails, open_readonly

    db = tmp_path / "skill_graph.db"
    _seed(db)

    conn = open_readonly(db)
    users = fetch_users_with_emails(conn)
    conn.close()

    by_email = {u["email"]: u for u in users}
    assert set(by_email) == {"ada@example.com", "bob-old@example.com", "bob@example.com"}

    # Activity mirrors sessions_count: distinct graded sessions per uid.
    assert by_email["ada@example.com"]["cases"] == 2
    assert by_email["ada@example.com"]["last_active"] is not None
    assert by_email["bob@example.com"]["cases"] == 0
    assert by_email["bob@example.com"]["last_active"] is None

    # One row per email, but bob's PRIMARY email is the one linked last —
    # the same answer SkillGraph.email_for_uid gives.
    from pmcaseprep.skill_graph import SkillGraph

    assert by_email["bob@example.com"]["primary"] is True
    assert by_email["bob-old@example.com"]["primary"] is False
    assert SkillGraph(db, "uid-bob").email_for_uid("uid-bob") == "bob@example.com"


def test_export_connection_cannot_write(tmp_path):
    from export_user_emails import open_readonly

    db = tmp_path / "skill_graph.db"
    _seed(db)

    conn = open_readonly(db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM users")
    conn.close()


def test_missing_db_fails_loudly_not_silently(tmp_path):
    """A typo'd path must not create an empty DB and report 'zero users'."""
    from export_user_emails import open_readonly

    missing = tmp_path / "nope" / "skill_graph.db"
    with pytest.raises(FileNotFoundError):
        open_readonly(missing)
    assert not missing.exists()


def test_empty_and_prelogin_databases(tmp_path):
    from export_user_emails import fetch_users_with_emails, open_readonly

    # A DB with the schema but no logins yet.
    from pmcaseprep.skill_graph import SkillGraph

    db = tmp_path / "fresh.db"
    SkillGraph(db, "uid-x")
    conn = open_readonly(db)
    assert fetch_users_with_emails(conn) == []
    conn.close()

    # A DB that predates logins entirely (no users table at all).
    bare = tmp_path / "bare.db"
    raw = sqlite3.connect(bare)
    raw.execute("CREATE TABLE unrelated (x)")
    raw.commit()
    raw.close()
    conn = open_readonly(bare)
    assert fetch_users_with_emails(conn) == []
    conn.close()


def test_cli_formats(tmp_path, capsys):
    from export_user_emails import main

    db = tmp_path / "skill_graph.db"
    _seed(db)

    assert main(["--db", str(db), "--format", "emails"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert sorted(out) == ["ada@example.com", "bob-old@example.com", "bob@example.com"]

    csv_path = tmp_path / "users.csv"
    assert main(["--db", str(db), "--format", "csv", "-o", str(csv_path)]) == 0
    lines = csv_path.read_text().strip().splitlines()
    assert lines[0] == "email,uid,linked_at,primary,cases,last_active"
    assert len(lines) == 4  # header + three email rows

    assert main(["--db", str(tmp_path / "missing.db")]) == 1

"""Prep docs persistence — the (owner, kind, track) contract, and peaceful
coexistence with database files created by the earlier story-bank era."""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_bank import KINDS, PrepBank  # noqa: E402


@pytest.fixture()
def bank(tmp_path):
    b = PrepBank(str(tmp_path / "prep.db"))
    yield b
    b.close()


REVIEW_DOC = {"cvText": "Led the revamp.", "target": None,
              "roleHint": {"archetype": "Growth", "seniority": ""},
              "review": {"points": [], "overall": {}}}
STORY_DOC = {"answers": [{"question": "Why?", "answer": "Because."}],
             "kit": {"throughLine": "t", "tellMe": "hi"}}


def test_kinds_are_the_two_docs():
    assert KINDS == ("review", "story")


def test_save_and_reload_roundtrip(bank):
    saved = bank.save_doc("p@x.com", "review", "pm", REVIEW_DOC)
    assert saved["updatedAt"] == pytest.approx(time.time(), abs=5)
    got = bank.doc("p@x.com", "review", "pm")
    assert got["cvText"] == "Led the revamp."
    assert got["updatedAt"] == saved["updatedAt"]


def test_saving_again_overwrites_not_duplicates(bank):
    bank.save_doc("p@x.com", "review", "pm", REVIEW_DOC)
    bank.save_doc("p@x.com", "review", "pm", {**REVIEW_DOC, "cvText": "v2"})
    assert bank.doc("p@x.com", "review", "pm")["cvText"] == "v2"
    rows = bank._db.execute("SELECT COUNT(*) FROM prep_docs").fetchone()[0]
    assert rows == 1


def test_docs_returns_both_kinds_with_nulls(bank):
    bank.save_doc("p@x.com", "story", "pm", STORY_DOC)
    docs = bank.docs("p@x.com", "pm")
    assert docs["review"] is None
    assert docs["story"]["kit"]["tellMe"] == "hi"


def test_owners_are_isolated(bank):
    bank.save_doc("a@x.com", "review", "pm", REVIEW_DOC)
    assert bank.doc("b@x.com", "review", "pm") is None


def test_tracks_are_isolated(bank):
    bank.save_doc("p@x.com", "review", "pm", REVIEW_DOC)
    assert bank.doc("p@x.com", "review", "ds") is None
    bank.save_doc("p@x.com", "review", "ds", {**REVIEW_DOC, "cvText": "ds cv"})
    assert bank.doc("p@x.com", "review", "pm")["cvText"] == "Led the revamp."


def test_delete_removes_only_that_doc(bank):
    bank.save_doc("p@x.com", "review", "pm", REVIEW_DOC)
    bank.save_doc("p@x.com", "story", "pm", STORY_DOC)
    bank.delete_doc("p@x.com", "review", "pm")
    assert bank.doc("p@x.com", "review", "pm") is None
    assert bank.doc("p@x.com", "story", "pm") is not None


def test_unknown_kind_or_track_is_an_error(bank):
    with pytest.raises(ValueError):
        bank.save_doc("p@x.com", "heatmap", "pm", {})
    with pytest.raises(ValueError):
        bank.doc("p@x.com", "review", "swe")


def test_story_bank_era_file_is_left_untouched(tmp_path):
    """Opening a database created by the old story-bank code must neither
    fail nor disturb its rows — the new docs table lives alongside them."""
    path = str(tmp_path / "legacy.db")
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE prep_units (
            owner TEXT NOT NULL, id TEXT NOT NULL, json TEXT NOT NULL,
            updated_at REAL NOT NULL, PRIMARY KEY (owner, id)
        );
        CREATE TABLE prep_targets (
            owner TEXT NOT NULL, id TEXT NOT NULL, json TEXT NOT NULL,
            heatmap TEXT NOT NULL DEFAULT '[]', updated_at REAL NOT NULL,
            PRIMARY KEY (owner, id)
        );
        """
    )
    db.execute(
        "INSERT INTO prep_units VALUES ('p@x.com', 'u1', '{\"title\": \"kept\"}', 1.0)"
    )
    db.commit()
    db.close()

    b = PrepBank(path)
    b.save_doc("p@x.com", "review", "pm", REVIEW_DOC)
    assert b.doc("p@x.com", "review", "pm")["cvText"] == "Led the revamp."
    legacy = b._db.execute("SELECT json FROM prep_units WHERE id='u1'").fetchone()
    assert legacy is not None and "kept" in legacy[0]
    b.close()

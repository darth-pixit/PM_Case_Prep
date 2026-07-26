"""Prep docs — persistence for the Prep Engine (/prep and /prep-ds).

One SQLite file holds, per verified user (owner = login email) and per track
("pm" | "ds"), the two working documents the page restores on every visit:

  * kind="review" — the pasted CV, the chosen target (decoded JD or the
    role-in-general hint), and the latest point-by-point review.
  * kind="story"  — the intro-story answers and the latest StoryKit.

Rows are JSON blobs keyed (owner, kind, track): the schemas live in
prep_engine.py's pydantic models and evolve faster than a normalized layout
would tolerate. Saving a kind overwrites the previous row — the engine keeps
your latest tuned CV and story, not an archive. The user owns their data:
both rows are readable through the API that writes them and deletable one
by one.

Database files created by the earlier story-bank era carry extra tables
(prep_units, prep_targets, prep_stories, prep_debriefs). They are left
untouched — this module neither reads, migrates, nor drops them.

Open per request, close in finally — same lifecycle as SkillGraph.
"""

from __future__ import annotations

import json
import sqlite3
import time

KINDS = ("review", "story")
TRACKS = ("pm", "ds")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prep_docs (
    owner      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    track      TEXT NOT NULL,
    json       TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (owner, kind, track)
);
"""


class PrepBank:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _check(kind: str, track: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown doc kind {kind!r}")
        if track not in TRACKS:
            raise ValueError(f"unknown track {track!r}")

    def save_doc(self, owner: str, kind: str, track: str, doc: dict) -> dict:
        """Upsert the (owner, kind, track) row. Stamps `updatedAt` into the
        stored JSON (and returns it) so the client shows freshness without a
        second query."""
        self._check(kind, track)
        doc = dict(doc)
        doc["updatedAt"] = time.time()
        self._db.execute(
            "INSERT INTO prep_docs (owner, kind, track, json, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT (owner, kind, track) DO UPDATE SET "
            "json=excluded.json, updated_at=excluded.updated_at",
            (owner, kind, track, json.dumps(doc), doc["updatedAt"]),
        )
        self._db.commit()
        return doc

    def doc(self, owner: str, kind: str, track: str) -> dict | None:
        self._check(kind, track)
        row = self._db.execute(
            "SELECT json FROM prep_docs WHERE owner=? AND kind=? AND track=?",
            (owner, kind, track),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def docs(self, owner: str, track: str) -> dict:
        """Everything the page needs on load: {"review": ..., "story": ...},
        each a stored doc or None."""
        return {kind: self.doc(owner, kind, track) for kind in KINDS}

    def delete_doc(self, owner: str, kind: str, track: str) -> None:
        self._check(kind, track)
        self._db.execute(
            "DELETE FROM prep_docs WHERE owner=? AND kind=? AND track=?",
            (owner, kind, track),
        )
        self._db.commit()

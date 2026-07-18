"""The story bank — v1 persistence for the Prep Engine (/prep).

The moat from the spec: a compounding personal "Career Genome". One SQLite
file holds, per verified user (owner = login email):

  * units     — the genome. Editable: the extractor is a first draft, not
                gospel. Re-extraction MERGES instead of duplicating (a unit
                with the same title+rawEvidence updates in place).
  * targets   — one row per application (TargetProfile + its cached heatmap),
                which is what makes re-tuning instant: same genome, new
                target, new heatmap.
  * stories   — drafted stories, with the devil's-advocate `solid` flag the
                pressure-test loop flips when the user marks one bulletproof.
  * debriefs  — post-interview write-backs and the insights mined from them.

Rows are JSON blobs keyed (owner, id): the schemas live in prep_engine.py's
pydantic models and evolve faster than a normalized layout would tolerate.
The user owns their data — everything here is listable, exportable through
the API that reads it, and deletable row by row.

Open per request, close in finally — same lifecycle as SkillGraph.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

# Per-user ceilings: a personal story bank, not a data warehouse. Hitting one
# returns a clear error instead of silently dropping rows.
MAX_UNITS = 200
MAX_TARGETS = 30
MAX_STORIES = 200
MAX_DEBRIEFS = 100

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prep_units (
    owner      TEXT NOT NULL,
    id         TEXT NOT NULL,
    json       TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (owner, id)
);
CREATE TABLE IF NOT EXISTS prep_targets (
    owner      TEXT NOT NULL,
    id         TEXT NOT NULL,
    json       TEXT NOT NULL,
    heatmap    TEXT NOT NULL DEFAULT '[]',
    updated_at REAL NOT NULL,
    PRIMARY KEY (owner, id)
);
CREATE TABLE IF NOT EXISTS prep_stories (
    owner      TEXT NOT NULL,
    id         TEXT NOT NULL,
    target_id  TEXT NOT NULL DEFAULT '',
    competency TEXT NOT NULL,
    json       TEXT NOT NULL,
    solid      INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (owner, id)
);
CREATE TABLE IF NOT EXISTS prep_debriefs (
    owner      TEXT NOT NULL,
    id         TEXT NOT NULL,
    target_id  TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL,
    insights   TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    PRIMARY KEY (owner, id)
);
"""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _dedupe_key(unit: dict) -> tuple[str, str]:
    """Two extractions of the same CV line are the SAME unit: identity is the
    normalized (title, rawEvidence) pair, not the per-extraction id."""
    norm = lambda s: " ".join(str(s or "").split()).lower()  # noqa: E731
    return (norm(unit.get("title")), norm(unit.get("rawEvidence")))


class BankFull(Exception):
    """A per-user ceiling was hit; the message is safe to show the user."""


class PrepBank:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # --- units (the genome) ---------------------------------------------------

    def units(self, owner: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT json FROM prep_units WHERE owner=? ORDER BY updated_at",
            (owner,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def save_units(self, owner: str, units: list[dict]) -> list[dict]:
        """Merge units into the bank (dedupe by title+rawEvidence; a match
        updates in place and keeps the bank's id so stories that reference it
        stay valid). Returns the full genome after the merge."""
        existing = {_dedupe_key(u): u["id"] for u in self.units(owner)}
        now = time.time()
        for unit in units:
            unit = dict(unit)
            kept_id = existing.get(_dedupe_key(unit))
            if kept_id is None:
                count = self._db.execute(
                    "SELECT COUNT(*) FROM prep_units WHERE owner=?", (owner,)
                ).fetchone()[0]
                if count >= MAX_UNITS:
                    raise BankFull(f"story bank is full ({MAX_UNITS} units) — delete some first")
                unit["id"] = str(unit.get("id") or _new_id())
                # A colliding id from a fresh extraction must not overwrite an
                # unrelated unit.
                clash = self._db.execute(
                    "SELECT 1 FROM prep_units WHERE owner=? AND id=?",
                    (owner, unit["id"]),
                ).fetchone()
                if clash:
                    unit["id"] = _new_id()
                existing[_dedupe_key(unit)] = unit["id"]
            else:
                unit["id"] = kept_id
            self._db.execute(
                "INSERT INTO prep_units (owner, id, json, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT (owner, id) DO UPDATE SET json=excluded.json, "
                "updated_at=excluded.updated_at",
                (owner, unit["id"], json.dumps(unit), now),
            )
        self._db.commit()
        return self.units(owner)

    def delete_unit(self, owner: str, unit_id: str) -> None:
        self._db.execute(
            "DELETE FROM prep_units WHERE owner=? AND id=?", (owner, unit_id)
        )
        self._db.commit()

    # --- targets (applications / campaigns) -----------------------------------

    def save_target(
        self, owner: str, target: dict, heatmap: list[dict], target_id: str = ""
    ) -> str:
        tid = target_id or _new_id()
        fresh = (
            self._db.execute(
                "SELECT 1 FROM prep_targets WHERE owner=? AND id=?", (owner, tid)
            ).fetchone()
            is None
        )
        if fresh:
            count = self._db.execute(
                "SELECT COUNT(*) FROM prep_targets WHERE owner=?", (owner,)
            ).fetchone()[0]
            if count >= MAX_TARGETS:
                raise BankFull(f"application list is full ({MAX_TARGETS}) — delete some first")
        self._db.execute(
            "INSERT INTO prep_targets (owner, id, json, heatmap, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT (owner, id) DO UPDATE SET "
            "json=excluded.json, heatmap=excluded.heatmap, updated_at=excluded.updated_at",
            (owner, tid, json.dumps(target), json.dumps(heatmap), time.time()),
        )
        self._db.commit()
        return tid

    def save_heatmap(self, owner: str, target_id: str, heatmap: list[dict]) -> None:
        self._db.execute(
            "UPDATE prep_targets SET heatmap=?, updated_at=? WHERE owner=? AND id=?",
            (json.dumps(heatmap), time.time(), owner, target_id),
        )
        self._db.commit()

    def targets(self, owner: str) -> list[dict]:
        """Campaign-dashboard summaries, most recent first."""
        rows = self._db.execute(
            "SELECT id, json, heatmap, updated_at FROM prep_targets "
            "WHERE owner=? ORDER BY updated_at DESC",
            (owner,),
        ).fetchall()
        out = []
        for tid, tj, hj, ts in rows:
            target, cells = json.loads(tj), json.loads(hj)
            solid = self._db.execute(
                "SELECT COUNT(*) FROM prep_stories WHERE owner=? AND target_id=? AND solid=1",
                (owner, tid),
            ).fetchone()[0]
            out.append(
                {
                    "id": tid,
                    "company": target.get("company", ""),
                    "roleTitle": target.get("roleTitle", ""),
                    "seniority": target.get("seniority", ""),
                    "archetype": target.get("archetype", ""),
                    "green": sum(1 for c in cells if c.get("strength") == "green"),
                    "amber": sum(1 for c in cells if c.get("strength") == "amber"),
                    "red": sum(1 for c in cells if c.get("strength") == "red"),
                    "solidStories": solid,
                    "updatedAt": ts,
                }
            )
        return out

    def target(self, owner: str, target_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT json, heatmap FROM prep_targets WHERE owner=? AND id=?",
            (owner, target_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": target_id,
            "target": json.loads(row[0]),
            "cells": json.loads(row[1]),
            "stories": self.stories(owner, target_id),
        }

    def delete_target(self, owner: str, target_id: str) -> None:
        """A campaign's stories go with it; the genome (units) never does."""
        self._db.execute(
            "DELETE FROM prep_targets WHERE owner=? AND id=?", (owner, target_id)
        )
        self._db.execute(
            "DELETE FROM prep_stories WHERE owner=? AND target_id=?", (owner, target_id)
        )
        self._db.execute(
            "DELETE FROM prep_debriefs WHERE owner=? AND target_id=?", (owner, target_id)
        )
        self._db.commit()

    # --- stories --------------------------------------------------------------

    def save_story(
        self, owner: str, story: dict, competency: str, target_id: str = ""
    ) -> str:
        story = dict(story)
        sid = str(story.get("id") or "").strip() or _new_id()
        fresh = (
            self._db.execute(
                "SELECT 1 FROM prep_stories WHERE owner=? AND id=?", (owner, sid)
            ).fetchone()
            is None
        )
        if fresh:
            count = self._db.execute(
                "SELECT COUNT(*) FROM prep_stories WHERE owner=?", (owner,)
            ).fetchone()[0]
            if count >= MAX_STORIES:
                raise BankFull(f"story bank is full ({MAX_STORIES} stories) — delete some first")
        story["id"] = sid
        self._db.execute(
            "INSERT INTO prep_stories (owner, id, target_id, competency, json, solid, updated_at) "
            "VALUES (?,?,?,?,?,0,?) ON CONFLICT (owner, id) DO UPDATE SET "
            "target_id=excluded.target_id, competency=excluded.competency, "
            "json=excluded.json, updated_at=excluded.updated_at",
            (owner, sid, target_id, competency, json.dumps(story), time.time()),
        )
        self._db.commit()
        return sid

    def stories(self, owner: str, target_id: str | None = None) -> list[dict]:
        q = "SELECT id, target_id, competency, json, solid FROM prep_stories WHERE owner=?"
        args: tuple = (owner,)
        if target_id is not None:
            q += " AND target_id=?"
            args = (owner, target_id)
        rows = self._db.execute(q + " ORDER BY updated_at", args).fetchall()
        out = []
        for sid, tid, comp, sj, solid in rows:
            story = json.loads(sj)
            story["id"] = sid
            out.append(
                {"id": sid, "targetId": tid, "competency": comp,
                 "solid": bool(solid), "story": story}
            )
        return out

    def set_story_solid(self, owner: str, story_id: str, solid: bool) -> bool:
        cur = self._db.execute(
            "UPDATE prep_stories SET solid=?, updated_at=? WHERE owner=? AND id=?",
            (1 if solid else 0, time.time(), owner, story_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_story(self, owner: str, story_id: str) -> None:
        self._db.execute(
            "DELETE FROM prep_stories WHERE owner=? AND id=?", (owner, story_id)
        )
        self._db.commit()

    # --- debriefs (the write-back loop) ---------------------------------------

    def save_debrief(
        self, owner: str, notes: str, insights: dict, target_id: str = ""
    ) -> str:
        count = self._db.execute(
            "SELECT COUNT(*) FROM prep_debriefs WHERE owner=?", (owner,)
        ).fetchone()[0]
        if count >= MAX_DEBRIEFS:
            raise BankFull(f"debrief log is full ({MAX_DEBRIEFS}) — delete some first")
        did = _new_id()
        self._db.execute(
            "INSERT INTO prep_debriefs (owner, id, target_id, notes, insights, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (owner, did, target_id, notes, json.dumps(insights), time.time()),
        )
        self._db.commit()
        return did

    def debriefs(self, owner: str, target_id: str | None = None) -> list[dict]:
        q = "SELECT id, target_id, notes, insights, created_at FROM prep_debriefs WHERE owner=?"
        args: tuple = (owner,)
        if target_id is not None:
            q += " AND target_id=?"
            args = (owner, target_id)
        rows = self._db.execute(q + " ORDER BY created_at DESC", args).fetchall()
        return [
            {"id": did, "targetId": tid, "notes": notes,
             "insights": json.loads(ins), "createdAt": ts}
            for did, tid, notes, ins, ts in rows
        ]

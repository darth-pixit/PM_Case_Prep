"""Pods: the opt-in multiplayer layer of Referral Paths (/referrals).

Solo referral-mapping never touches the server — the LinkedIn/Instagram/phone
exports are parsed entirely in the browser. Pods are the explicit opt-in step
that makes networks composable across a group of friends job-hunting together.

The privacy contract (the page copy mirrors this — keep them in sync):
  * A member shares exactly two things with a pod:
      1. company names from their own work history (so the pod can see who is
         able to refer directly where — the "referral exchange"), and
      2. one row per LinkedIn connection: SHA-256(profile URL) + that
         connection's company name.
  * No names, no emails, no titles, no profile URLs in the clear. The upload
    endpoint REJECTS anything that isn't a 64-hex hash and drops company
    strings that look like emails — the promise is enforced by code, not copy.
  * Equal hashes across two members = a mutual connection, countable without
    the server ever knowing who anyone is. Members resolve hashes back to
    people only in their own browser, where the URL->name mapping already
    lives (it came from their own export).
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path

MAX_PODS_PER_USER = 10
MAX_MEMBERS = 12  # a pod is a friend group, not a channel
MAX_ROWS = 30_000  # hashed connections per member per pod
MAX_COMPANIES = 40  # work-history entries per member
POD_NAME_MAX = 40

# No lookalikes (0/O, 1/I/L) — codes get read out loud over calls and chats.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 6
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pods (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pod_members (
    pod_id    INTEGER NOT NULL,
    email     TEXT NOT NULL,
    joined_at REAL NOT NULL,
    companies TEXT NOT NULL DEFAULT '[]',
    shared_at REAL,
    PRIMARY KEY (pod_id, email)
);
CREATE TABLE IF NOT EXISTS pod_graph (
    pod_id   INTEGER NOT NULL,
    email    TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    company  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (pod_id, email, url_hash)
);
CREATE INDEX IF NOT EXISTS idx_pod_graph_hash ON pod_graph (pod_id, url_hash);
CREATE INDEX IF NOT EXISTS idx_pod_graph_co ON pod_graph (pod_id, company);
"""


def clean_company(raw: object) -> str:
    """Normalize a company string for storage/matching. Anything email-shaped
    is dropped outright — a company field must never smuggle in an address."""
    s = " ".join(str(raw or "").split()).strip().lower()
    if not s or "@" in s:
        return ""
    return s[:80]


def valid_hash(h: object) -> bool:
    return isinstance(h, str) and bool(_HASH_RE.match(h))


def display_name(email: str) -> str:
    """What pod-mates see for a member. The local part is plenty — pods are
    invite-code friend groups, but there's no reason to show full addresses."""
    return email.split("@", 1)[0][:24]


class Pods:
    """SQLite store for pods, memberships, and hashed connection graphs.
    Same open/use/close-per-request lifecycle as AuthCodes."""

    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- membership -----------------------------------------------------------

    def create(self, name: str, email: str) -> tuple[dict | None, str | None]:
        name = " ".join(name.split()).strip()[:POD_NAME_MAX]
        if not name:
            return None, "give the pod a name"
        n = self.conn.execute(
            "SELECT COUNT(*) FROM pod_members WHERE email = ?", (email,)
        ).fetchone()[0]
        if n >= MAX_PODS_PER_USER:
            return None, f"you're already in {MAX_PODS_PER_USER} pods — leave one first"
        for _ in range(20):  # collision retry; 31^6 keys makes >1 loop ~never
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
            try:
                cur = self.conn.execute(
                    "INSERT INTO pods (code, name, created_by, created_at) VALUES (?,?,?,?)",
                    (code, name, email, time.time()),
                )
                break
            except sqlite3.IntegrityError:
                continue
        else:  # pragma: no cover - astronomically unlikely
            return None, "couldn't mint a pod code — try again"
        self.conn.execute(
            "INSERT INTO pod_members (pod_id, email, joined_at) VALUES (?,?,?)",
            (cur.lastrowid, email, time.time()),
        )
        self.conn.commit()
        return {"code": code, "name": name}, None

    def _pod(self, code: str) -> tuple[int, str] | None:
        row = self.conn.execute(
            "SELECT id, name FROM pods WHERE code = ?", (code.strip().upper(),)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def _is_member(self, pod_id: int, email: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM pod_members WHERE pod_id = ? AND email = ?",
                (pod_id, email),
            ).fetchone()
            is not None
        )

    def join(self, code: str, email: str) -> tuple[dict | None, str | None]:
        pod = self._pod(code)
        if pod is None:
            return None, "no pod with that code — check it with whoever created it"
        pod_id, name = pod
        if self._is_member(pod_id, email):
            return {"code": code.strip().upper(), "name": name}, None  # idempotent
        n_members = self.conn.execute(
            "SELECT COUNT(*) FROM pod_members WHERE pod_id = ?", (pod_id,)
        ).fetchone()[0]
        if n_members >= MAX_MEMBERS:
            return None, f"that pod is full ({MAX_MEMBERS} people max)"
        n_mine = self.conn.execute(
            "SELECT COUNT(*) FROM pod_members WHERE email = ?", (email,)
        ).fetchone()[0]
        if n_mine >= MAX_PODS_PER_USER:
            return None, f"you're already in {MAX_PODS_PER_USER} pods — leave one first"
        self.conn.execute(
            "INSERT INTO pod_members (pod_id, email, joined_at) VALUES (?,?,?)",
            (pod_id, email, time.time()),
        )
        self.conn.commit()
        return {"code": code.strip().upper(), "name": name}, None

    def leave(self, code: str, email: str) -> bool:
        """Leaving deletes the member's rows AND their shared graph — opting out
        must remove the data, not just the listing. Last one out turns off the
        lights (the pod row itself goes too)."""
        pod = self._pod(code)
        if pod is None:
            return False
        pod_id, _ = pod
        self.conn.execute(
            "DELETE FROM pod_graph WHERE pod_id = ? AND email = ?", (pod_id, email)
        )
        n = self.conn.execute(
            "DELETE FROM pod_members WHERE pod_id = ? AND email = ?", (pod_id, email)
        ).rowcount
        left = self.conn.execute(
            "SELECT COUNT(*) FROM pod_members WHERE pod_id = ?", (pod_id,)
        ).fetchone()[0]
        if left == 0:
            self.conn.execute("DELETE FROM pods WHERE id = ?", (pod_id,))
        self.conn.commit()
        return n > 0

    def mine(self, email: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.code, p.name, "
            "  (SELECT COUNT(*) FROM pod_members m2 WHERE m2.pod_id = p.id) "
            "FROM pods p JOIN pod_members m ON m.pod_id = p.id "
            "WHERE m.email = ? ORDER BY m.joined_at DESC",
            (email,),
        ).fetchall()
        return [{"code": c, "name": n, "members": k} for c, n, k in rows]

    # --- the shared graph -------------------------------------------------------

    def set_graph(
        self, code: str, email: str, companies: list, connections: list
    ) -> tuple[dict | None, str | None]:
        """Replace this member's shared slice. Validation is the privacy floor:
        every connection row must be (64-hex hash, company string) — anything
        else is a 400 upstream, never silently stored."""
        pod = self._pod(code)
        if pod is None:
            return None, "no pod with that code"
        pod_id, _ = pod
        if not self._is_member(pod_id, email):
            return None, "join the pod before sharing into it"
        if not isinstance(companies, list) or not isinstance(connections, list):
            return None, "bad payload"
        if len(connections) > MAX_ROWS:
            return None, f"too many rows — cap is {MAX_ROWS:,}"

        cos: list[dict] = []
        for c in companies[:MAX_COMPANIES]:
            if not isinstance(c, dict):
                return None, "bad company entry"
            name = clean_company(c.get("company"))
            if name:
                cos.append({"company": name, "current": bool(c.get("current"))})

        rows: list[tuple] = []
        for r in connections:
            if not isinstance(r, dict) or not valid_hash(r.get("h")):
                return None, "connections must be 64-hex SHA-256 hashes — nothing else is accepted"
            rows.append((pod_id, email, r["h"], clean_company(r.get("c"))))

        self.conn.execute(
            "DELETE FROM pod_graph WHERE pod_id = ? AND email = ?", (pod_id, email)
        )
        self.conn.executemany(
            "INSERT OR IGNORE INTO pod_graph (pod_id, email, url_hash, company) "
            "VALUES (?,?,?,?)",
            rows,
        )
        self.conn.execute(
            "UPDATE pod_members SET companies = ?, shared_at = ? "
            "WHERE pod_id = ? AND email = ?",
            (json.dumps(cos), time.time(), pod_id, email),
        )
        self.conn.commit()
        n = self.conn.execute(
            "SELECT COUNT(*) FROM pod_graph WHERE pod_id = ? AND email = ?",
            (pod_id, email),
        ).fetchone()[0]
        return {"shared": n, "companies": len(cos)}, None

    def summary(self, code: str, me: str) -> tuple[dict | None, str | None]:
        pod = self._pod(code)
        if pod is None:
            return None, "no pod with that code"
        pod_id, name = pod
        if not self._is_member(pod_id, me):
            return None, "you're not in that pod"
        members = []
        for email, companies, shared_at in self.conn.execute(
            "SELECT email, companies, shared_at FROM pod_members "
            "WHERE pod_id = ? ORDER BY joined_at",
            (pod_id,),
        ).fetchall():
            n_conn = self.conn.execute(
                "SELECT COUNT(*) FROM pod_graph WHERE pod_id = ? AND email = ?",
                (pod_id, email),
            ).fetchone()[0]
            mutuals = 0
            if email != me:
                mutuals = self.conn.execute(
                    "SELECT COUNT(*) FROM pod_graph a JOIN pod_graph b "
                    "ON a.pod_id = b.pod_id AND a.url_hash = b.url_hash "
                    "WHERE a.pod_id = ? AND a.email = ? AND b.email = ?",
                    (pod_id, me, email),
                ).fetchone()[0]
            members.append(
                {
                    "display": display_name(email),
                    "you": email == me,
                    "companies": json.loads(companies or "[]"),
                    "connections": n_conn,
                    "shared": shared_at is not None,
                    "mutuals": mutuals,
                }
            )
        return {"code": code.strip().upper(), "name": name, "members": members}, None

    def who(self, code: str, me: str, company_q: str) -> tuple[list | None, str | None]:
        """Per-member counts of connections at companies matching the query.
        Counts only — the server holds no names to return, by construction."""
        pod = self._pod(code)
        if pod is None:
            return None, "no pod with that code"
        pod_id, _ = pod
        if not self._is_member(pod_id, me):
            return None, "you're not in that pod"
        q = clean_company(company_q).replace("%", "").replace("_", "")
        if len(q) < 2:
            return None, "type at least 2 characters of a company name"
        rows = self.conn.execute(
            "SELECT email, COUNT(*) FROM pod_graph "
            "WHERE pod_id = ? AND company LIKE ? "
            "GROUP BY email ORDER BY COUNT(*) DESC",
            (pod_id, f"%{q}%"),
        ).fetchall()
        return (
            [
                {"display": display_name(e), "you": e == me, "count": n}
                for e, n in rows
            ],
            None,
        )

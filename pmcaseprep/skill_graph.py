"""Cross-case longitudinal analytics — the moat feature from the strategy note.

Every graded case writes per-dimension scores to a plain SQLite table. Analytics
run over that STRUCTURED table (never over raw transcripts) — cheaper, reliable,
and honest. An optional Claude "coach" call turns the numbers into a paragraph.

Alongside the analytics rows, each graded case also stores its FULL record
(scorecard JSON, delivery metrics, transcript) in a `sessions` table, and
`users` maps email -> uid. So when a person attaches their email — even after
finishing cases anonymously — everything they've done is theirs, durably
(`merge_from` re-homes pre-login cases at restore time).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any, Optional

from .models import ScoreCard
from .rubric import BANDS, DIMENSIONS

DIMENSION_NAMES = {key: name for key, name, _ in DIMENSIONS}
_BAR = {name: cutoff for cutoff, name in BANDS}
HIRE_BAR = _BAR["hire"]
STRONG_HIRE_BAR = _BAR["strong_hire"]
# A projection past this many cases is noise, not a plan — report "flat" instead.
MAX_PROJECTED_CASES = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL DEFAULT 'local',
    session_id TEXT NOT NULL,
    case_id    TEXT NOT NULL,
    archetype  TEXT NOT NULL,
    dimension  TEXT NOT NULL,
    score      INTEGER NOT NULL,
    band       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    email      TEXT PRIMARY KEY,
    uid        TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    case_id       TEXT NOT NULL,
    archetype     TEXT NOT NULL,
    band          TEXT NOT NULL,
    weighted      REAL,
    card_json     TEXT,
    delivery_json TEXT,
    transcript    TEXT,
    created_at    TEXT NOT NULL
);
"""


class SkillGraph:
    """One user's longitudinal scores. `user_id` scopes every read and write —
    on the web each visitor gets a cookie uid; the CLI stays 'local'."""

    def __init__(self, db_path: str | Path = "skill_graph.db", user_id: str = "local"):
        self.conn = sqlite3.connect(str(db_path))
        self.user = user_id
        self.conn.executescript(_SCHEMA)
        # Migrate pre-multi-user databases in place.
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(scores)")]
        if "user_id" not in cols:
            self.conn.execute(
                "ALTER TABLE scores ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'"
            )
        self.conn.commit()

    def record(
        self,
        session_id: str,
        case_id: str,
        archetype: str,
        card: ScoreCard,
        band: str,
        *,
        weighted: Optional[float] = None,
        transcript: Optional[str] = None,
        delivery: Optional[dict] = None,
    ) -> None:
        """Persist a graded case: structured scores (analytics) plus the full
        session record (scorecard, transcript, delivery) so a person's cases
        survive to be revisited — especially once they attach an email."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (self.user, session_id, case_id, archetype, ds.dimension, ds.score, band, now)
            for ds in card.dimension_scores
        ]
        self.conn.executemany(
            "INSERT INTO scores (user_id, session_id, case_id, archetype, dimension, score, band, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.execute(
            "INSERT INTO sessions (user_id, session_id, case_id, archetype, band, "
            "weighted, card_json, delivery_json, transcript, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.user,
                session_id,
                case_id,
                archetype,
                band,
                weighted,
                card.model_dump_json(),
                json.dumps(delivery) if delivery is not None else None,
                transcript,
                now,
            ),
        )
        self.conn.commit()

    def history(self) -> list[dict]:
        """This user's graded cases, oldest first — the light index (no blobs)."""
        cur = self.conn.execute(
            "SELECT session_id, case_id, archetype, band, weighted, created_at "
            "FROM sessions WHERE user_id = ? ORDER BY created_at, id",
            (self.user,),
        )
        cols = ("session_id", "case_id", "archetype", "band", "weighted", "created_at")
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def session_record(self, session_id: str) -> Optional[dict]:
        """Full stored record for one of this user's sessions (scorecard,
        delivery metrics, transcript) — None if it isn't theirs."""
        row = self.conn.execute(
            "SELECT session_id, case_id, archetype, band, weighted, card_json, "
            "delivery_json, transcript, created_at "
            "FROM sessions WHERE user_id = ? AND session_id = ?",
            (self.user, session_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row[0],
            "case_id": row[1],
            "archetype": row[2],
            "band": row[3],
            "weighted": row[4],
            "card": json.loads(row[5]) if row[5] else None,
            "delivery": json.loads(row[6]) if row[6] else None,
            "transcript": row[7],
            "created_at": row[8],
        }

    def merge_from(self, other_uid: str) -> None:
        """Re-home another uid's data onto this user. Used at login-restore so
        cases finished anonymously (before entering the email) follow the
        person into their saved account instead of being orphaned."""
        if not other_uid or other_uid == self.user:
            return
        self.conn.execute(
            "UPDATE scores SET user_id = ? WHERE user_id = ?", (self.user, other_uid)
        )
        self.conn.execute(
            "UPDATE sessions SET user_id = ? WHERE user_id = ?", (self.user, other_uid)
        )
        self.conn.commit()

    def sessions_count(self) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM scores WHERE user_id = ?", (self.user,)
        )
        return cur.fetchone()[0]

    def averages(self) -> dict[str, float]:
        cur = self.conn.execute(
            "SELECT dimension, AVG(score) FROM scores WHERE user_id = ? GROUP BY dimension",
            (self.user,),
        )
        return {dim: round(avg, 2) for dim, avg in cur.fetchall()}

    def trend(self, dimension: str) -> Optional[float]:
        """Delta between the earliest-half and latest-half average for a dimension."""
        cur = self.conn.execute(
            "SELECT score FROM scores WHERE user_id = ? AND dimension = ? ORDER BY created_at, id",
            (self.user, dimension),
        )
        vals = [r[0] for r in cur.fetchall()]
        if len(vals) < 4:
            return None
        mid = len(vals) // 2
        first = sum(vals[:mid]) / mid
        last = sum(vals[mid:]) / (len(vals) - mid)
        return round(last - first, 2)

    def session_series(self) -> list[float]:
        """Per-case mean score (across dimensions), oldest case first."""
        cur = self.conn.execute(
            "SELECT AVG(score) FROM scores WHERE user_id = ? "
            "GROUP BY session_id ORDER BY MIN(created_at), MIN(id)",
            (self.user,),
        )
        return [float(row[0]) for row in cur.fetchall()]

    # --- identity: link a cookie uid to an email ---------------------------

    def uid_for_email(self, email: str) -> Optional[str]:
        row = self.conn.execute("SELECT uid FROM users WHERE email = ?", (email,)).fetchone()
        return row[0] if row else None

    def email_for_uid(self, uid: str) -> Optional[str]:
        # A uid can legitimately hold several emails (saved with one, later
        # signed in with another) — report the one they signed in with LAST,
        # not whichever row happens to come back first.
        row = self.conn.execute(
            "SELECT email FROM users WHERE uid = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (uid,),
        ).fetchone()
        return row[0] if row else None

    def link_email(self, email: str, uid: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO users (email, uid, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET uid = excluded.uid",
            (email, uid, now),
        )
        self.conn.commit()

    def projection(self) -> dict:
        """How many more cases to the hire / strong-hire bar at the current pace.

        Honest by construction: needs >=2 graded cases, uses a least-squares
        trend over per-case mean scores, refuses to extrapolate a flat or
        absurdly long trend, and is labeled an estimate (the real band also
        gates on the weakest dimension, which an average can't see).
        """
        series = self.session_series()
        n = len(series)
        out: dict[str, Any] = {
            "sessions": n,
            "series": [round(s, 2) for s in series],  # for the client sparkline
            "current": round(series[-1], 2) if series else None,
            "slope_per_case": None,
            "to_hire": None,
            "to_strong_hire": None,
            "note": "",
        }
        if n < 2:
            out["note"] = "Finish one more case to unlock your trajectory."
            return out

        xs = list(range(n))
        mean_x = (n - 1) / 2
        mean_y = sum(series) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series)) / denom
        level = mean_y + slope * ((n - 1) - mean_x)  # fitted level at the latest case
        out["current"] = round(level, 2)
        out["slope_per_case"] = round(slope, 3)

        def cases_to(target: float) -> Optional[int]:
            if level >= target:
                return 0
            if slope <= 0.005:  # flat or falling — no honest projection exists
                return None
            needed = ceil((target - level) / slope)
            return needed if needed <= MAX_PROJECTED_CASES else None

        out["to_hire"] = cases_to(HIRE_BAR)
        out["to_strong_hire"] = cases_to(STRONG_HIRE_BAR)

        if out["to_strong_hire"] == 0:
            out["note"] = (
                "You're scoring at the strong-hire bar — consistency across "
                "archetypes is the goal now."
            )
        elif out["to_hire"] == 0:
            out["note"] = (
                "You're at the hire bar. Hold this level and push your weakest "
                "dimension to reach strong hire."
            )
        elif out["to_hire"] is None:
            out["note"] = (
                "Your trend is flat right now, so a case count would be a guess — "
                "the fastest route up is drilling your two weakest dimensions, "
                "not more volume."
            )
        else:
            out["note"] = "Estimate — assumes your current pace of improvement holds."
        return out

    def render_summary(self) -> str:
        n = self.sessions_count()
        if n == 0:
            return "No cases graded yet."
        avgs = self.averages()
        ordered = sorted(avgs.items(), key=lambda kv: kv[1])
        lines = [f"Skill graph across {n} case(s):", ""]
        for dim, avg in sorted(avgs.items(), key=lambda kv: kv[1], reverse=True):
            bar = "#" * int(round(avg)) + "-" * (4 - int(round(avg)))
            t = self.trend(dim)
            trend = f"  (trend {t:+.2f})" if t is not None else ""
            lines.append(f"  {DIMENSION_NAMES.get(dim, dim):<26} {avg:.2f} [{bar}]{trend}")
        weakest = [DIMENSION_NAMES.get(d, d) for d, _ in ordered[:2]]
        lines += ["", f"Recurring weak spots: {', '.join(weakest)}."]
        lines.append("Next case will be selected to drill exactly these.  # TODO: adaptive selection")
        return "\n".join(lines)

    def coach_note(self, client: Any, model: str) -> str:
        """Optional: turn the numbers into a short coach paragraph (one cheap call)."""
        if self.sessions_count() == 0:
            return ""
        facts = self.render_summary()
        resp = client.messages.create(
            model=model,
            max_tokens=400,
            system=(
                "You are a concise PM interview coach. Given a candidate's skill-graph "
                "summary, write 3-4 sentences: their consistent strength, their top "
                "recurring weakness, and the single most useful thing to practice next. "
                "No fluff."
            ),
            messages=[{"role": "user", "content": facts}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def close(self) -> None:
        self.conn.close()

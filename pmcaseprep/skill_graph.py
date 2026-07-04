"""Cross-case longitudinal analytics — the moat feature from the strategy note.

Every graded case writes per-dimension scores to a plain SQLite table. Analytics
run over that STRUCTURED table (never over raw transcripts) — cheaper, reliable,
and honest. An optional Claude "coach" call turns the numbers into a paragraph.
"""

from __future__ import annotations

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
    session_id TEXT NOT NULL,
    case_id    TEXT NOT NULL,
    archetype  TEXT NOT NULL,
    dimension  TEXT NOT NULL,
    score      INTEGER NOT NULL,
    band       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SkillGraph:
    def __init__(self, db_path: str | Path = "skill_graph.db"):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def record(self, session_id: str, case_id: str, archetype: str, card: ScoreCard, band: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (session_id, case_id, archetype, ds.dimension, ds.score, band, now)
            for ds in card.dimension_scores
        ]
        self.conn.executemany(
            "INSERT INTO scores (session_id, case_id, archetype, dimension, score, band, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def sessions_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(DISTINCT session_id) FROM scores")
        return cur.fetchone()[0]

    def averages(self) -> dict[str, float]:
        cur = self.conn.execute(
            "SELECT dimension, AVG(score) FROM scores GROUP BY dimension"
        )
        return {dim: round(avg, 2) for dim, avg in cur.fetchall()}

    def trend(self, dimension: str) -> Optional[float]:
        """Delta between the earliest-half and latest-half average for a dimension."""
        cur = self.conn.execute(
            "SELECT score FROM scores WHERE dimension = ? ORDER BY created_at, id",
            (dimension,),
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
            "SELECT AVG(score) FROM scores GROUP BY session_id ORDER BY MIN(created_at), MIN(id)"
        )
        return [float(row[0]) for row in cur.fetchall()]

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

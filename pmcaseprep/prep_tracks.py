"""Track registry for the Prep Engine — the role families /prep can prep for.

The engine's loop (CV -> units -> target -> heatmap -> stories -> grilling)
is role-agnostic; what changes per role family is the competency taxonomy,
the seniority ladder, the framing the prompts inject, and which curated
learning resources apply. That per-family configuration lives here, so
adding a track never means forking the engine.

Two tracks today:
  * "pm" — the original Product Management track (/prep).
  * "ds" — Data Science (/prep-ds), taxonomy grounded in the same research
    pass as the recruiter copilot's KB (recruiter_kb.py): SQL screens, stats
    rounds, ML fundamentals, experiment design, ML system design, and the
    GenAI/eval rounds that now show up inside DS loops.

Learning resources are allowlisted: the plan builder may only cite links
from these curated pools (recruiter_kb's 40 URL-verified picks + the
tutor's resources.py list). A model can propose any of them; it can never
mint a URL of its own — prep_engine.sanitize_learning_plan enforces that.
"""

from __future__ import annotations

from .recruiter_kb import GUIDE
from .resources import RESOURCES as _PM_CASE_RESOURCES

# --- Competency taxonomies (closed lists; the Literal in prep_engine mirrors
# --- them and an import-time assert keeps the two from drifting) --------------

PM_TAXONOMY: tuple[str, ...] = (
    "product-sense",
    "zero-to-one-shipping",
    "execution-delivery",
    "data-driven-decisions",
    "influence-without-authority",
    "stakeholder-exec-communication",
    "strategy-prioritization",
    "technical-fluency",
    "conflict-disagreement",
    "leadership-mentorship",
    "user-empathy-research",
    "metrics-experimentation",
)

DS_TAXONOMY: tuple[str, ...] = (
    "sql-data-wrangling",
    "statistics-probability",
    "ml-fundamentals",
    "experiment-design",
    "product-metrics-sense",
    "ml-system-design",
    "genai-llm-fluency",
    "coding-engineering-rigor",
    "data-storytelling",
    "stakeholder-influence",
    "project-ownership",
    "business-impact",
)


TRACKS: dict[str, dict] = {
    "pm": {
        "key": "pm",
        "name": "Product Management",
        "role_noun": "product manager",
        "taxonomy": PM_TAXONOMY,
        "seniority": ("APM", "PM", "Senior", "Group", "Director"),
        "archetypes": "Growth / Platform / 0-to-1 / Data / AI / Core",
        "extract_context": (
            "The candidate is a product manager: launches, growth pushes, "
            "fixes, strategy calls, conflicts, and research efforts are all "
            "candidate units."
        ),
        "target_context": (
            "This is a product-management hire: read for what the PM will "
            "own, ship, measure, and influence."
        ),
        "grill_context": (
            "Grill like a PM interviewer: why this bet and not another, what "
            "was cut, how success was measured, who pushed back and what "
            "changed, and what the candidate — not the team — decided."
        ),
    },
    "ds": {
        "key": "ds",
        "name": "Data Science",
        "role_noun": "data scientist",
        "taxonomy": DS_TAXONOMY,
        "seniority": ("Junior", "Mid", "Senior", "Staff", "Principal", "Lead"),
        "archetypes": (
            "Product Analytics / Experimentation / ML & Modeling / "
            "GenAI & LLM / Platform & Infra / Decision Science"
        ),
        "extract_context": (
            "The candidate is a data scientist: analyses, models, pipelines, "
            "experiments, dashboards, and publications are all candidate "
            "units — capture datasets, methods, tools, and metrics exactly "
            "as written."
        ),
        "target_context": (
            "This is a data-science hire: read for the stack (SQL, Python), "
            "the methods (statistics, ML, experimentation, GenAI/LLM work), "
            "the product surface, and who consumes the analysis."
        ),
        "grill_context": (
            "Grill like a DS interviewer: data provenance and leakage risk, "
            "metric and baseline choice, statistical validity, why this "
            "method over a simpler one, what reached production, how it was "
            "monitored, and what broke."
        ),
    },
}


def track(key: str) -> dict:
    """The track config for `key`, defaulting to the PM track for anything
    unknown — an unrecognized track must degrade, not 500."""
    return TRACKS.get(key) or TRACKS["pm"]


def all_competencies() -> tuple[str, ...]:
    return PM_TAXONOMY + DS_TAXONOMY


# --- Curated learning resources (the allowlist) -------------------------------
# Canonical shape everywhere: {title, url, kind, time, why}.


def _canon(title: str, url: str, kind: str, time: str, why: str) -> dict:
    return {
        "title": title,
        "url": url,
        "kind": kind or "article",
        "time": time or "",
        "why": " ".join((why or "").split())[:220],
    }


def _kb_pool() -> list[dict]:
    """recruiter_kb's 40 URL-verified picks, with their topic kept for the
    per-competency fallback mapping."""
    out = []
    for r in GUIDE.get("resources", []):
        item = _canon(r["title"], r["url"], r.get("kind", ""), r.get("time", ""), r.get("why", ""))
        item["topic"] = r.get("topic", "")
        out.append(item)
    return out


def _pm_pool() -> list[dict]:
    """resources.py flattened (dedupe by URL — a link can back several keys),
    with its rubric/tag key kept for the fallback mapping."""
    seen: set[str] = set()
    out = []
    for tag, entries in _PM_CASE_RESOURCES.items():
        for r in entries:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            item = _canon(
                f"{r['title']} ({r['author']})", r["url"], r.get("type", ""), "", r.get("why", "")
            )
            item["topic"] = tag
            out.append(item)
    return out


_KB_POOL = _kb_pool()
_PM_POOL = _pm_pool()

# One allowlist for both tracks: every curated link is legitimate everywhere;
# what differs per track is which pool the prompt leads with.
ALLOWED_RESOURCES: dict[str, dict] = {r["url"]: r for r in _KB_POOL + _PM_POOL}


def resource_pool(track_key: str) -> list[dict]:
    """The pool shown to the learning-plan prompt: the track's primary
    collection first, the other track's after (cross-picks are allowed —
    e.g. Pyramid Principle for a data-storytelling gap)."""
    primary, secondary = (_KB_POOL, _PM_POOL) if track_key == "ds" else (_PM_POOL, _KB_POOL)
    return primary + secondary


def _by_topic(pool: list[dict], *topics: str) -> list[dict]:
    return [r for t in topics for r in pool if r.get("topic") == t]


# Deterministic per-competency picks: used to back-fill a gap competency the
# model skipped, so a red cell always leaves the user with something real to
# study even when a model response comes back thin.
_FALLBACKS: dict[str, dict[str, list[dict]]] = {
    "ds": {
        "sql-data-wrangling": _by_topic(_KB_POOL, "SQL"),
        "statistics-probability": _by_topic(_KB_POOL, "Statistics & A/B testing"),
        "ml-fundamentals": _by_topic(_KB_POOL, "Machine learning basics"),
        "experiment-design": _by_topic(_KB_POOL, "Statistics & A/B testing"),
        "product-metrics-sense": _by_topic(_KB_POOL, "AI product metrics")
        + _by_topic(_PM_POOL, "metric_debugging"),
        "ml-system-design": _by_topic(_KB_POOL, "Machine learning basics")[2:]
        + _by_topic(_KB_POOL, "Evaluating AI quality (evals)"),
        "genai-llm-fluency": _by_topic(
            _KB_POOL, "LLM fundamentals", "RAG — retrieval-augmented generation"
        ),
        "coding-engineering-rigor": _by_topic(_KB_POOL, "Machine learning basics")[4:5]
        + _by_topic(_KB_POOL, "Prompt engineering")[:1],
        "data-storytelling": _by_topic(_PM_POOL, "communication"),
        "stakeholder-influence": _by_topic(_PM_POOL, "communication"),
        "project-ownership": _by_topic(_KB_POOL, "Machine learning basics")[4:5],
        "business-impact": _by_topic(_KB_POOL, "AI product metrics")
        + _by_topic(_PM_POOL, "data_business"),
    },
    "pm": {
        "product-sense": _by_topic(_PM_POOL, "creativity"),
        "metrics-experimentation": _by_topic(_PM_POOL, "ab_testing", "metric_debugging"),
        "data-driven-decisions": _by_topic(_PM_POOL, "data_business", "metric_debugging"),
        "user-empathy-research": _by_topic(_PM_POOL, "user_empathy"),
        "stakeholder-exec-communication": _by_topic(_PM_POOL, "communication"),
        "influence-without-authority": _by_topic(_PM_POOL, "communication"),
        "strategy-prioritization": _by_topic(_PM_POOL, "prioritization"),
        "technical-fluency": _by_topic(_PM_POOL, "ai_evals", "sql_metrics"),
        "execution-delivery": _by_topic(_PM_POOL, "structure"),
    },
}


def fallback_resources(track_key: str, competency: str) -> list[dict]:
    picks = _FALLBACKS.get(track_key, {}).get(competency, [])
    return [{k: v for k, v in r.items() if k != "topic"} for r in picks[:2]]


# --- Interview-loop map (the "rounds to expect" card) -------------------------


def rounds_for(track_key: str) -> list[dict]:
    """The researched question archetypes this role family actually faces —
    straight from recruiter_kb (browser-safe by design). DS-only today: the
    PM loop map lives in the arena's five tracks instead."""
    if track_key != "ds":
        return []
    out = []
    for a in GUIDE.get("archetypes", []):
        if "data-science" not in a.get("roles", []):
            continue
        out.append(
            {
                "name": a["name"],
                "description": a["description"],
                "example_questions": a.get("example_questions", [])[:3],
                "good": a.get("good", ""),
                "bad": a.get("bad", ""),
                "seniority": a.get("seniority", ""),
            }
        )
    return out

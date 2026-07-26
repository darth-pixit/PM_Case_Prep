"""Track registry for the Prep Engine — the role families /prep can prep for.

The engine's two jobs — tune how each CV point is *presented*, and shape the
candidate's own intro story — are role-agnostic; what changes per role family
is the hiring lens the prompts adopt, the competency taxonomy a decoded JD
can cite, the seniority ladder, and the archetype names the "role in
general" picker offers. That per-family configuration lives here, so adding
a track never means forking the engine.

Two tracks today:
  * "pm" — the original Product Management track (/prep).
  * "ds" — Data Science (/prep-ds), grounded in the same research pass as
    the recruiter copilot's KB (recruiter_kb.py).

The competency taxonomies are closed lists. They exist for the OPTIONAL
job-description path: a decoded TargetProfile names which competencies the
role weights, and the review/story prompts tune their advice to that. With
no JD, the track's archetype + seniority hint carries the framing instead.
"""

from __future__ import annotations

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
        "archetypes": ("Growth", "Platform", "0-to-1", "Data", "AI", "Core"),
        "target_context": (
            "This is a product-management hire: read for what the PM will "
            "own, ship, measure, and influence."
        ),
        "review_lens": (
            "Read each point the way a PM hiring panel does. A strong PM "
            "bullet shows a problem understood, a decision the candidate — "
            "not the team — owned, and an outcome that mattered, in that "
            "order. Weak bullets list features shipped or ceremonies run "
            "with no user, no scope, and no evidence anything changed. "
            "Screeners give one skim per bullet: the signal has to be in "
            "the first clause."
        ),
        "story_lens": (
            "A PM intro has to land three things in one arc: the kind of "
            "problems that pull this person, proof they ship real outcomes, "
            "and why this role is the obvious next chapter. Interviewers "
            "listen for a motivation that would survive a hard quarter — "
            "'I like working with people' and 'I enjoy the intersection of "
            "business and tech' are auto-discards."
        ),
    },
    "ds": {
        "key": "ds",
        "name": "Data Science",
        "role_noun": "data scientist",
        "taxonomy": DS_TAXONOMY,
        "seniority": ("Junior", "Mid", "Senior", "Staff", "Principal", "Lead"),
        "archetypes": (
            "Product Analytics", "Experimentation", "ML & Modeling",
            "GenAI & LLM", "Platform & Infra", "Decision Science",
        ),
        "target_context": (
            "This is a data-science hire: read for the stack (SQL, Python), "
            "the methods (statistics, ML, experimentation, GenAI/LLM work), "
            "the product surface, and who consumes the analysis."
        ),
        "review_lens": (
            "Read each point the way a DS hiring panel does. A strong DS "
            "bullet names the question, the data and method, the rigor "
            "(baseline, validation, size), and the impact in the metric the "
            "business actually tracks. Weak bullets list tools and model "
            "names with no question answered, no baseline beaten, and no "
            "statement of what changed because of the work."
        ),
        "story_lens": (
            "A DS intro has to land three things in one arc: genuine "
            "curiosity about questions (not tools), proof of rigor that "
            "reached production or a decision, and why this role is the "
            "obvious next chapter. Interviewers listen for whether the "
            "candidate frames work as questions answered or as models "
            "trained — the first gets hired."
        ),
    },
}


def track(key: str) -> dict:
    """The track config for `key`, defaulting to the PM track for anything
    unknown — an unrecognized track must degrade, not 500."""
    return TRACKS.get(key) or TRACKS["pm"]


def all_competencies() -> tuple[str, ...]:
    return PM_TAXONOMY + DS_TAXONOMY

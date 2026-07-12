"""Typed models for cases, observations, and the grader scorecard.

The scorecard models double as the structured-output schema handed to Claude's
`messages.parse()` — keeping the grader's output machine-readable so it can feed
the skill graph directly (no prose parsing).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Polarity = Literal["positive", "negative", "neutral"]

# The six universal Layer-1 rubric dimensions (see rubric.py for descriptions).
DimensionKey = Literal[
    "structure",
    "user_empathy",
    "prioritization",
    "creativity",
    "communication",
    "data_business",
]

OverallBand = Literal["strong_no_hire", "no_hire", "hire", "strong_hire"]


class Anchors(BaseModel):
    """Calibration exemplars the grader scores *against* (not absolute judgment)."""

    strong: str
    at_bar: str
    weak: str


class Case(BaseModel):
    """A single case, loaded from cases/*.json.

    `hidden_facts` and `ideal_answer_notes` are interviewer/grader-only and are
    never shown to the candidate. `hidden_facts` seeds consistent answers to
    clarifying questions; `ideal_answer_notes` seed the grader only.
    """

    id: str
    archetype: str  # ai-pm | growth | technical | consumer | b2b | data | design
    company_persona: str
    interviewer_name: str = "Maya"
    title: str
    # product-design | execution | estimation | strategy | behavioral | ai-pm
    type: str
    prompt: str  # candidate-facing case statement
    hidden_facts: dict[str, str] = Field(default_factory=dict)  # interviewer-only
    ideal_answer_notes: list[str] = Field(default_factory=list)  # grader-only
    rubric_weights: Optional[dict[str, float]] = None  # per-case override
    extra_checklist: list[str] = Field(default_factory=list)  # case-specific items
    anchors: Optional[Anchors] = None
    # Concept keys (see resources.py) this case exercises beyond the six
    # dimensions — used to attach "go deeper" learning links to the scorecard.
    resource_tags: list[str] = Field(default_factory=list)
    # Arena catalog metadata (browser-safe): a one-line hook shown on the case
    # card, and a rough time estimate. Both optional — the tutor case skips them.
    teaser: str = ""
    minutes: int = 20


class Observation(BaseModel):
    """A silent, in-flight note the interviewer logs while the candidate works.

    These are the raw material for both the end-of-case critique and the
    cross-case skill graph — they never reach the candidate mid-session.
    """

    dimension: DimensionKey
    note: str
    polarity: Polarity = "neutral"


# --- Grader structured output ------------------------------------------------


class DimensionScore(BaseModel):
    dimension: DimensionKey
    score: Literal[1, 2, 3, 4]  # 1=red flag, 2=below bar, 3=at bar/hire, 4=exceptional
    justification: str


class ChecklistItem(BaseModel):
    criterion: str
    met: bool
    note: str


class ScoreCard(BaseModel):
    """The grader's machine-readable verdict for one case."""

    dimension_scores: list[DimensionScore]
    category_checklist: list[ChecklistItem]
    red_flags: list[str]
    top_improvement: str
    overall_band: OverallBand
    summary: str

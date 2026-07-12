"""The two-layer PM grading rubric.

Layer 1: six universal dimensions scored 1-4 on EVERY answer. The overall
         verdict is *gated* on any dimension scoring <= 2 (excelling on one
         dimension cannot offset a weak one — this mirrors real FAANG scorecards).

Layer 2: a category-specific checklist keyed by case `type`, mapping to the
         framework interviewers actually look for (CIRCLES, MECE RCA, etc.).

Everything here is original wording derived from the public taxonomy — no
copyrighted rubric text is reproduced.
"""

from __future__ import annotations

# (key, display name, what a strong answer shows)
DIMENSIONS: list[tuple[str, str, str]] = [
    (
        "structure",
        "Structure",
        "MECE, signposted approach; defines the problem, goal, and success metric "
        "before jumping to solutions.",
    ),
    (
        "user_empathy",
        "User Empathy",
        "Segments users by behavior/motivation (not demographics) and names genuine, "
        "specific pain points.",
    ),
    (
        "prioritization",
        "Prioritization",
        "States explicit criteria and de-prioritizes specific things for specific "
        "reasons (vague de-prioritization reads as avoidance).",
    ),
    (
        "creativity",
        "Creativity / Solutioning",
        "Generates 3+ distinct ideas, draws cross-domain analogies, and holds a clear "
        "point of view / vision.",
    ),
    (
        "communication",
        "Communication",
        "Clear, concise, signposted; surfaces the recommendation instead of burying it "
        "under rambling.",
    ),
    (
        "data_business",
        "Data / Business Sense",
        "Defines success metrics and guardrails, reasons with data, and ties choices to "
        "a business outcome.",
    ),
]

DIMENSION_KEYS = [key for key, _, _ in DIMENSIONS]

# Default weights (sum to 1.0). Cases may override via Case.rubric_weights, and
# per-archetype weightings live in ARCHETYPE_WEIGHTS below.
DEFAULT_WEIGHTS: dict[str, float] = {
    "structure": 0.15,
    "user_empathy": 0.20,
    "prioritization": 0.15,
    "creativity": 0.15,
    "communication": 0.15,
    "data_business": 0.20,
}

# Per-archetype dimension tilts (the same answer graded through the right lens).
# These are relative multipliers applied to DEFAULT_WEIGHTS then re-normalized.
ARCHETYPE_WEIGHTS: dict[str, dict[str, float]] = {
    "ai-pm": {"data_business": 1.5, "structure": 1.3, "creativity": 0.8},
    "growth": {"data_business": 1.6, "prioritization": 1.3, "user_empathy": 0.9},
    "technical": {"structure": 1.5, "data_business": 1.2, "creativity": 0.8},
    "consumer": {"user_empathy": 1.6, "creativity": 1.3, "data_business": 0.9},
    "b2b": {"prioritization": 1.4, "data_business": 1.3, "creativity": 0.8},
    "data": {"data_business": 1.6, "structure": 1.3, "creativity": 0.7},
    "design": {"user_empathy": 1.6, "creativity": 1.4, "data_business": 0.8},
    # Arena tracks (the top-5 PM hiring categories). ai-pm above serves both.
    "core-pm": {"user_empathy": 1.3, "creativity": 1.2, "communication": 1.1},
    "growth-pm": {"data_business": 1.6, "prioritization": 1.3, "user_empathy": 0.9},
    "platform-pm": {"structure": 1.5, "data_business": 1.2, "creativity": 0.8},
    "data-pm": {"data_business": 1.6, "structure": 1.3, "creativity": 0.7},
}

# Aggregate bands over the (weighted) 1-4 average, AFTER the <=2 gate.
BANDS: list[tuple[float, str]] = [
    (3.5, "strong_hire"),
    (2.75, "hire"),
    (2.0, "no_hire"),
    (0.0, "strong_no_hire"),
]

# Auto-cap red flags: if the grader detects one, the paired dimension cannot
# exceed the cap. Phrased so the grader can apply them mechanically.
RED_FLAG_CAPS: list[tuple[str, str, int]] = [
    ("Jumped to features/solutions before defining the user or problem", "structure", 2),
    ("Segmented users by demographics only, not behavior/motivation", "user_empathy", 2),
    ("Listed solutions without prioritizing or stating criteria", "prioritization", 2),
    ("Never named a success metric or guardrail", "data_business", 2),
    ("Started arithmetic before building a defensible estimation structure", "structure", 2),
]

# Layer-2 category checklists, keyed by Case.type.
CATEGORY_CHECKLISTS: dict[str, list[str]] = {
    "product-design": [
        "Comprehends the situation: clarifies the goal and a success metric",
        "Identifies and picks a specific user segment",
        "Reports concrete user needs / pain points as user stories",
        "Cuts through: prioritizes which need to solve and why",
        "Lists 3+ distinct solution ideas",
        "Evaluates tradeoffs (value vs effort vs revenue) before recommending",
        "Summarizes a clear recommendation",
    ],
    "execution": [
        "Defines the metric precisely before diagnosing",
        "Characterizes the pattern (sudden vs gradual, segment-wide vs isolated)",
        "Splits causes MECE into internal vs external",
        "Uses process-of-elimination rather than a question dump",
        "Proposes how to confirm the leading hypothesis (data / experiment)",
        "Names a short-term mitigation and a guardrail metric",
    ],
    "estimation": [
        "Builds a MECE calculation tree before any arithmetic",
        "States and justifies each key assumption",
        "Keeps the math clean and traceable",
        "Sanity-checks the final number against a reference point",
    ],
    "strategy": [
        "Frames the decision and the goal/objective explicitly",
        "Analyzes market, users, and competitive dynamics",
        "Weighs options (build/buy/partner, enter/hold) with criteria",
        "Commits to a recommendation with a first move and success measure",
    ],
    "behavioral": [
        "Situation and task are clear and specific",
        "Demonstrates personal ownership (I, not we)",
        "Quantifies the impact / result",
        "Reflects on what was learned or would change",
        "Holds up under a follow-up probe",
    ],
    "ai-pm": [
        "Treats model quality / thumbs-down as a guardrail metric and asks about "
        "model or version changes",
        "Considers eval-set regression and hallucination, not just UX",
        "Reasons about model tradeoffs (quality vs latency vs cost)",
        "Proposes an experiment-based confirmation before concluding",
    ],
    "system-design": [
        "Clarifies who the customer is (internal teams / external developers) and "
        "what job the system does for them before drawing boxes",
        "States requirements and scale assumptions (traffic, latency, consistency) "
        "explicitly instead of designing in a vacuum",
        "Reasons about tradeoffs (build vs buy, latency vs cost, reliability vs "
        "velocity) rather than reciting one architecture",
        "Defines success metrics and an SLA/SLO for the system",
        "Plans rollout/migration and failure modes, not just the happy path",
    ],
}


def weights_for(archetype: str, override: dict[str, float] | None = None) -> dict[str, float]:
    """Resolve final per-dimension weights: override > archetype tilt > default."""
    if override:
        total = sum(override.values()) or 1.0
        return {k: v / total for k, v in override.items()}
    tilt = ARCHETYPE_WEIGHTS.get(archetype, {})
    raw = {k: DEFAULT_WEIGHTS[k] * tilt.get(k, 1.0) for k in DIMENSION_KEYS}
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def band_for(weighted_avg: float, min_dimension: int) -> str:
    """Apply the <=2 gate, then map the weighted average to a band."""
    if min_dimension <= 2:
        # Gate: any dimension at/below the bar caps the outcome at no_hire.
        return "no_hire" if weighted_avg >= 2.0 else "strong_no_hire"
    for threshold, band in BANDS:
        if weighted_avg >= threshold:
            return band
    return "strong_no_hire"

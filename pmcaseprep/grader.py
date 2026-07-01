"""End-of-case grader: one structured-output call producing a ScoreCard.

Uses `client.messages.parse(output_format=ScoreCard)` so the verdict comes back
validated and machine-readable — ready to insert straight into the skill graph.
"""

from __future__ import annotations

from typing import Any

from .models import Case, ScoreCard
from .prompts import GRADER_SYSTEM, build_grader_input
from .rubric import band_for, weights_for


def grade(
    client: Any,
    case: Case,
    transcript: str,
    observations_text: str,
    model: str,
    max_tokens: int = 4000,
) -> ScoreCard:
    """Score one completed case. Adaptive thinking on for careful judgment."""
    resp = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=GRADER_SYSTEM,
        thinking={"type": "adaptive"},
        messages=[
            {
                "role": "user",
                "content": build_grader_input(case, transcript, observations_text),
            }
        ],
        output_format=ScoreCard,
    )
    return resp.parsed_output


def weighted_result(case: Case, card: ScoreCard) -> tuple[float, int, str]:
    """Compute the weighted average, the min dimension, and the gated band.

    We recompute the band locally from the numeric scores so the outcome is
    deterministic and auditable rather than trusting the model's free-text band.
    """
    weights = weights_for(case.archetype, case.rubric_weights)
    scores = {ds.dimension: ds.score for ds in card.dimension_scores}
    weighted = sum(weights.get(k, 0.0) * scores.get(k, 0) for k in weights)
    min_dim = min(scores.values()) if scores else 0
    return weighted, min_dim, band_for(weighted, min_dim)

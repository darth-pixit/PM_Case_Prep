"""Prep Engine tests — the review and story-kit guards, the places the
concept says correctness matters: advice may never smuggle in facts the
candidate didn't provide. Offline: golden-file style fixtures stand in for
model output (fixed input -> assert on structured shape + the truthfulness
invariants); no Anthropic calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_engine import (  # noqa: E402
    ISSUE_TAGS,
    PROMPTS_DIR,
    CVReview,
    PointReview,
    StoryKit,
    TargetProfile,
    audit_kit,
    fill_prompt,
    load_prompt,
    role_context,
    sanitize_review,
    sanitize_target,
)

# --- Golden fixtures ----------------------------------------------------------

CV = """
Acme Corp, Product Manager, 2021-2024.
Led the checkout revamp with a team of 6 engineers; cut drop-off by 18%.
Killed the loyalty-points launch after 2 sprints when retention data went flat.
Ran weekly user interviews for the seller dashboard redesign.
"""

CHECKOUT = "Led the checkout revamp with a team of 6 engineers; cut drop-off by 18%."
LOYALTY = "Killed the loyalty-points launch after 2 sprints when retention data went flat."
INTERVIEWS = "Ran weekly user interviews for the seller dashboard redesign."


def _point(original, rewrite, issues=(), flags=()):
    return {
        "original": original,
        "read": "what a screener takes away",
        "issues": list(issues),
        "rewrite": rewrite,
        "why": "leads with the outcome",
        "flags": list(flags),
    }


# What a well-behaved reviewer returns — plus the failure modes the guards
# exist for: a point the CV never contained, an invented number in a rewrite,
# an off-list issue tag, and a duplicate point.
def raw_review():
    return {
        "points": [
            _point(CHECKOUT, "Cut checkout drop-off 18% by leading a 6-engineer revamp",
                   issues=["buried-lede"]),
            # INVENTED provenance: this line is nowhere in the CV -> dropped
            _point("Grew revenue 40% at Initech.", "whatever"),
            # real line, but the rewrite smuggles in $50,000 -> flagged
            _point(LOYALTY,
                   "Killed a failing loyalty bet after 2 sprints, saving $50,000 of run-rate",
                   issues=["no-evidence", "grit"]),  # "grit" is off-list
            # duplicate of the first point (case/whitespace aside) -> collapsed
            _point("  led the checkout revamp with a team of 6 engineers; cut drop-off by 18%. ",
                   "dup"),
            # honest placeholder instead of a guessed number -> no flags
            _point(INTERVIEWS,
                   "Ran [ADD: how many] weekly user interviews that shaped the seller dashboard redesign",
                   issues=["activity-not-outcome"]),
        ],
        "overall": {
            "readsAs": "A delivery-focused PM with one strong quantified win.",
            "leadWith": [CHECKOUT, "A point that matches nothing in the review"],
            "cut": [LOYALTY.lower()],  # matching is case-insensitive
            "missing": ["A concrete outcome for the research work", "   "],
            "ordering": "Lead with the checkout result.",
        },
    }


def review():
    return sanitize_review(raw_review(), CV)


# --- Review guards ------------------------------------------------------------


def test_review_golden_shape():
    out = review()
    assert isinstance(out, CVReview)
    assert [p.original.strip() for p in out.points] == [CHECKOUT, LOYALTY, INTERVIEWS]
    assert all(isinstance(p, PointReview) for p in out.points)


def test_point_the_cv_never_contained_is_dropped():
    out = review()
    assert all("Initech" not in p.original for p in out.points)


def test_duplicate_point_collapses_to_first():
    out = review()
    assert sum(1 for p in out.points if "checkout revamp" in p.original) == 1
    assert out.points[0].rewrite != "dup"


def test_grounded_rewrite_numbers_pass_invented_ones_flag():
    out = review()
    assert out.points[0].flags == []  # 18 and 6 are in the CV
    loyalty = out.points[1]
    assert len(loyalty.flags) == 1 and '"50000"' in loyalty.flags[0]


def test_placeholder_rewrite_is_the_honest_path():
    # [ADD: …] instead of a guessed number -> nothing to flag.
    assert review().points[2].flags == []


def test_off_list_issue_tag_dropped_not_guessed():
    loyalty = review().points[1]
    assert loyalty.issues == ["no-evidence"]
    for p in review().points:
        assert all(i in ISSUE_TAGS for i in p.issues)


def test_overall_references_only_surviving_points():
    o = review().overall
    assert o.leadWith == [CHECKOUT]  # the no-match entry died
    # case-insensitive match canonicalizes to the point's own original text
    assert o.cut == [LOYALTY]
    assert o.missing == ["A concrete outcome for the research work"]


def test_review_with_no_verifiable_points_is_an_error():
    fake = {"points": [_point("Not in the CV at all", "x")], "overall": {}}
    with pytest.raises(ValueError):
        sanitize_review(fake, CV)


def test_malformed_point_never_sinks_the_review():
    raw = raw_review()
    raw["points"].insert(0, {"original": CHECKOUT})  # missing required fields
    out = sanitize_review(raw, CV)
    assert [p.original.strip() for p in out.points] == [CHECKOUT, LOYALTY, INTERVIEWS]


# --- Story-kit audit ----------------------------------------------------------


def kit(tell_me: str, beats=None, tips=None):
    return StoryKit(
        throughLine="I fix funnels other people gave up on.",
        tellMe=tell_me,
        whyRole="Because shipping beats admiring problems.",
        whyThis="This role owns the funnel end to end.",
        beats=beats if beats is not None else ["engineer", "the checkout win", "why here"],
        tips=tips if tips is not None else ["pause after the 18% number"],
    )


SOURCES = CV + "\nQ: proudest?\nA: the checkout revamp, drop-off down 18%."


def test_grounded_numbers_are_not_flagged():
    out = audit_kit(kit("I led a checkout revamp that cut drop-off 18%."), SOURCES)
    assert out.flags == []


def test_invented_number_lands_in_flags():
    out = audit_kit(kit("I cut drop-off 18% and grew revenue 47%."), SOURCES)
    assert len(out.flags) == 1 and '"47"' in out.flags[0]


def test_alien_number_flagged_once_across_sections():
    k = kit("Revenue grew 47%.")
    k.whyRole = "The 47% story is why."
    out = audit_kit(k, SOURCES)
    assert len(out.flags) == 1


def test_beats_and_tips_are_bounded():
    out = audit_kit(
        kit("fine", beats=[f"beat {i}" for i in range(10)],
            tips=[f"tip {i}" for i in range(9)]),
        SOURCES,
    )
    assert len(out.beats) == 6 and len(out.tips) == 5


def test_kit_without_its_core_pieces_is_an_error():
    with pytest.raises(ValueError):
        audit_kit(kit("   "), SOURCES)


# --- The optional target ------------------------------------------------------


def target(**over):
    base = dict(
        company="Globex", roleTitle="Senior PM, Growth", seniority="Senior",
        archetype="Growth",
        requiredCompetencies=[
            {"competency": "execution-delivery", "weight": 5, "evidence": "ship fast"},
        ],
        unwrittenPain="Growth has stalled.", companyValues=[],
    )
    base.update(over)
    return TargetProfile(**base)


def test_role_context_without_jd_is_the_general_path():
    ctx = role_context("pm")
    assert "No specific opening" in ctx
    assert "product manager roles in general" in ctx
    assert "Do not invent a company" in ctx


def test_role_context_carries_the_hint():
    ctx = role_context("pm", role_hint={"seniority": "Senior", "archetype": "Growth"})
    assert "Senior Growth product manager" in ctx
    assert "data scientist" in role_context("ds")


def test_role_context_with_target_is_the_jd_path():
    ctx = role_context("pm", target=target())
    assert "Decoded target role" in ctx and "Globex" in ctx


def test_target_dedupes_required_competencies():
    t = target(requiredCompetencies=[
        {"competency": "product-sense", "weight": 2, "evidence": "a"},
        {"competency": "product-sense", "weight": 5, "evidence": "b"},
    ])
    out = sanitize_target(t)
    assert len(out.requiredCompetencies) == 1
    assert out.requiredCompetencies[0].weight == 5  # highest weight wins


def test_target_with_no_competencies_is_an_error():
    with pytest.raises(ValueError):
        sanitize_target(target(requiredCompetencies=[]))


# --- Prompt files (must exist, carry the hard rules, and fill cleanly) --------

PROMPT_PLACEHOLDERS = {
    "tune-cv.md": {
        "ROLE_LENS": "lens", "ROLE_NOUN": "PM", "TARGET_CONTEXT": "ctx",
        "ISSUE_TAGS": "a, b", "CV": "cv",
    },
    "intro-story.md": {
        "ROLE_LENS": "lens", "ROLE_NOUN": "PM", "TARGET_CONTEXT": "ctx",
        "CV": "cv", "ANSWERS": "qa", "REVISION": "(first draft)",
    },
    "extract-target.md": {
        "ROLE_CONTEXT": "r", "TAXONOMY": "t", "SENIORITY_LADDER": "s",
        "ARCHETYPES": "a", "JOB_DESCRIPTION": "jd",
    },
}


def test_prompts_live_on_disk_and_fill_cleanly():
    for name, subs in PROMPT_PLACEHOLDERS.items():
        assert (PROMPTS_DIR / name).is_file(), f"missing prompts/{name}"
        filled = fill_prompt(load_prompt(name), **subs)
        for key in subs:
            assert f"<{key}>" not in filled


def test_prompts_state_the_no_fabrication_rule():
    tune = load_prompt("tune-cv.md")
    assert "Do NOT invent" in tune
    assert "[ADD:" in tune and "Never guess a value" in tune
    assert "VERBATIM" in tune  # provenance: quote, don't paraphrase
    story = load_prompt("intro-story.md")
    assert "Do NOT invent" in story
    assert "[ADD:" in story and "never a guessed value" in story


def test_fill_prompt_rejects_missing_placeholder():
    with pytest.raises(KeyError):
        fill_prompt("no tokens here", CV="x")

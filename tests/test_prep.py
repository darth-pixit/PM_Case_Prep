"""Prep Engine tests — the extractor guards and the heatmap scorer, the two
places the spec says correctness matters. Offline: golden-file style fixtures
stand in for model output (fixed input -> assert on structured shape + the
truthfulness invariants); no Anthropic calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_engine import (  # noqa: E402
    GENERIC_GAP,
    PROMPTS_DIR,
    TAXONOMY,
    AchievementUnit,
    Story,
    StoryVersions,
    TargetProfile,
    audit_story,
    fill_prompt,
    load_prompt,
    sanitize_heatmap,
    sanitize_target,
    sanitize_units,
)

# --- Golden fixtures ----------------------------------------------------------

CV = """
Acme Corp, Product Manager, 2021-2024.
Led the checkout revamp with a team of 6 engineers; cut drop-off by 18%.
Killed the loyalty-points launch after 2 sprints when retention data went flat.
Ran weekly user interviews for the seller dashboard redesign.
"""

# What a well-behaved extractor returns for CV — plus the failure modes the
# guards exist for: an invented metric, an off-taxonomy competency, a dup id.
RAW_UNITS = [
    {
        "id": "u1",
        "title": "Cut checkout drop-off",
        "context": "Acme Corp, 2021-2024",
        "action": "Led the checkout revamp with a team of 6 engineers",
        "result": "Drop-off fell",
        "metric": "cut drop-off by 18%",  # real: 18 and 6 are in the source
        "competencies": ["execution-delivery", "data-driven-decisions"],
        "skills": ["checkout"],
        "scale": "team of 6",
        "type": "fix",
        "isFailure": False,
        "rawEvidence": "Led the checkout revamp with a team of 6 engineers; cut drop-off by 18%.",
    },
    {
        "id": "u1",  # duplicate id — must be uniquified, not dropped
        "title": "Killed the loyalty launch",
        "context": "Acme Corp",
        "action": "Stopped the loyalty-points launch after 2 sprints",
        "result": "Saved the roadmap from a flat bet",
        "metric": "saved $40,000",  # INVENTED: 40000 appears nowhere in the CV
        "competencies": ["strategy-prioritization", "grit"],  # "grit" is off-taxonomy
        "skills": [],
        "scale": None,
        "type": "strategy",
        "isFailure": True,
        "rawEvidence": "Killed the loyalty-points launch after 2 sprints when retention data went flat.",
    },
    {
        "id": "",  # empty id — must be assigned
        "title": "Weekly user interviews",
        "context": "Acme Corp, seller dashboard",
        "action": "Ran weekly user interviews",
        "result": "Informed the redesign",
        "metric": None,  # no number in the bullet -> stays null
        "competencies": ["user-empathy-research"],
        "skills": ["research"],
        "scale": None,
        "type": "research",
        "isFailure": False,
        "rawEvidence": "Ran weekly user interviews for the seller dashboard redesign.",
    },
]

TARGET = TargetProfile(
    company="Globex",
    roleTitle="Senior PM, Growth",
    seniority="Senior",
    archetype="Growth",
    requiredCompetencies=[
        {"competency": "execution-delivery", "weight": 5, "evidence": "ship fast"},
        {"competency": "metrics-experimentation", "weight": 4, "evidence": "A/B testing"},
        {"competency": "user-empathy-research", "weight": 2, "evidence": "talk to users"},
    ],
    unwrittenPain="Growth has stalled and nobody trusts the funnel numbers.",
    companyValues=[],
)


def units():
    return sanitize_units([dict(u) for u in RAW_UNITS], source=CV)


# --- Extractor guards ---------------------------------------------------------


def test_extractor_golden_shape():
    out = units()
    assert len(out) == 3
    assert all(isinstance(u, AchievementUnit) for u in out)
    # ids: unique, non-empty
    ids = [u.id for u in out]
    assert len(set(ids)) == 3 and all(ids)
    # the failure story keeps its behavioral-gold flag
    assert out[1].isFailure is True


def test_real_metric_survives_invented_metric_dies():
    out = units()
    assert out[0].metric == "cut drop-off by 18%"  # 18 and 6 are in the CV
    assert out[1].metric is None  # $40,000 is nowhere in the CV -> nulled
    assert out[2].metric is None  # null in, null out — never invented


def test_off_taxonomy_competency_dropped_not_guessed():
    out = units()
    assert out[1].competencies == ["strategy-prioritization"]
    for u in out:
        assert all(c in TAXONOMY for c in u.competencies)


def test_roundtrip_revalidation_skips_metric_audit():
    # Units coming back from the browser have no source text attached; the
    # metric audit already ran at extraction and must not re-null real metrics.
    once = units()
    again = sanitize_units([u.model_dump() for u in once])
    assert again[0].metric == "cut drop-off by 18%"


def test_taxonomy_is_the_specs_closed_list():
    assert len(TAXONOMY) == 12
    assert "product-sense" in TAXONOMY and "metrics-experimentation" in TAXONOMY


# --- Heatmap scorer guards ----------------------------------------------------


def golden_cells(us):
    return [
        # green with real evidence — passes through untouched
        {"competency": "execution-delivery", "strength": "green",
         "bestUnitId": us[0].id, "gapAction": None},
        # green citing a unit that doesn't exist — evidence cleared, downgraded
        {"competency": "metrics-experimentation", "strength": "green",
         "bestUnitId": "ghost-unit", "gapAction": None},
        # user-empathy-research is REQUIRED but missing from the model's answer
        # a cell for a competency the role never asked about — must not appear
        {"competency": "technical-fluency", "strength": "amber",
         "bestUnitId": None, "gapAction": "learn to code"},
    ]


def test_heatmap_golden():
    us = units()
    cells = sanitize_heatmap(golden_cells(us), TARGET, us)
    # exactly one cell per required competency, in the target's order
    assert [c.competency for c in cells] == [
        "execution-delivery", "metrics-experimentation", "user-empathy-research"
    ]
    by = {c.competency: c for c in cells}
    assert by["execution-delivery"].strength == "green"
    assert by["execution-delivery"].bestUnitId == us[0].id
    assert by["execution-delivery"].gapAction is None  # green never carries one


def test_green_without_real_evidence_downgrades():
    us = units()
    by = {c.competency: c for c in sanitize_heatmap(golden_cells(us), TARGET, us)}
    cell = by["metrics-experimentation"]
    assert cell.bestUnitId is None  # "ghost-unit" matches nothing
    assert cell.strength == "amber"  # green MEANS direct evidence exists
    assert cell.gapAction  # amber always tells you how to close the gap


def test_skipped_required_competency_comes_back_red():
    us = units()
    by = {c.competency: c for c in sanitize_heatmap(golden_cells(us), TARGET, us)}
    cell = by["user-empathy-research"]
    assert cell.strength == "red"
    assert cell.gapAction == GENERIC_GAP.format(competency="user-empathy-research")


def test_target_dedupes_required_competencies():
    t = TargetProfile(
        company="X", roleTitle="PM", seniority="PM", archetype="Core",
        requiredCompetencies=[
            {"competency": "product-sense", "weight": 2, "evidence": "a"},
            {"competency": "product-sense", "weight": 5, "evidence": "b"},
        ],
        unwrittenPain="pain", companyValues=[],
    )
    out = sanitize_target(t)
    assert len(out.requiredCompetencies) == 1
    assert out.requiredCompetencies[0].weight == 5  # highest weight wins


def test_target_with_no_competencies_is_an_error():
    t = TargetProfile(
        company="X", roleTitle="PM", seniority="PM", archetype="Core",
        requiredCompetencies=[], unwrittenPain="pain", companyValues=[],
    )
    with pytest.raises(ValueError):
        sanitize_target(t)


# --- Story audit --------------------------------------------------------------


def story(text_2min: str) -> Story:
    return Story(
        id="s1",
        spineTag="ships real outcomes",
        unitIds=["u1", "not-a-unit"],
        competenciesCovered=["execution-delivery"],
        versions=StoryVersions(
            thirtySec="I led the checkout revamp and cut drop-off by 18%.",
            twoMin=text_2min,
            deepDive="Team of 6, drop-off down 18%.",
        ),
        anticipatedFollowups=["Why you?", "What broke?", "What would you redo?"],
    )


def test_grounded_numbers_are_not_flagged():
    us = units()
    st = audit_story(story("With 6 engineers we cut drop-off 18%."), us)
    assert st.unverifiedClaims == []


def test_invented_number_lands_in_unverified_claims():
    us = units()
    st = audit_story(story("We cut drop-off 18% and grew revenue 47%."), us)
    assert len(st.unverifiedClaims) == 1
    assert '"47"' in st.unverifiedClaims[0]


def test_story_unit_refs_are_pruned_to_real_units():
    us = units()
    st = audit_story(story("plain words, no numbers"), us)
    assert "not-a-unit" not in st.unitIds
    assert st.unitIds == ["u1"]


# --- Prompt files (must exist, carry the hard rules, and fill cleanly) --------

PROMPT_PLACEHOLDERS = {
    "extract-units.md": {"TAXONOMY": "t", "CV_OR_BRAINDUMP": "cv"},
    "extract-target.md": {"TAXONOMY": "t", "JOB_DESCRIPTION": "jd"},
    "score-coverage.md": {"UNITS_JSON": "[]", "REQUIRED_COMPETENCIES_JSON": "[]"},
    "craft-story.md": {"SPINE_TAG": "s", "COMPETENCY": "c", "REFERENCED_UNITS_JSON": "[]"},
}


def test_prompts_live_on_disk_and_fill_cleanly():
    for name, subs in PROMPT_PLACEHOLDERS.items():
        assert (PROMPTS_DIR / name).is_file(), f"missing prompts/{name}"
        filled = fill_prompt(load_prompt(name), **subs)
        for key in subs:
            assert f"<{key}>" not in filled


def test_prompts_state_the_no_fabrication_rule():
    assert "Do NOT invent" in load_prompt("extract-units.md")
    assert '"metric": null' in load_prompt("extract-units.md")
    assert "unverifiedClaims" in load_prompt("craft-story.md")
    assert "not how to\nspin" in load_prompt("score-coverage.md") or (
        "spin" in load_prompt("score-coverage.md")
    )


def test_fill_prompt_rejects_missing_placeholder():
    with pytest.raises(KeyError):
        fill_prompt("no tokens here", TAXONOMY="x")

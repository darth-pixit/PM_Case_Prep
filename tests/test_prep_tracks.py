"""Track registry tests — the per-role-family configuration the Prep Engine
prompts run on, and the cross-track guards on the optional decoded target."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_engine import (  # noqa: E402
    Competency,
    TargetProfile,
    sanitize_target,
)
from pmcaseprep.prep_tracks import (  # noqa: E402
    DS_TAXONOMY,
    PM_TAXONOMY,
    TRACKS,
    all_competencies,
    track,
)

# --- The registry -------------------------------------------------------------


def test_taxonomies_are_disjoint_and_cover_the_literal():
    assert not set(PM_TAXONOMY) & set(DS_TAXONOMY)
    assert set(get_args(Competency)) == set(all_competencies())
    assert len(PM_TAXONOMY) == 12 and len(DS_TAXONOMY) == 12


def test_unknown_track_degrades_to_pm():
    assert track("nope")["key"] == "pm"
    assert track("")["key"] == "pm"
    assert track("ds")["name"] == "Data Science"


def test_each_track_carries_the_prompt_lenses():
    for key, tr in TRACKS.items():
        assert tr["key"] == key
        for field in ("role_noun", "review_lens", "story_lens", "target_context"):
            assert tr[field].strip(), f"{key}.{field} is empty"
        assert len(tr["archetypes"]) >= 4  # the role-in-general picker
        assert len(tr["seniority"]) >= 4
        assert isinstance(tr["archetypes"], tuple)


def test_lenses_read_for_presentation_not_spin():
    # Load-bearing framing the prompts inject — keep the meaning if rewording.
    assert "not the team" in TRACKS["pm"]["review_lens"]
    assert "baseline" in TRACKS["ds"]["review_lens"]
    for tr in TRACKS.values():
        assert "arc" in tr["story_lens"]


# --- The optional decoded target (cross-track guards) -------------------------


def _target(**over):
    base = dict(
        company="Globex", roleTitle="Senior DS", seniority="Senior",
        archetype="Experimentation",
        requiredCompetencies=[
            {"competency": "experiment-design", "weight": 5, "evidence": "a/b"},
            {"competency": "product-sense", "weight": 4, "evidence": "pm-ish"},
        ],
        unwrittenPain="Nobody trusts the experiments.", companyValues=[],
    )
    base.update(over)
    return TargetProfile(**base)


def test_target_track_is_stamped_and_off_track_rows_drop():
    out = sanitize_target(_target(), track_key="ds")
    assert out.track == "ds"
    comps = [rc.competency for rc in out.requiredCompetencies]
    assert comps == ["experiment-design"]  # the PM row died on the DS page


def test_target_with_only_off_track_rows_is_an_error():
    with pytest.raises(ValueError):
        sanitize_target(
            _target(requiredCompetencies=[
                {"competency": "product-sense", "weight": 4, "evidence": "x"},
            ]),
            track_key="ds",
        )


def test_legacy_target_defaults_to_pm_track():
    # Rows saved before tracks existed round-trip with track="pm".
    raw = _target(requiredCompetencies=[
        {"competency": "product-sense", "weight": 4, "evidence": "x"},
    ]).model_dump()
    raw.pop("track")
    assert TargetProfile.model_validate(raw).track == "pm"

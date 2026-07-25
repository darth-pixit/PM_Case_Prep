"""Prep Engine v3 tests: the track registry (PM vs DS), the grill sanitizers,
the learning-plan allowlist, and the bank's cross-track contracts. Offline —
fixtures stand in for model output, tmp_path sqlite for the bank."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import get_args

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_bank import PrepBank  # noqa: E402
from pmcaseprep.prep_engine import (  # noqa: E402
    PROMPTS_DIR,
    AttackVerdict,
    Competency,
    CoverageCell,
    GrillProbe,
    GrillRound,
    LearningItem,
    LearningPlan,
    LearningResource,
    TargetProfile,
    fill_prompt,
    load_prompt,
    sanitize_grill_map,
    sanitize_grill_round,
    sanitize_learning_plan,
    sanitize_target,
    sanitize_units,
)
from pmcaseprep.prep_tracks import (  # noqa: E402
    ALLOWED_RESOURCES,
    DS_TAXONOMY,
    PM_TAXONOMY,
    TRACKS,
    fallback_resources,
    resource_pool,
    rounds_for,
    track,
)

# --- Fixtures -----------------------------------------------------------------

MIXED_UNIT = {
    "id": "u1",
    "title": "Built the churn model",
    "context": "Acme, 2023",
    "action": "Built an XGBoost churn model over 2M users",
    "result": "Recall up over the rules baseline",
    "metric": "recall up 22%",
    # one tag from each track — the genome is shared across pages
    "competencies": ["ml-fundamentals", "data-driven-decisions"],
    "skills": ["python", "xgboost"],
    "scale": "2M users",
    "type": "model",
    "isFailure": False,
    "rawEvidence": "Built churn model (XGBoost, 2M users) — recall up 22%.",
}

DS_TARGET = TargetProfile(
    company="Globex",
    roleTitle="Senior Data Scientist",
    seniority="Senior",
    archetype="Experimentation",
    requiredCompetencies=[
        {"competency": "statistics-probability", "weight": 5, "evidence": "strong stats"},
        {"competency": "experiment-design", "weight": 4, "evidence": "own the A/B program"},
        {"competency": "sql-data-wrangling", "weight": 3, "evidence": "fluent SQL"},
    ],
    unwrittenPain="Nobody trusts the experiment readouts.",
    companyValues=[],
    track="ds",
)

DS_CELLS = [
    CoverageCell(competency="statistics-probability", strength="red",
                 bestUnitId=None, gapAction="study inference for real"),
    CoverageCell(competency="experiment-design", strength="amber",
                 bestUnitId=None, gapAction="bridge from the churn work"),
    CoverageCell(competency="sql-data-wrangling", strength="green",
                 bestUnitId="u1", gapAction=None),
]


def units():
    return sanitize_units([dict(MIXED_UNIT)])


# --- The track registry -------------------------------------------------------


def test_taxonomies_are_disjoint_and_cover_the_literal():
    assert len(DS_TAXONOMY) == 12 and len(PM_TAXONOMY) == 12
    assert not set(DS_TAXONOMY) & set(PM_TAXONOMY)
    assert set(get_args(Competency)) == set(PM_TAXONOMY) | set(DS_TAXONOMY)


def test_unknown_track_degrades_to_pm():
    assert track("nope")["key"] == "pm"
    assert track("ds")["key"] == "ds"
    assert TRACKS["ds"]["taxonomy"] == DS_TAXONOMY


def test_ds_seniority_ladder_validates():
    for level in TRACKS["ds"]["seniority"]:
        TargetProfile(
            company="X", roleTitle="DS", seniority=level, archetype="ML",
            requiredCompetencies=[
                {"competency": "ml-fundamentals", "weight": 3, "evidence": "e"}],
            unwrittenPain="p", companyValues=[], track="ds",
        )


# --- Cross-track unit sanitizing ----------------------------------------------


def test_roundtrip_default_keeps_both_tracks_tags():
    # Units round-tripping through the browser must keep BOTH tracks' tags —
    # the genome is one bank shared by /prep and /prep-ds.
    out = units()
    assert out[0].competencies == ["ml-fundamentals", "data-driven-decisions"]


def test_extraction_taxonomy_narrows_to_one_track():
    out = sanitize_units([dict(MIXED_UNIT)], taxonomy=DS_TAXONOMY)
    assert out[0].competencies == ["ml-fundamentals"]  # the PM tag is dropped


def test_target_track_is_stamped_and_off_track_rows_drop():
    t = TargetProfile(
        company="X", roleTitle="DS", seniority="Mid", archetype="ML",
        requiredCompetencies=[
            {"competency": "statistics-probability", "weight": 5, "evidence": "a"},
            {"competency": "product-sense", "weight": 4, "evidence": "b"},  # PM row
        ],
        unwrittenPain="p", companyValues=[],
    )
    out = sanitize_target(t, track_key="ds")
    assert out.track == "ds"
    assert [rc.competency for rc in out.requiredCompetencies] == ["statistics-probability"]

    all_foreign = TargetProfile(
        company="X", roleTitle="DS", seniority="Mid", archetype="ML",
        requiredCompetencies=[
            {"competency": "product-sense", "weight": 4, "evidence": "b"}],
        unwrittenPain="p", companyValues=[],
    )
    with pytest.raises(ValueError):
        sanitize_target(all_foreign, track_key="ds")


def test_legacy_target_defaults_to_pm_track():
    t = TargetProfile.model_validate(
        {"company": "X", "roleTitle": "PM", "seniority": "PM", "archetype": "Core",
         "requiredCompetencies": [
             {"competency": "product-sense", "weight": 3, "evidence": "e"}],
         "unwrittenPain": "p", "companyValues": []}
    )
    assert t.track == "pm"


# --- Grill sanitizers ---------------------------------------------------------


def test_grill_map_rows_must_point_at_real_units():
    us = units()
    raw = [
        {"unitId": "u1", "questions": [
            {"question": f"q{i}", "trap": "t"} for i in range(5)]},  # capped to 3
        {"unitId": "ghost", "questions": [{"question": "q", "trap": "t"}]},  # dropped
        {"unitId": "u1", "questions": [{"question": "dup", "trap": "t"}]},  # first wins
        {"unitId": "u1"},  # malformed (no questions) — skipped, never sinks the map
    ]
    rows = sanitize_grill_map(raw, us)
    assert len(rows) == 1
    assert rows[0].unitId == "u1"
    assert len(rows[0].questions) == 3
    assert rows[0].questions[0].question == "q0"


def test_grill_round_bounds():
    round_ = GrillRound(
        verdicts=[AttackVerdict(question=f"q{i}", verdict="held", why="w") for i in range(5)],
        probes=[GrillProbe(question=f"p{i}", angle="drill-down", listenFor="l") for i in range(6)],
        weakSpots=["a", " ", "b", "c", "d", "e", "f", "g"],
    )
    out = sanitize_grill_round(round_, n_exchanges=2)
    assert len(out.verdicts) == 2  # never more verdicts than answers given
    assert len(out.probes) == 4
    assert out.weakSpots == ["a", "b", "c", "d", "e", "f"]  # blanks out, capped at 6

    with pytest.raises(ValueError):
        sanitize_grill_round(GrillRound(verdicts=[], probes=[], weakSpots=[]), 0)


# --- Learning plan: the allowlist is the law ----------------------------------


def _plan(items):
    return LearningPlan(items=items, sequence="start with stats")


def test_invented_urls_die_and_curated_fields_win():
    plan = _plan([
        LearningItem(
            competency="statistics-probability", priority=5, why="JD says stats",
            topics=["p-values", ""],
            resources=[
                # invented link -> must not survive
                LearningResource(title="Great Stats Course", url="https://evil.example/stats"),
                # real curated URL but the model lied about the title
                LearningResource(title="Wrong Title", url="https://seeing-theory.brown.edu/"),
            ],
            practice="re-analyze an old A/B readout",
        ),
    ])
    out = sanitize_learning_plan(plan, DS_TARGET, DS_CELLS, "ds")
    stats = next(i for i in out.items if i.competency == "statistics-probability")
    urls = [r.url for r in stats.resources]
    assert "https://evil.example/stats" not in urls
    assert "https://seeing-theory.brown.edu/" in urls
    seeing = next(r for r in stats.resources if r.url == "https://seeing-theory.brown.edu/")
    assert seeing.title.startswith("Seeing Theory")  # curated fields replace the model's
    assert stats.topics == ["p-values"]  # blanks trimmed


def test_all_dead_links_fall_back_to_curated_picks():
    plan = _plan([
        LearningItem(
            competency="statistics-probability", priority=5, why="w", topics=[],
            resources=[LearningResource(title="x", url="https://evil.example/a")],
            practice="p",
        ),
    ])
    out = sanitize_learning_plan(plan, DS_TARGET, DS_CELLS, "ds")
    stats = next(i for i in out.items if i.competency == "statistics-probability")
    assert stats.resources, "fallback picks must fill in when every link dies"
    assert all(r.url in ALLOWED_RESOURCES for r in stats.resources)


def test_skipped_gaps_are_backfilled_and_off_track_dropped():
    plan = _plan([
        LearningItem(  # off-track (PM) item on a DS plan — dropped
            competency="product-sense", priority=3, why="w", topics=[],
            resources=[], practice="p"),
    ])
    out = sanitize_learning_plan(plan, DS_TARGET, DS_CELLS, "ds")
    comps = [i.competency for i in out.items]
    assert "product-sense" not in comps
    # both non-green cells came back even though the model skipped them...
    assert "statistics-probability" in comps and "experiment-design" in comps
    # ...the green one was not invented into homework
    assert "sql-data-wrangling" not in comps
    # red before amber, and the backfill carries the heatmap's own gap action
    assert comps[0] == "statistics-probability"
    stats = out.items[0]
    assert stats.why == "study inference for real"


def test_fallback_resources_are_always_allowlisted():
    for track_key in TRACKS:
        for comp in TRACKS[track_key]["taxonomy"]:
            for r in fallback_resources(track_key, comp):
                assert r["url"] in ALLOWED_RESOURCES, (track_key, comp, r["url"])


def test_resource_pool_leads_with_the_tracks_own_collection():
    ds_pool = resource_pool("ds")
    assert ds_pool[0]["topic"] == "Machine learning basics"  # KB first on ds
    pm_pool = resource_pool("pm")
    assert pm_pool[0]["topic"] == "structure"  # resources.py first on pm


# --- The loop map -------------------------------------------------------------


def test_rounds_are_ds_only_and_browser_safe():
    ds = rounds_for("ds")
    assert len(ds) >= 5  # the researched DS loop is substantial
    for r in ds:
        assert r["name"] and r["description"]
        assert 1 <= len(r["example_questions"]) <= 3
    assert rounds_for("pm") == []
    assert rounds_for("nonsense") == []


# --- New prompt files ---------------------------------------------------------

V3_PROMPTS = {
    "project-grill.md": {
        "ROLE_CONTEXT": "r", "TARGET_JSON": "{}", "PROJECT": "p",
        "UNITS_JSON": "[]", "EXCHANGES_JSON": "[]"},
    "grill-map.md": {"ROLE_CONTEXT": "r", "TARGET_JSON": "{}", "UNITS_JSON": "[]"},
    "learning-plan.md": {
        "ROLE_CONTEXT": "r", "TARGET_JSON": "{}", "CELLS_JSON": "[]",
        "UNITS_SUMMARY_JSON": "[]", "RESOURCES_JSON": "[]"},
}


def test_v3_prompts_live_on_disk_and_fill_cleanly():
    for name, subs in V3_PROMPTS.items():
        assert (PROMPTS_DIR / name).is_file(), f"missing prompts/{name}"
        filled = fill_prompt(load_prompt(name), **subs)
        for key in subs:
            assert f"<{key}>" not in filled


def test_v3_guardrail_language_survives_editing():
    assert "Do not invent facts" in load_prompt("project-grill.md")
    assert "Do NOT invent facts" in load_prompt("grill-map.md")
    assert "ONLY resources from" in load_prompt("learning-plan.md")
    assert "never invent" in load_prompt("learning-plan.md")


# --- The bank's cross-track contracts -----------------------------------------


@pytest.fixture()
def bank(tmp_path):
    b = PrepBank(str(tmp_path / "bank.db"))
    yield b
    b.close()


def test_extraction_merge_unions_competencies_editor_replaces(bank):
    bank.save_units("p@x.com", [dict(MIXED_UNIT, competencies=["data-driven-decisions"])])
    # a DS-page re-extraction of the same line tags only DS competencies...
    ds_view = dict(MIXED_UNIT, id="fresh9", competencies=["ml-fundamentals"])
    genome = bank.save_units("p@x.com", [ds_view], merge_competencies=True)
    assert len(genome) == 1
    assert set(genome[0]["competencies"]) == {"ml-fundamentals", "data-driven-decisions"}
    # ...but the EDITOR is the editor of record: an explicit save replaces
    edited = dict(genome[0], competencies=["ml-fundamentals"])
    genome = bank.save_units("p@x.com", [edited])
    assert genome[0]["competencies"] == ["ml-fundamentals"]


def test_learning_and_grill_persist_per_application(bank):
    tid = bank.save_target("p@x.com", DS_TARGET.model_dump(), [])
    assert bank.target("p@x.com", tid)["learning"] == {}
    assert bank.target("p@x.com", tid)["grill"] == []
    bank.save_learning("p@x.com", tid, {"items": [{"competency": "x"}], "sequence": "s"})
    bank.save_grill_map("p@x.com", tid, [{"unitId": "u1", "questions": []}])
    got = bank.target("p@x.com", tid)
    assert got["learning"]["sequence"] == "s"
    assert got["grill"][0]["unitId"] == "u1"
    assert bank.targets("p@x.com")[0]["track"] == "ds"


def test_pre_v3_database_migrates_in_place(tmp_path):
    # A database created before the learning/grill columns must open cleanly:
    # CREATE IF NOT EXISTS won't touch it, so the add-column migration must.
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE prep_targets (owner TEXT NOT NULL, id TEXT NOT NULL, "
        "json TEXT NOT NULL, heatmap TEXT NOT NULL DEFAULT '[]', "
        "updated_at REAL NOT NULL, PRIMARY KEY (owner, id))"
    )
    db.execute(
        "INSERT INTO prep_targets (owner, id, json, heatmap, updated_at) "
        "VALUES ('p@x.com', 't1', '{\"company\": \"Old Co\"}', '[]', 1.0)"
    )
    db.commit()
    db.close()

    bank = PrepBank(path)
    try:
        got = bank.target("p@x.com", "t1")
        assert got["target"]["company"] == "Old Co"
        assert got["learning"] == {} and got["grill"] == []
        assert bank.targets("p@x.com")[0]["track"] == "pm"  # pre-track row
        bank.save_learning("p@x.com", "t1", {"items": [], "sequence": "s"})
        assert bank.target("p@x.com", "t1")["learning"]["sequence"] == "s"
    finally:
        bank.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Prep Engine v1/v2 tests: the story bank's persistence contract and the
new feature sanitizers. Offline — fixtures stand in for model output."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep.prep_bank import (  # noqa: E402
    MAX_TARGETS,
    BankFull,
    PrepBank,
)
from pmcaseprep.prep_engine import (  # noqa: E402
    PROMPTS_DIR,
    Attack,
    AttackRound,
    fill_prompt,
    load_prompt,
    sanitize_attack_round,
    transcript_stats,
)

UNIT = {
    "id": "u1",
    "title": "Cut checkout drop-off",
    "context": "Acme",
    "action": "Led the revamp",
    "result": "Drop-off fell",
    "metric": "18%",
    "competencies": ["execution-delivery"],
    "skills": [],
    "scale": None,
    "type": "fix",
    "isFailure": False,
    "rawEvidence": "Led the checkout revamp; cut drop-off by 18%.",
}

TARGET = {"company": "Globex", "roleTitle": "Senior PM", "seniority": "Senior",
          "archetype": "Growth", "requiredCompetencies": [], "unwrittenPain": "x",
          "companyValues": []}


@pytest.fixture()
def bank(tmp_path):
    b = PrepBank(str(tmp_path / "bank.db"))
    yield b
    b.close()


# --- The genome: merge, don't duplicate ---------------------------------------


def test_reextraction_merges_instead_of_duplicating(bank):
    bank.save_units("p@x.com", [UNIT])
    tweaked = dict(UNIT, id="u9", metric="18% in 6 weeks")  # same title+evidence
    genome = bank.save_units("p@x.com", [tweaked])
    assert len(genome) == 1
    assert genome[0]["id"] == "u1"  # bank identity survives; stories stay valid
    assert genome[0]["metric"] == "18% in 6 weeks"  # but the edit lands


def test_different_evidence_is_a_new_unit(bank):
    bank.save_units("p@x.com", [UNIT])
    other = dict(UNIT, id="", title="Killed the loyalty launch",
                 rawEvidence="Killed the loyalty launch after 2 sprints.")
    genome = bank.save_units("p@x.com", [other])
    assert len(genome) == 2
    assert all(u["id"] for u in genome)


def test_colliding_id_from_fresh_extraction_never_overwrites(bank):
    bank.save_units("p@x.com", [UNIT])
    impostor = dict(UNIT, title="Some other thing", rawEvidence="other line")
    genome = bank.save_units("p@x.com", [impostor])  # also claims id "u1"
    assert len(genome) == 2
    titles = {u["title"] for u in genome}
    assert titles == {"Cut checkout drop-off", "Some other thing"}


def test_owners_are_isolated(bank):
    bank.save_units("a@x.com", [UNIT])
    assert bank.units("b@x.com") == []
    bank.delete_unit("b@x.com", "u1")  # deleting across owners is a no-op
    assert len(bank.units("a@x.com")) == 1


# --- Targets: the campaign dashboard ------------------------------------------


def test_target_roundtrip_with_heatmap_and_stories(bank):
    tid = bank.save_target("p@x.com", TARGET, [])
    bank.save_heatmap("p@x.com", tid, [{"competency": "product-sense",
                                        "strength": "red", "bestUnitId": None,
                                        "gapAction": "build one"}])
    sid = bank.save_story("p@x.com", {"spineTag": "s"}, "product-sense", tid)
    got = bank.target("p@x.com", tid)
    assert got["target"]["company"] == "Globex"
    assert got["cells"][0]["strength"] == "red"
    assert got["stories"][0]["id"] == sid
    assert got["stories"][0]["solid"] is False

    summaries = bank.targets("p@x.com")
    assert summaries[0]["red"] == 1 and summaries[0]["solidStories"] == 0

    assert bank.set_story_solid("p@x.com", sid, True)
    assert bank.targets("p@x.com")[0]["solidStories"] == 1
    assert bank.target("p@x.com", tid)["stories"][0]["solid"] is True


def test_deleting_a_target_keeps_the_genome(bank):
    bank.save_units("p@x.com", [UNIT])
    tid = bank.save_target("p@x.com", TARGET, [])
    bank.save_story("p@x.com", {"spineTag": "s"}, "product-sense", tid)
    bank.delete_target("p@x.com", tid)
    assert bank.target("p@x.com", tid) is None
    assert bank.stories("p@x.com", tid) == []
    assert len(bank.units("p@x.com")) == 1  # the genome is never collateral


def test_target_cap_is_enforced(bank):
    for i in range(MAX_TARGETS):
        bank.save_target("p@x.com", dict(TARGET, company=f"c{i}"), [])
    with pytest.raises(BankFull):
        bank.save_target("p@x.com", dict(TARGET, company="one too many"), [])
    # updating an EXISTING target must still work at the cap
    existing = bank.targets("p@x.com")[0]["id"]
    bank.save_target("p@x.com", dict(TARGET, company="updated"), [], existing)


def test_debrief_roundtrip(bank):
    tid = bank.save_target("p@x.com", TARGET, [])
    bank.save_debrief("p@x.com", "they asked about failure", {"lessons": []}, tid)
    got = bank.debriefs("p@x.com", tid)
    assert len(got) == 1 and got[0]["notes"] == "they asked about failure"


# --- New sanitizers -----------------------------------------------------------


def test_attack_round_bounds():
    round_ = AttackRound(
        verdicts=[{"question": f"q{i}", "verdict": "held", "why": "w"} for i in range(5)],
        attacks=[Attack(question=f"a{i}", probes="p", strongAnswer="s") for i in range(9)],
    )
    out = sanitize_attack_round(round_, n_exchanges=2)
    assert len(out.verdicts) == 2  # never more verdicts than answers given
    assert len(out.attacks) == 5

    with pytest.raises(ValueError):
        sanitize_attack_round(AttackRound(verdicts=[], attacks=[]), 0)


def test_transcript_stats_are_deterministic():
    s = transcript_stats("um so we cut drop-off by like eighteen percent um", 20.0)
    assert s["words"] == 10
    assert s["coreFillers"] == 2  # both "um"s
    assert s["softFillers"] == 2  # "so", "like"
    assert s["wpm"] == 30.0  # 10 words / (20s / 60)
    assert transcript_stats("", 0)["wpm"] == 0.0


# --- New prompt files ---------------------------------------------------------

NEW_PROMPTS = {
    "devils-advocate.md": {"STORY_JSON": "{}", "UNITS_JSON": "[]", "EXCHANGES_JSON": "[]"},
    "gap-sprint.md": {"COMPETENCY": "c", "GAP_ACTION": "g", "TARGET_JSON": "{}"},
    "interviewer-twin.md": {"TAXONOMY": "t", "NAME_AND_ROLE": "n", "SIGNALS": "s", "TARGET_JSON": "{}"},
    "mock-behavioral.md": {"MAX_QUESTIONS": "8", "TARGET_JSON": "{}", "CELLS_JSON": "[]"},
    "mock-scorecard.md": {"TARGET_JSON": "{}", "TRANSCRIPT": "t"},
    "debrief.md": {"TAXONOMY": "t", "TARGET_JSON": "{}", "NOTES": "n"},
    "delivery-check.md": {"QUESTION": "q", "TRANSCRIPT": "t"},
}


def test_new_prompts_live_on_disk_and_fill_cleanly():
    for name, subs in NEW_PROMPTS.items():
        assert (PROMPTS_DIR / name).is_file(), f"missing prompts/{name}"
        filled = fill_prompt(load_prompt(name), **subs)
        for key in subs:
            assert f"<{key}>" not in filled


def test_guardrail_language_survives_editing():
    # The truthfulness guardrails live in prose the user may edit — keep the
    # load-bearing phrases pinned so a careless edit fails a test, not a user.
    assert "Do not invent facts" in load_prompt("devils-advocate.md")
    assert "not language to\nspin" in load_prompt("gap-sprint.md") or "spin" in load_prompt("gap-sprint.md")
    assert "ONLY" in load_prompt("interviewer-twin.md")
    assert "DRAFTS" in load_prompt("debrief.md")
    assert "unprobed competency is unknown" in load_prompt("mock-scorecard.md")

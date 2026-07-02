"""Offline smoke tests — validate wiring without hitting the Anthropic API.

Run with:  python -m pytest -q     (or: python tests/test_smoke.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmcaseprep import prompts, rubric  # noqa: E402
from pmcaseprep.case_loader import default_case_path, list_cases, load_case  # noqa: E402
from pmcaseprep.grader import weighted_result  # noqa: E402
from pmcaseprep.models import (  # noqa: E402
    Case,
    DimensionScore,
    ScoreCard,
)


def test_cases_load_and_validate():
    cases = list_cases()
    assert cases, "expected at least one case in cases/"
    for path in cases:
        case = load_case(path)
        assert case.id and case.prompt and case.type


def test_default_case_is_ai_pm():
    case = load_case(default_case_path())
    assert isinstance(case, Case)
    assert case.hidden_facts  # interviewer needs facts to answer clarifications


def test_rubric_weights_normalize():
    for archetype in ("ai-pm", "growth", "consumer", "unknown-archetype"):
        w = rubric.weights_for(archetype)
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert set(w) == set(rubric.DIMENSION_KEYS)


def test_gate_caps_band_at_no_hire():
    # A single sub-bar dimension must gate the outcome even with high others.
    assert rubric.band_for(weighted_avg=3.9, min_dimension=2) == "no_hire"
    assert rubric.band_for(weighted_avg=3.9, min_dimension=3) == "strong_hire"


def test_prompts_omit_ideal_answer_from_interviewer():
    case = load_case(default_case_path())
    system = prompts.build_interviewer_system(case)
    # The interviewer must not be handed the model answer.
    for note in case.ideal_answer_notes:
        assert note not in system
    # ...but it must have the hidden facts to answer clarifications.
    assert any(v in system for v in case.hidden_facts.values())


def test_vision_builds_image_blocks(tmp_path=None):
    import base64

    from pmcaseprep import vision

    # 1x1 transparent PNG
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    p = Path(__file__).resolve().parent / "_tmp_pixel.png"
    p.write_bytes(png)
    try:
        blocks = vision.image_content(p, "my 2x2")
        assert blocks[0]["type"] == "image"
        assert blocks[0]["source"]["media_type"] == "image/png"
        assert blocks[1] == {"type": "text", "text": "my 2x2"}
    finally:
        p.unlink()


def test_transcribe_reports_missing_key(monkeypatch=None):
    import os

    from pmcaseprep import transcribe

    saved = os.environ.pop("DEEPGRAM_API_KEY", None)
    try:
        assert transcribe.voice_configured() is False
        try:
            transcribe.transcribe("does-not-matter.wav")
            assert False, "expected TranscriptionError without a key"
        except transcribe.TranscriptionError:
            pass
    finally:
        if saved is not None:
            os.environ["DEEPGRAM_API_KEY"] = saved


def test_weighted_result_is_deterministic():
    case = load_case(default_case_path())
    card = ScoreCard(
        dimension_scores=[
            DimensionScore(dimension=k, score=3, justification="ok")
            for k in rubric.DIMENSION_KEYS
        ],
        category_checklist=[],
        red_flags=[],
        top_improvement="x",
        overall_band="hire",
        summary="y",
    )
    weighted, min_dim, band = weighted_result(case, card)
    assert min_dim == 3
    assert round(weighted, 2) == 3.0
    assert band == "hire"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll smoke tests passed.")

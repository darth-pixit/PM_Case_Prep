"""Prep Engine — behavioral storytelling + CV tuning (the /prep experiment).

The v0 loop from the build spec: CV / brain-dump -> AchievementUnits (the
Career Genome), JD -> TargetProfile, units x target -> Coverage Heatmap, and
one cell -> a STAR Story in three lengths with anticipated follow-ups.

Two deliberate choices:

* Field names are camelCase, mirroring the spec's TypeScript types exactly, so
  the JSON the browser sees is identical to what a Next.js port would produce
  and the data model transfers byte-for-byte.
* Truthfulness is enforced twice. The prompts (loaded from /prompts/*.md so
  they can be edited without a rebuild) forbid invention — but prompts are
  requests, not guarantees, so a deterministic audit pass runs on everything
  the model returns: metrics whose digits aren't in the source get nulled,
  story numbers that appear in no referenced unit land in `unverifiedClaims`,
  heatmap cells pointing at nonexistent units lose their evidence claim, and
  a "green" with no evidence is downgraded. The model can be wrong; the
  guards make sure it can't be wrong *silently*.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional, get_args

from pydantic import BaseModel, Field, ValidationError

from .delivery import FILLERS_CORE, FILLERS_SOFT

# --- The competency taxonomy (closed list, spec section 4) --------------------

Competency = Literal[
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
]
TAXONOMY: tuple[str, ...] = get_args(Competency)

UnitType = Literal[
    "launch", "growth", "fix", "strategy", "conflict", "leadership", "research"
]


# --- Core data model (spec section 4) -----------------------------------------


class AchievementUnit(BaseModel):
    """The atom of the Career Genome. One accomplishment, fully self-contained."""

    id: str
    title: str  # short handle, e.g. "Cut onboarding drop-off"
    context: str  # company / team / timeframe
    action: str  # what THEY specifically did
    result: str  # outcome in words
    metric: Optional[str] = None  # quantified impact — null if none given
    competencies: list[Competency]
    skills: list[str]  # tools/domains: SQL, pricing, mobile, ...
    scale: Optional[str] = None  # team size / users / $ / etc.
    type: UnitType
    isFailure: bool  # conflict / failed launch / wrong call — behavioral gold
    rawEvidence: str  # the exact CV bullet or note it came from (provenance)


class StoryVersions(BaseModel):
    thirtySec: str
    twoMin: str
    deepDive: str


class Story(BaseModel):
    """A composed answer, built by recombining units for a target role."""

    id: str
    spineTag: str  # the one-line thread this reinforces
    unitIds: list[str]  # which achievement units it draws on
    competenciesCovered: list[Competency]
    versions: StoryVersions
    anticipatedFollowups: list[str]  # nasty questions, pre-answered
    deliveryNotes: Optional[str] = None  # pacing / structure reminders (v1+)
    unverifiedClaims: list[str] = Field(default_factory=list)


class RequiredCompetency(BaseModel):
    competency: Competency
    weight: Literal[1, 2, 3, 4, 5]
    evidence: str  # the JD phrase that justifies it


class TargetProfile(BaseModel):
    """The role you're prepping for. interviewerProfiles is v2 — added when it exists."""

    company: str
    roleTitle: str
    seniority: Literal["APM", "PM", "Senior", "Group", "Director"]
    archetype: str  # Growth / Platform / 0-1 / Data / AI ...
    requiredCompetencies: list[RequiredCompetency]
    unwrittenPain: str  # inferred: the real problem behind the hire
    companyValues: list[str]


class CoverageCell(BaseModel):
    """One cell of the Coverage Heatmap."""

    competency: Competency
    strength: Literal["green", "amber", "red"]
    bestUnitId: Optional[str] = None  # strongest supporting unit, if any
    gapAction: Optional[str] = None  # if amber/red: how to CLOSE the gap


# Wrappers because messages.parse() wants a single object, not a bare array.
class ExtractedUnits(BaseModel):
    units: list[AchievementUnit]


class Heatmap(BaseModel):
    cells: list[CoverageCell]


# --- v1/v2 data model: pressure-test, sprint, twin, mock, debrief, delivery ---


class AttackVerdict(BaseModel):
    """Judgment of the user's answer to one earlier attack."""

    question: str
    verdict: Literal["held", "cracked"]
    why: str


class Attack(BaseModel):
    question: str
    probes: str  # the weakness this attack targets
    strongAnswer: str  # what good looks like — grounded in the units


class AttackRound(BaseModel):
    """One round of Devil's Advocate: verdicts on prior answers + new attacks."""

    verdicts: list[AttackVerdict]
    attacks: list[Attack]


class SprintMilestone(BaseModel):
    days: str  # e.g. "Days 1-2"
    task: str
    output: str


class GapSprint(BaseModel):
    """A red cell turned into a concrete 2-week become-qualified plan."""

    competency: Competency
    goal: str
    milestones: list[SprintMilestone]
    deliverable: str
    proofMetric: str  # the number the candidate can truthfully claim after
    unitOutline: str  # the achievement unit this becomes once done


class InterviewerProfile(BaseModel):
    """Spec v2 type — public info only, supplied BY the user."""

    name: str
    role: str
    publicSignals: list[str]  # talks, posts, background -> what they'll probe
    likelyFocus: list[Competency]


class PredictedQuestion(BaseModel):
    question: str
    competency: Competency


class InterviewerTwin(BaseModel):
    profile: InterviewerProfile
    predictedQuestions: list[PredictedQuestion]
    prepTips: list[str]  # tuning, never fabrication
    rationale: str  # how strong the signal base actually is


class MockScore(BaseModel):
    competency: Competency
    score: Literal[1, 2, 3, 4]
    justification: str


class MockScorecard(BaseModel):
    """Grades only what the mock actually probed — unprobed is unknown, not 1."""

    scores: list[MockScore]
    topImprovement: str
    pressureTestNext: list[Competency]


class DebriefLesson(BaseModel):
    lesson: str
    adjustment: str


class FocusItem(BaseModel):
    competency: Competency
    why: str


class DebriefInsights(BaseModel):
    """Mined from a real interview's debrief; suggestedUnits are DRAFTS the
    user must confirm before they enter the bank."""

    lessons: list[DebriefLesson]
    suggestedUnits: list[AchievementUnit]
    focusNext: list[FocusItem]


class DeliveryCheck(BaseModel):
    structure: str  # one-sentence verdict on the spine
    answered: bool  # did it answer THE question asked?
    answeredNote: str
    cuts: list[str]  # phrases worth deleting, quoted
    rewrite: str  # strongest 2-sentence version, transcript facts only


# --- Prompts: loaded from /prompts/*.md, never inlined ------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def fill_prompt(template: str, **subs: str) -> str:
    """Replace <PLACEHOLDER> tokens. Every placeholder must be consumed —
    a prompt sent with a dangling <TAXONOMY> is a silent quality bug."""
    for key, value in subs.items():
        token = f"<{key}>"
        if token not in template:
            raise KeyError(f"prompt is missing placeholder {token}")
        template = template.replace(token, value)
    return template


# --- Truthfulness guards (deterministic; run on every model response) ---------

_NUM_RE = re.compile(r"\d[\d,.]*")


def _numbers(text: str) -> set[str]:
    """Digit-groups in `text`, normalized so "1,200" == "1200" and a trailing
    sentence period doesn't make "40." a different number than "40"."""
    return {n.replace(",", "").rstrip(".") for n in _NUM_RE.findall(text or "")}


GENERIC_GAP = (
    "No verifiable evidence in your inputs yet. Pick a small real project that "
    "exercises {competency}, run it, and capture one concrete metric — then it "
    "becomes a true story, not spin."
)


def sanitize_units(
    raw: list[dict], source: Optional[str] = None
) -> list[AchievementUnit]:
    """Validate + audit extracted units.

    - competencies outside the closed taxonomy are dropped (not guessed);
    - ids are made unique and non-empty so the heatmap/story can reference them;
    - with `source` given (extraction time), a metric whose numbers don't appear
      in that source text is NULLED — the spec's "never invent" rule enforced in
      code, not just in the prompt. Without `source` (re-validating units that
      round-tripped through the browser), the metric audit is skipped: it
      already ran at extraction and the original CV isn't in the request.
    """
    src_numbers = _numbers(source) if source is not None else None
    out: list[AchievementUnit] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        item = dict(item)
        item["competencies"] = [
            c for c in (item.get("competencies") or []) if c in TAXONOMY
        ]
        unit = AchievementUnit.model_validate(item)
        base = unit.id.strip() or f"u{i + 1}"
        uid, n = base, 1
        while uid in seen:
            n += 1
            uid = f"{base}-{n}"
        seen.add(uid)
        unit.id = uid
        if unit.metric is not None:
            metric = unit.metric.strip()
            if not metric or (
                src_numbers is not None and not _numbers(metric) <= src_numbers
            ):
                unit.metric = None
        out.append(unit)
    return out


def sanitize_target(target: TargetProfile) -> TargetProfile:
    """Dedupe required competencies (keep the highest weight per competency)."""
    best: dict[str, RequiredCompetency] = {}
    for rc in target.requiredCompetencies:
        prev = best.get(rc.competency)
        if prev is None or rc.weight > prev.weight:
            best[rc.competency] = rc
    target.requiredCompetencies = list(best.values())
    if not target.requiredCompetencies:
        raise ValueError("the model returned no required competencies")
    return target


def sanitize_heatmap(
    raw_cells: list[dict], target: TargetProfile, units: list[AchievementUnit]
) -> list[CoverageCell]:
    """One cell per required competency, in the target's order, with the
    evidence claims verified:

    - a bestUnitId that matches no actual unit is cleared;
    - "green" without a real supporting unit is downgraded to amber (green
      MEANS direct evidence exists);
    - amber/red cells always carry a gapAction (an honest generic one if the
      model omitted it); green cells never do;
    - required competencies the model skipped come back as red — a silent
      missing row would read as "covered".
    """
    unit_ids = {u.id for u in units}
    by_comp: dict[str, CoverageCell] = {}
    for item in raw_cells:
        try:
            cell = CoverageCell.model_validate(item)
        except ValidationError:
            continue  # one malformed cell shouldn't sink the whole heatmap
        if cell.bestUnitId is not None and cell.bestUnitId not in unit_ids:
            cell.bestUnitId = None
        if cell.strength == "green" and cell.bestUnitId is None:
            cell.strength = "amber"
        if cell.strength == "green":
            cell.gapAction = None
        elif not (cell.gapAction or "").strip():
            cell.gapAction = GENERIC_GAP.format(competency=cell.competency)
        by_comp.setdefault(cell.competency, cell)
    cells: list[CoverageCell] = []
    for rc in target.requiredCompetencies:
        cells.append(
            by_comp.get(rc.competency)
            or CoverageCell(
                competency=rc.competency,
                strength="red",
                bestUnitId=None,
                gapAction=GENERIC_GAP.format(competency=rc.competency),
            )
        )
    return cells


def audit_story(story: Story, units: list[AchievementUnit]) -> Story:
    """Flag numbers in the story that appear in none of its source units.

    Conservative on purpose: a false positive costs the user one confirming
    glance; a false negative is a fabricated metric spoken in a real interview.
    The model is asked to self-report invented specifics — this catches the
    ones it didn't.
    """
    known: set[str] = set()
    for u in units:
        known |= _numbers(
            " ".join(
                [u.title, u.context, u.action, u.result, u.metric or "",
                 u.scale or "", u.rawEvidence, *u.skills]
            )
        )
    flags = list(story.unverifiedClaims)
    already = set(flags)
    for text in (
        story.versions.thirtySec,
        story.versions.twoMin,
        story.versions.deepDive,
    ):
        for num in sorted(_numbers(text) - known):
            claim = (
                f'The number "{num}" does not appear in your source units — '
                "confirm it's real or cut it."
            )
            if claim not in already:
                already.add(claim)
                flags.append(claim)
    story.unverifiedClaims = flags
    story.unitIds = [uid for uid in story.unitIds if uid in {u.id for u in units}]
    return story


# --- Model calls (one careful structured-output call each) --------------------


def _taxonomy_str() -> str:
    return ", ".join(TAXONOMY)


def extract_units(client: Any, cv_text: str, model: str) -> list[AchievementUnit]:
    prompt = fill_prompt(
        load_prompt("extract-units.md"),
        TAXONOMY=_taxonomy_str(),
        CV_OR_BRAINDUMP=cv_text,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
        output_format=ExtractedUnits,
    )
    raw = [u.model_dump() for u in resp.parsed_output.units]
    return sanitize_units(raw, cv_text)


def extract_target(client: Any, jd_text: str, model: str) -> TargetProfile:
    prompt = fill_prompt(
        load_prompt("extract-target.md"),
        TAXONOMY=_taxonomy_str(),
        JOB_DESCRIPTION=jd_text,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_format=TargetProfile,
    )
    return sanitize_target(resp.parsed_output)


def score_coverage(
    client: Any, units: list[AchievementUnit], target: TargetProfile, model: str
) -> list[CoverageCell]:
    prompt = fill_prompt(
        load_prompt("score-coverage.md"),
        UNITS_JSON=json.dumps([u.model_dump() for u in units]),
        REQUIRED_COMPETENCIES_JSON=json.dumps(
            [rc.model_dump() for rc in target.requiredCompetencies]
        ),
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        output_format=Heatmap,
    )
    raw = [c.model_dump() for c in resp.parsed_output.cells]
    return sanitize_heatmap(raw, target, units)


def craft_story(
    client: Any,
    spine: str,
    competency: str,
    units: list[AchievementUnit],
    model: str,
) -> Story:
    prompt = fill_prompt(
        load_prompt("craft-story.md"),
        SPINE_TAG=spine,
        COMPETENCY=competency,
        REFERENCED_UNITS_JSON=json.dumps([u.model_dump() for u in units]),
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=5000,
        thinking={"type": "adaptive"},  # storycraft benefits from a beat of thought
        messages=[{"role": "user", "content": prompt}],
        output_format=Story,
    )
    return audit_story(resp.parsed_output, units)


# --- v1: Devil's Advocate (pressure-test until solid) -------------------------


def sanitize_attack_round(round_: AttackRound, n_exchanges: int) -> AttackRound:
    """Bound the round: verdicts only for answers that exist, 1-5 attacks."""
    round_.verdicts = round_.verdicts[:n_exchanges]
    round_.attacks = round_.attacks[:5]
    if not round_.attacks:
        raise ValueError("the devil's advocate returned no attacks")
    return round_


def devils_advocate(
    client: Any,
    story: Story,
    units: list[AchievementUnit],
    exchanges: list[dict],
    model: str,
) -> AttackRound:
    """One adversarial round. `exchanges` = [{question, answer}] from earlier
    rounds; the model judges those answers, then attacks again. The loop ends
    when the USER marks the story solid — bulletproof is their call, not ours."""
    prompt = fill_prompt(
        load_prompt("devils-advocate.md"),
        STORY_JSON=json.dumps(story.model_dump()),
        UNITS_JSON=json.dumps([u.model_dump() for u in units]),
        EXCHANGES_JSON=json.dumps(exchanges),
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        thinking={"type": "adaptive"},  # judging answers fairly needs care
        messages=[{"role": "user", "content": prompt}],
        output_format=AttackRound,
    )
    return sanitize_attack_round(resp.parsed_output, len(exchanges))


# --- v2: Gap-to-Sprint (red cell -> 2-week credibility plan) ------------------


def gap_sprint(
    client: Any, competency: str, gap_action: str, target: TargetProfile, model: str
) -> GapSprint:
    prompt = fill_prompt(
        load_prompt("gap-sprint.md"),
        COMPETENCY=competency,
        GAP_ACTION=gap_action or "no evidence yet",
        TARGET_JSON=json.dumps(target.model_dump()),
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_format=GapSprint,
    )
    sprint = resp.parsed_output
    if not sprint.milestones:
        raise ValueError("sprint came back without milestones")
    return sprint


# --- v2: Interviewer Twin (public signals only, supplied by the user) ---------


def interviewer_twin(
    client: Any,
    name: str,
    role: str,
    signals: str,
    target: TargetProfile,
    model: str,
) -> InterviewerTwin:
    prompt = fill_prompt(
        load_prompt("interviewer-twin.md"),
        TAXONOMY=_taxonomy_str(),
        NAME_AND_ROLE=f"{name} — {role}",
        SIGNALS=signals,
        TARGET_JSON=json.dumps(target.model_dump()),
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_format=InterviewerTwin,
    )
    twin = resp.parsed_output
    twin.predictedQuestions = twin.predictedQuestions[:8]
    return twin


# --- v2: mock interview loop (adaptive probing of the weakest competencies) ---

MOCK_MAX_QUESTIONS = 8


def mock_system(target: TargetProfile, cells: list[CoverageCell]) -> str:
    return fill_prompt(
        load_prompt("mock-behavioral.md"),
        MAX_QUESTIONS=str(MOCK_MAX_QUESTIONS),
        TARGET_JSON=json.dumps(target.model_dump()),
        CELLS_JSON=json.dumps([c.model_dump() for c in cells]),
    )


def mock_reply(
    client: Any,
    messages: list[dict],
    target: TargetProfile,
    cells: list[CoverageCell],
    model: str,
) -> str:
    """One interviewer turn. The transcript lives in the browser; the system
    prompt (stable across the whole mock) is cached like the recruiter's."""
    resp = client.messages.create(
        model=model,
        max_tokens=600,  # real interviewers ask short questions
        system=[
            {
                "type": "text",
                "text": mock_system(target, cells),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def mock_scorecard(
    client: Any, transcript: str, target: TargetProfile, model: str
) -> MockScorecard:
    prompt = fill_prompt(
        load_prompt("mock-scorecard.md"),
        TARGET_JSON=json.dumps(target.model_dump()),
        TRANSCRIPT=transcript,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        thinking={"type": "adaptive"},  # grading deserves the careful path
        messages=[{"role": "user", "content": prompt}],
        output_format=MockScorecard,
    )
    return resp.parsed_output


# --- v2: debrief -> write-back ------------------------------------------------


def debrief_insights(
    client: Any, notes: str, target: TargetProfile, model: str
) -> DebriefInsights:
    """Mine a real interview's debrief. suggestedUnits pass through the same
    truthfulness audit as extraction — grounded in the debrief text itself, so
    a metric the user didn't write gets nulled before they even see it."""
    prompt = fill_prompt(
        load_prompt("debrief.md"),
        TAXONOMY=_taxonomy_str(),
        TARGET_JSON=json.dumps(target.model_dump()),
        NOTES=notes,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        output_format=DebriefInsights,
    )
    insights = resp.parsed_output
    insights.suggestedUnits = sanitize_units(
        [u.model_dump() for u in insights.suggestedUnits], source=notes
    )
    insights.focusNext = insights.focusNext[:3]
    return insights


# --- v1: delivery self-check (rehearse one answer aloud) ----------------------


def transcript_stats(transcript: str, seconds: float) -> dict:
    """Deterministic delivery numbers — computed, never model-guessed.
    Browser speech recognition gives no word timings, so pace is overall
    words-per-minute and fillers are exact token counts."""
    tokens = [
        "".join(ch for ch in t.lower() if ch.isalpha())
        for t in transcript.split()
    ]
    tokens = [t for t in tokens if t]
    minutes = seconds / 60 if seconds > 0 else 0
    return {
        "words": len(tokens),
        "seconds": round(seconds, 1),
        "wpm": round(len(tokens) / minutes, 1) if minutes else 0.0,
        "coreFillers": sum(1 for t in tokens if t in FILLERS_CORE),
        "softFillers": sum(1 for t in tokens if t in FILLERS_SOFT),
    }


def delivery_check(
    client: Any, question: str, transcript: str, model: str
) -> DeliveryCheck:
    prompt = fill_prompt(
        load_prompt("delivery-check.md"),
        QUESTION=question,
        TRANSCRIPT=transcript,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_format=DeliveryCheck,
    )
    return resp.parsed_output

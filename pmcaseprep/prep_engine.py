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
from .prep_tracks import (
    ALLOWED_RESOURCES,
    DS_TAXONOMY,
    PM_TAXONOMY,
    all_competencies,
    fallback_resources,
    resource_pool,
)
from .prep_tracks import track as track_config

# --- The competency taxonomies (closed lists; per-track tuples live in
# --- prep_tracks.py, and this Literal is the union both tracks share so one
# --- schema serves every structured-output call) ------------------------------

Competency = Literal[
    # pm (spec section 4)
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
    # ds (grounded in the recruiter_kb research pass)
    "sql-data-wrangling",
    "statistics-probability",
    "ml-fundamentals",
    "experiment-design",
    "product-metrics-sense",
    "ml-system-design",
    "genai-llm-fluency",
    "coding-engineering-rigor",
    "data-storytelling",
    "stakeholder-influence",
    "project-ownership",
    "business-impact",
]
TAXONOMY: tuple[str, ...] = PM_TAXONOMY  # the spec's original PM list, unchanged

# The Literal above and the track tuples must never drift apart — fail the
# import, not a 3am extraction.
assert set(get_args(Competency)) == set(all_competencies())

UnitType = Literal[
    # pm-flavored
    "launch", "growth", "fix", "strategy", "conflict", "leadership", "research",
    # ds-flavored
    "analysis", "model", "pipeline", "experiment",
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
    """The role you're prepping for. interviewerProfiles is v2 — added when it exists.

    `track` names the role family (which taxonomy + page owns this target);
    it is set by the SERVER from the requesting page, never by the model, and
    defaults to "pm" so every pre-track saved row stays valid."""

    company: str
    roleTitle: str
    seniority: Literal[
        "APM", "PM", "Senior", "Group", "Director",  # pm ladder
        "Junior", "Mid", "Staff", "Principal", "Lead",  # ds ladder (Senior shared)
    ]
    archetype: str  # Growth / Platform / 0-1 / Data / AI ...
    requiredCompetencies: list[RequiredCompetency]
    unwrittenPain: str  # inferred: the real problem behind the hire
    companyValues: list[str]
    track: Literal["pm", "ds"] = "pm"


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


# --- v3 data model: project/CV grilling + the learning plan -------------------

# The interrogation angles real deep-dive rounds cycle through (mirrors the
# evaluation techniques researched in recruiter_kb: drill-down, trade-off,
# failure, constraint twist, ownership audit, impact anchor — plus "rigor",
# the methodology probe that DS loops add).
GrillAngle = Literal[
    "drill-down",
    "trade-off",
    "failure",
    "constraint-twist",
    "ownership",
    "impact",
    "rigor",
]


class GrillProbe(BaseModel):
    question: str
    angle: GrillAngle
    listenFor: str  # what a strong answer contains — grounded in the project


class GrillRound(BaseModel):
    """One round of the project grill: verdicts on prior answers, next probes,
    and the running list of weak spots exposed so far."""

    verdicts: list[AttackVerdict]
    probes: list[GrillProbe]
    weakSpots: list[str]


class GrillQuestion(BaseModel):
    question: str
    trap: str  # the weakness this question hunts


class GrillMapRow(BaseModel):
    """The exhaustive-CV-prep atom: one unit, pre-interrogated."""

    unitId: str
    questions: list[GrillQuestion]


class GrillMap(BaseModel):
    rows: list[GrillMapRow]


class LearningResource(BaseModel):
    """One curated link. URLs are allowlisted against prep_tracks — a URL the
    curation pass never verified cannot survive the sanitizer."""

    title: str
    url: str
    kind: str = "article"
    time: str = ""


class LearningItem(BaseModel):
    competency: Competency
    priority: Literal[1, 2, 3, 4, 5]
    why: str  # tied to the JD's own words and the heatmap strength
    topics: list[str]  # the concrete subtopics to actually study
    resources: list[LearningResource]
    practice: str  # the do-something exercise that proves it stuck


class LearningPlan(BaseModel):
    items: list[LearningItem]
    sequence: str  # one short paragraph: what to do first and why


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
    raw: list[dict],
    source: Optional[str] = None,
    taxonomy: Optional[tuple[str, ...]] = None,
) -> list[AchievementUnit]:
    """Validate + audit extracted units.

    - competencies outside the closed taxonomy are dropped (not guessed).
      `taxonomy` narrows the check to one track's list (extraction time, so a
      DS extraction can't tag PM competencies); the default is the union of
      all tracks, which is what round-tripped units need — the genome is
      shared across tracks and a PM tag must survive a DS-page save;
    - ids are made unique and non-empty so the heatmap/story can reference them;
    - with `source` given (extraction time), a metric whose numbers don't appear
      in that source text is NULLED — the spec's "never invent" rule enforced in
      code, not just in the prompt. Without `source` (re-validating units that
      round-tripped through the browser), the metric audit is skipped: it
      already ran at extraction and the original CV isn't in the request.
    """
    allowed = set(taxonomy if taxonomy is not None else all_competencies())
    src_numbers = _numbers(source) if source is not None else None
    out: list[AchievementUnit] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        item = dict(item)
        item["competencies"] = [
            c for c in (item.get("competencies") or []) if c in allowed
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


def sanitize_target(
    target: TargetProfile, track_key: Optional[str] = None
) -> TargetProfile:
    """Dedupe required competencies (keep the highest weight per competency).
    With `track_key` given (extraction time), the track is stamped on the
    target server-side and competencies from the OTHER track's taxonomy are
    dropped — the schema Literal is the union, so the model could otherwise
    hand a DS heatmap a PM row."""
    if track_key is not None:
        target.track = "ds" if track_key == "ds" else "pm"
    allowed = set(track_config(target.track)["taxonomy"])
    best: dict[str, RequiredCompetency] = {}
    for rc in target.requiredCompetencies:
        if rc.competency not in allowed:
            continue
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


def _taxonomy_str(taxonomy: Optional[tuple[str, ...]] = None) -> str:
    return ", ".join(taxonomy if taxonomy is not None else TAXONOMY)


class PrepTruncated(RuntimeError):
    """The model ran out of output budget before finishing its JSON.

    Its own class because it is the one engine failure with a *user* fix
    (shorten the input) rather than an operator fix, so the web layer can say
    so instead of showing the generic error.
    """


def _thinking_for(model: str, adaptive: bool = False) -> Optional[dict]:
    """The `thinking` setting for a model call — never left to default.

    Most calls in this module are the same shape: read some text, emit JSON
    against a fixed schema. There is no multi-step reasoning to do, so thinking
    buys nothing there — and leaving it unset actively breaks the call on
    current models. Omitting `thinking` used to mean "no thinking"; on
    claude-sonnet-5 and claude-opus-5 it means ADAPTIVE thinking, and
    `max_tokens` caps the thinking and the JSON *together*. A long CV then
    spends the budget reasoning, the JSON truncates mid-object, and
    messages.parse() raises — which is what reaches the browser as "the engine
    hit a snag".

    So we always say what we want, and `adaptive=True` is how a call that
    genuinely wants a beat of thought (storycraft) asks for it explicitly
    rather than by omission. Fable/Mythos are the exception in the other
    direction: thinking is always on there and an explicit
    {"type": "disabled"} is a 400, so for those we omit the field entirely.
    """
    lowered = model.lower()
    if "fable" in lowered or "mythos" in lowered:
        return None
    return {"type": "adaptive"} if adaptive else {"type": "disabled"}


def _parse(
    client: Any,
    *,
    model: str,
    prompt: str,
    output_format: type,
    max_tokens: int,
    adaptive: bool = False,
    system: Optional[list[dict]] = None,
) -> Any:
    """Every structured call goes through here, so the thinking setting and the
    truncation check can never drift apart across the fourteen call sites."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_format": output_format,
    }
    thinking = _thinking_for(model, adaptive)
    if thinking is not None:
        kwargs["thinking"] = thinking
    if system is not None:
        kwargs["system"] = system
    resp = client.messages.parse(**kwargs)
    # Belt and braces: a schema loose enough to validate a short answer can
    # still have been cut off. Don't hand back a half-read CV as if it were
    # the whole thing.
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise PrepTruncated(f"{output_format.__name__} hit max_tokens ({max_tokens})")
    return resp.parsed_output


def extract_units(
    client: Any, cv_text: str, model: str, track_key: str = "pm"
) -> list[AchievementUnit]:
    tr = track_config(track_key)
    prompt = fill_prompt(
        load_prompt("extract-units.md"),
        ROLE_CONTEXT=tr["extract_context"],
        TAXONOMY=_taxonomy_str(tr["taxonomy"]),
        CV_OR_BRAINDUMP=cv_text,
    )
    # The heaviest call in the engine: one object per achievement, each one
    # quoting its source line back verbatim, for a CV up to PREP_MAX_CHARS.
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=ExtractedUnits,
        max_tokens=16000,
    )
    raw = [u.model_dump() for u in parsed.units]
    return sanitize_units(raw, cv_text, taxonomy=tr["taxonomy"])


def generic_target(
    track_key: str = "pm", archetype: Optional[str] = None
) -> TargetProfile:
    """The target to prep against when there is NO job description.

    The JD is optional by design — you prep for a role, not only for one
    opening. Everything downstream (heatmap, stories, grill map, learning
    plan) reads a TargetProfile, so rather than special-casing the no-JD path
    through the whole engine we build an honest profile here:

    - no company is invented (the field stays empty),
    - every competency in the track's taxonomy is required at equal weight,
      because without a JD we have no basis to rank one above another,
    - each `evidence` string says plainly that it came from the role family
      and not from a posting, so nothing downstream can mistake it for a
      quote from a real JD.

    `archetype` is the ONE optional question we're willing to ask — the role
    category (AI PM, Growth PM, …) when the candidate happens to know it.
    Anything outside the track's own list is ignored rather than trusted, so
    the fallback is always the plain generic role. We deliberately do NOT ask
    for seniority: without a posting we have no honest way to pick a rung, so
    the schema's required field takes the track's middle default and no prose
    claims a level.

    Costs no model call — there is no text to read.
    """
    tr = track_config(track_key)
    flavour = (archetype or "").strip()
    if flavour not in tr["archetype_options"]:
        flavour = tr["default_archetype"]
    generic = flavour == tr["default_archetype"]
    described = tr["role_noun"] if generic else f"{flavour} {tr['role_noun']}"
    return sanitize_target(
        TargetProfile(
            company="",
            roleTitle=described[:1].upper() + described[1:],
            seniority=tr["default_seniority"],
            archetype=flavour,
            requiredCompetencies=[
                RequiredCompetency(
                    competency=c,
                    weight=3,
                    evidence=f"No job description — core competency for {described} roles.",
                )
                for c in tr["taxonomy"]
            ],
            unwrittenPain=(
                f"No specific opening: preparing for {described} roles in "
                "general, so treat every competency as equally likely to be "
                "tested."
            ),
            companyValues=[],
        ),
        track_key=tr["key"],
    )


def extract_target(
    client: Any, jd_text: str, model: str, track_key: str = "pm"
) -> TargetProfile:
    tr = track_config(track_key)
    prompt = fill_prompt(
        load_prompt("extract-target.md"),
        ROLE_CONTEXT=tr["target_context"],
        TAXONOMY=_taxonomy_str(tr["taxonomy"]),
        SENIORITY_LADDER=" | ".join(tr["seniority"]),
        ARCHETYPES=tr["archetypes"],
        JOB_DESCRIPTION=jd_text,
    )
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=TargetProfile,
        max_tokens=6000,
    )
    return sanitize_target(parsed, track_key=tr["key"])


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
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=Heatmap,
        max_tokens=8000,
    )
    raw = [c.model_dump() for c in parsed.cells]
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
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=Story,
        # Storycraft benefits from a beat of thought, so this one keeps
        # adaptive thinking — and gets the headroom to pay for it.
        adaptive=True,
        max_tokens=12000,
    )
    return audit_story(parsed, units)


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
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=AttackRound,
        adaptive=True,  # judging answers fairly needs care
        max_tokens=8000,
    )
    return sanitize_attack_round(parsed, len(exchanges))


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
    sprint = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=GapSprint,
        max_tokens=6000,
    )
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
        TAXONOMY=_taxonomy_str(track_config(target.track)["taxonomy"]),
        NAME_AND_ROLE=f"{name} — {role}",
        SIGNALS=signals,
        TARGET_JSON=json.dumps(target.model_dump()),
    )
    twin = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=InterviewerTwin,
        max_tokens=6000,
    )
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
    # 600 tokens is the right size for an interviewer's question, but it is
    # only safe as a ceiling once thinking is off: with thinking left to
    # default, a Claude 5 model spends the whole 600 reasoning and the reply
    # comes back empty. Keep the question short by instruction, not by a
    # budget the model has to share.
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 2000,
        "system": [
            {
                "type": "text",
                "text": mock_system(target, cells),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": messages,
    }
    thinking = _thinking_for(model)
    if thinking is not None:
        kwargs["thinking"] = thinking
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def mock_scorecard(
    client: Any, transcript: str, target: TargetProfile, model: str
) -> MockScorecard:
    prompt = fill_prompt(
        load_prompt("mock-scorecard.md"),
        TARGET_JSON=json.dumps(target.model_dump()),
        TRANSCRIPT=transcript,
    )
    return _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=MockScorecard,
        adaptive=True,  # grading deserves the careful path
        max_tokens=8000,
    )


# --- v2: debrief -> write-back ------------------------------------------------


def debrief_insights(
    client: Any, notes: str, target: TargetProfile, model: str
) -> DebriefInsights:
    """Mine a real interview's debrief. suggestedUnits pass through the same
    truthfulness audit as extraction — grounded in the debrief text itself, so
    a metric the user didn't write gets nulled before they even see it."""
    taxonomy = track_config(target.track)["taxonomy"]
    prompt = fill_prompt(
        load_prompt("debrief.md"),
        TAXONOMY=_taxonomy_str(taxonomy),
        TARGET_JSON=json.dumps(target.model_dump()),
        NOTES=notes,
    )
    insights = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=DebriefInsights,
        max_tokens=8000,
    )
    insights.suggestedUnits = sanitize_units(
        [u.model_dump() for u in insights.suggestedUnits],
        source=notes,
        taxonomy=taxonomy,
    )
    insights.focusNext = insights.focusNext[:3]
    return insights


# --- v3: project & CV grilling ------------------------------------------------


def sanitize_grill_map(
    raw_rows: list[dict], units: list[AchievementUnit]
) -> list[GrillMapRow]:
    """Rows must point at real units (one row per unit, first wins), carry
    1-3 questions each, and a malformed row never sinks the map. Units the
    model skipped stay visibly absent — the page renders every unit, so a
    missing row reads as "not grilled yet", never as "nothing to ask"."""
    unit_ids = {u.id for u in units}
    seen: set[str] = set()
    rows: list[GrillMapRow] = []
    for item in raw_rows:
        try:
            row = GrillMapRow.model_validate(item)
        except ValidationError:
            continue
        if row.unitId not in unit_ids or row.unitId in seen:
            continue
        row.questions = row.questions[:3]
        if not row.questions:
            continue
        seen.add(row.unitId)
        rows.append(row)
    return rows


def sanitize_grill_round(round_: GrillRound, n_exchanges: int) -> GrillRound:
    """Bound the round: verdicts only for answers that exist, 1-4 probes,
    at most 6 running weak spots."""
    round_.verdicts = round_.verdicts[:n_exchanges]
    round_.probes = round_.probes[:4]
    if not round_.probes:
        raise ValueError("the grill returned no probes")
    round_.weakSpots = [w.strip() for w in round_.weakSpots if w.strip()][:6]
    return round_


def grill_map(
    client: Any, units: list[AchievementUnit], target: TargetProfile, model: str
) -> list[GrillMapRow]:
    """The exhaustive CV prep: every unit in the genome pre-interrogated with
    the nastiest fair questions this target's interviewers would ask."""
    tr = track_config(target.track)
    prompt = fill_prompt(
        load_prompt("grill-map.md"),
        ROLE_CONTEXT=tr["grill_context"],
        TARGET_JSON=json.dumps(target.model_dump()),
        UNITS_JSON=json.dumps([u.model_dump() for u in units]),
    )
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=GrillMap,
        max_tokens=12000,
    )
    return sanitize_grill_map([r.model_dump() for r in parsed.rows], units)


def project_grill(
    client: Any,
    project_text: str,
    units: list[AchievementUnit],
    target: TargetProfile,
    exchanges: list[dict],
    model: str,
) -> GrillRound:
    """One round of the project deep-dive. Same loop shape as the Devil's
    Advocate — judge prior answers, then probe again — but aimed at ONE
    project/CV claim and cycling through the interrogation angles a real
    deep-dive round uses. The loop has no terminal verdict: the exposed
    weak spots ARE the deliverable."""
    prompt = fill_prompt(
        load_prompt("project-grill.md"),
        ROLE_CONTEXT=track_config(target.track)["grill_context"],
        TARGET_JSON=json.dumps(target.model_dump()),
        PROJECT=project_text,
        UNITS_JSON=json.dumps([u.model_dump() for u in units]),
        EXCHANGES_JSON=json.dumps(exchanges),
    )
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=GrillRound,
        adaptive=True,  # judging answers fairly needs care
        max_tokens=8000,
    )
    return sanitize_grill_round(parsed, len(exchanges))


# --- v3: the learning plan (suggested learnings from JD + heatmap) ------------


def sanitize_learning_plan(
    plan: LearningPlan,
    target: TargetProfile,
    cells: list[CoverageCell],
    track_key: str,
) -> LearningPlan:
    """The truthfulness pass for suggested learnings:

    - resources survive ONLY if their URL is in the curated allowlist, and a
      surviving link's title/kind/time are replaced with the curated entry's
      own fields — the model picks links, it never describes them;
    - an item whose links all died falls back to the track's deterministic
      picks for that competency (possibly empty — honest beats padded);
    - off-track competencies are dropped, first mention wins;
    - every amber/red heatmap competency the model skipped is back-filled —
      a silent miss would read as "nothing to learn" on the weakest spot;
    - items come back ordered red -> amber -> green, heaviest JD weight first.
    """
    allowed_comps = set(track_config(track_key)["taxonomy"])
    weight = {rc.competency: rc.weight for rc in target.requiredCompetencies}
    strength = {c.competency: c.strength for c in cells}
    items: dict[str, LearningItem] = {}
    for item in plan.items:
        if item.competency not in allowed_comps or item.competency in items:
            continue
        fixed: list[LearningResource] = []
        for res in item.resources:
            canon = ALLOWED_RESOURCES.get((res.url or "").strip())
            if canon is None:
                continue
            fixed.append(
                LearningResource(
                    title=canon["title"], url=canon["url"],
                    kind=canon["kind"], time=canon["time"],
                )
            )
        item.resources = fixed[:3] or [
            LearningResource(**r) for r in fallback_resources(track_key, item.competency)
        ]
        item.topics = [t.strip() for t in item.topics if t.strip()][:6]
        items[item.competency] = item
    for cell in cells:
        if cell.strength == "green" or cell.competency in items:
            continue
        items[cell.competency] = LearningItem(
            competency=cell.competency,
            priority=weight.get(cell.competency, 3),
            why=cell.gapAction or GENERIC_GAP.format(competency=cell.competency),
            topics=[],
            resources=[
                LearningResource(**r)
                for r in fallback_resources(track_key, cell.competency)
            ],
            practice=cell.gapAction
            or "Run a small real project that exercises this, and capture one concrete metric.",
        )
    rank = {"red": 0, "amber": 1, "green": 2}
    plan.items = sorted(
        items.values(),
        key=lambda i: (
            rank.get(strength.get(i.competency, "amber"), 1),
            -weight.get(i.competency, 0),
            -i.priority,
        ),
    )[:12]
    if not plan.items:
        raise ValueError("the learning plan came back empty")
    return plan


def learning_plan(
    client: Any,
    units: list[AchievementUnit],
    target: TargetProfile,
    cells: list[CoverageCell],
    model: str,
) -> LearningPlan:
    tr = track_config(target.track)
    units_summary = [{"id": u.id, "title": u.title, "skills": u.skills} for u in units]
    prompt = fill_prompt(
        load_prompt("learning-plan.md"),
        ROLE_CONTEXT=tr["target_context"],
        TARGET_JSON=json.dumps(target.model_dump()),
        CELLS_JSON=json.dumps([c.model_dump() for c in cells]),
        UNITS_SUMMARY_JSON=json.dumps(units_summary),
        RESOURCES_JSON=json.dumps(resource_pool(tr["key"])),
    )
    parsed = _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=LearningPlan,
        adaptive=True,  # sequencing a study plan deserves a beat
        max_tokens=12000,
    )
    return sanitize_learning_plan(parsed, target, cells, tr["key"])


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
    return _parse(
        client,
        model=model,
        prompt=prompt,
        output_format=DeliveryCheck,
        max_tokens=4000,
    )

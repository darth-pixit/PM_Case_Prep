"""Prep Engine — CV-point presentation advice + the candidate's own intro
story (the /prep and /prep-ds experiment).

The concept: you already did the work — the engine helps you *present* it.

  * Tune-CV: every CV point, reviewed through the target role family's
    hiring lens — how the line reads to a screener today, what weakens it,
    and the strongest HONEST version of the same point. Where a number or
    fact is missing, the rewrite carries an explicit "[ADD: …]" placeholder
    for the candidate to fill — never an invented value.
  * Intro story: guided answers about why they do what they do, plus the CV,
    become a StoryKit — the spoken "tell me about yourself", the "why this
    craft", the "why this role", and the beats to adapt live.

A job description is OPTIONAL by design: pasting one decodes a TargetProfile
and the advice tunes to that opening; without one, a role-family hint
(archetype + seniority, or nothing at all) frames the lens instead — for
people prepping for a role, not a specific opening at a specific company.

Two deliberate choices, carried over from the first Prep Engine:

* Field names are camelCase, mirroring a TypeScript client's types exactly,
  so the JSON the browser sees transfers byte-for-byte to a future port.
* Truthfulness is enforced twice. The prompts (loaded from /prompts/*.md so
  they can be edited without a rebuild) forbid invention — but prompts are
  requests, not guarantees, so a deterministic audit pass runs on everything
  the model returns: a reviewed point whose "original" cannot be found in
  the CV is dropped, numbers in a rewrite or story that appear in none of
  the candidate's own inputs are flagged, and off-list issue tags die. The
  model can be wrong; the guards make sure it can't be wrong *silently*.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Optional, get_args

from pydantic import BaseModel, Field, ValidationError

from .prep_tracks import all_competencies
from .prep_tracks import track as track_config

# --- The competency taxonomies (closed lists; per-track tuples live in
# --- prep_tracks.py, and this Literal is the union both tracks share so one
# --- schema serves every structured-output call) ------------------------------

Competency = Literal[
    # pm
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

# The Literal above and the track tuples must never drift apart — fail the
# import, not a 3am review.
assert set(get_args(Competency)) == set(all_competencies())


# --- The optional target (JD path) --------------------------------------------


class RequiredCompetency(BaseModel):
    competency: Competency
    weight: Literal[1, 2, 3, 4, 5]
    evidence: str  # the JD phrase that justifies it


class TargetProfile(BaseModel):
    """The specific opening being prepped for — exists ONLY when a JD was
    pasted. `track` names the role family (which page owns this target); it
    is set by the SERVER from the requesting page, never by the model."""

    company: str
    roleTitle: str
    seniority: Literal[
        "APM", "PM", "Senior", "Group", "Director",  # pm ladder
        "Junior", "Mid", "Staff", "Principal", "Lead",  # ds ladder (Senior shared)
    ]
    archetype: str  # Growth / Platform / 0-1 / Experimentation / ...
    requiredCompetencies: list[RequiredCompetency]
    unwrittenPain: str  # inferred: the real problem behind the hire
    companyValues: list[str]
    track: Literal["pm", "ds"] = "pm"


# --- The CV review ------------------------------------------------------------

# Closed list of presentation flaws — chips in the UI, countable in analytics,
# and un-inventable by the model (off-list tags are dropped, not guessed).
IssueTag = Literal[
    "vague-verb",           # "worked on", "helped with", "was involved in"
    "activity-not-outcome", # describes effort/ceremony, not what changed
    "feature-not-problem",  # ships named, user problem absent
    "missing-scope",        # no team size / users / duration / surface area
    "missing-user",         # who was this for?
    "no-evidence",          # a claim with nothing measurable behind it
    "buried-lede",          # the impressive part hides at the end
    "jargon",               # internal codenames / acronyms a stranger can't read
    "laundry-list",         # three unrelated things crammed into one point
    "no-ownership",         # can't tell what the CANDIDATE did vs the team
    "reads-junior",         # framing undersells the actual scope
    "too-long",             # a paragraph doing a bullet's job
]


class PointReview(BaseModel):
    """One CV point, reviewed. `original` is provenance — it must be quoted
    from the CV, and the sanitizer drops any point it can't find there."""

    original: str
    read: str  # what a screener honestly takes away from the line today
    issues: list[IssueTag]
    rewrite: str  # same facts, presented stronger; [ADD: …] for missing ones
    why: str  # why the rewrite lands, through the role lens
    flags: list[str] = Field(default_factory=list)  # audit findings


class ReviewOverall(BaseModel):
    """The whole-CV read: what the document currently says the candidate is,
    and how to re-present it. Entries in leadWith/cut reference points by
    their original text; the sanitizer keeps only ones that match a
    surviving point."""

    readsAs: str = ""  # the candidate this CV currently describes
    leadWith: list[str] = Field(default_factory=list)
    cut: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)  # go gather, don't spin
    ordering: str = ""


class CVReview(BaseModel):
    points: list[PointReview]
    overall: ReviewOverall


# --- The intro story ----------------------------------------------------------


class StoryKit(BaseModel):
    """The candidate's own story, shaped: the spoken tell-me-about-yourself,
    the why-this-craft, the why-this-role — grounded in their CV and their
    own answers, never a template biography."""

    throughLine: str  # one sentence: the thread that makes the moves make sense
    tellMe: str  # "tell me about yourself", 60-90 seconds spoken
    whyRole: str  # why product / why data science — theirs, not generic
    whyThis: str  # why this opening (JD path) or this kind of role (no JD)
    beats: list[str]  # cue-card beats to adapt live, not a script to memorize
    tips: list[str]  # delivery tips tied to their content
    flags: list[str] = Field(default_factory=list)  # audit findings


# --- Prompts: loaded from /prompts/*.md, never inlined ------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def fill_prompt(template: str, **subs: str) -> str:
    """Replace <PLACEHOLDER> tokens. Every placeholder must be consumed —
    a prompt sent with a dangling <CV> is a silent quality bug."""
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


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


MAX_POINTS = 40
ISSUE_TAGS: tuple[str, ...] = get_args(IssueTag)


def sanitize_target(
    target: TargetProfile, track_key: Optional[str] = None
) -> TargetProfile:
    """Dedupe required competencies (keep the highest weight per competency).
    With `track_key` given (extraction time), the track is stamped on the
    target server-side and competencies from the OTHER track's taxonomy are
    dropped — the schema Literal is the union, so the model could otherwise
    hand a PM page a DS row."""
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


def sanitize_review(raw: dict, cv_text: str) -> CVReview:
    """Validate + audit a CV review.

    - a point whose `original` cannot be found in the CV (whitespace/case
      aside) is DROPPED — reviewing a bullet the candidate never wrote is
      noise at best and fabrication at worst;
    - duplicate points (same normalized original) collapse to the first;
    - issue tags outside the closed list are dropped (not guessed);
    - numbers in a rewrite that appear nowhere in the CV are flagged — the
      "never invent" rule enforced in code, not just in the prompt;
    - overall.leadWith / overall.cut keep only entries that match a
      surviving point, rewritten to that point's canonical original.
    """
    cv_norm = _norm(cv_text)
    cv_nums = _numbers(cv_text)
    points: list[PointReview] = []
    seen: set[str] = set()
    for item in (raw.get("points") or [])[: MAX_POINTS * 2]:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        item["issues"] = [t for t in (item.get("issues") or []) if t in ISSUE_TAGS]
        try:
            point = PointReview.model_validate(item)
        except ValidationError:
            continue  # one malformed point shouldn't sink the review
        key = _norm(point.original)
        if not key or key in seen or key not in cv_norm:
            continue
        seen.add(key)
        flags = [f.strip() for f in point.flags if f.strip()]
        for num in sorted(_numbers(point.rewrite) - cv_nums):
            flags.append(
                f'The number "{num}" is not in your CV — replace it with the '
                "real value or an [ADD: …] placeholder."
            )
        point.flags = flags
        points.append(point)
        if len(points) >= MAX_POINTS:
            break
    if not points:
        raise ValueError("no reviewable CV points survived the audit")

    try:
        overall = ReviewOverall.model_validate(raw.get("overall") or {})
    except ValidationError:
        overall = ReviewOverall()

    def canonical(entry: str) -> Optional[str]:
        e = _norm(entry)
        if not e:
            return None
        for p in points:
            po = _norm(p.original)
            if e == po or e in po or po in e:
                return p.original
        return None

    def match_points(entries: list[str]) -> list[str]:
        out: list[str] = []
        for entry in entries:
            c = canonical(entry)
            if c is not None and c not in out:
                out.append(c)
        return out[:5]

    overall.leadWith = match_points(overall.leadWith)
    overall.cut = match_points(overall.cut)
    overall.missing = [m.strip() for m in overall.missing if m.strip()][:6]
    return CVReview(points=points, overall=overall)


def audit_kit(kit: StoryKit, source_text: str) -> StoryKit:
    """Flag numbers in the story kit that appear in none of the candidate's
    own inputs (CV + their answers + the decoded target).

    Conservative on purpose: a false positive costs one confirming glance;
    a false negative is a fabricated fact spoken in a real interview.
    """
    known = _numbers(source_text)
    flags = [f.strip() for f in kit.flags if f.strip()]
    already = set(flags)
    audited = [kit.throughLine, kit.tellMe, kit.whyRole, kit.whyThis, *kit.beats]
    alien: set[str] = set()
    for text in audited:
        alien |= _numbers(text) - known
    for num in sorted(alien):
        claim = (
            f'The number "{num}" appears in none of your inputs — '
            "confirm it's real or cut it."
        )
        if claim not in already:
            already.add(claim)
            flags.append(claim)
    kit.flags = flags
    kit.beats = [b.strip() for b in kit.beats if b.strip()][:6]
    kit.tips = [t.strip() for t in kit.tips if t.strip()][:5]
    if not kit.tellMe.strip() or not kit.throughLine.strip():
        raise ValueError("the story kit came back without its core pieces")
    return kit


def role_context(
    track_key: str,
    target: Optional[TargetProfile] = None,
    role_hint: Optional[dict] = None,
) -> str:
    """The target context the prompts inject. With a decoded JD it's the
    TargetProfile; without one it's an honest role-family line — the JD is
    optional by design (prepping for a role, not only a specific opening)."""
    if target is not None:
        return (
            "Decoded target role (from a pasted job description):\n"
            + json.dumps(target.model_dump())
        )
    tr = track_config(track_key)
    hint = role_hint or {}
    qualifier = " ".join(
        s
        for s in (
            str(hint.get("seniority") or "").strip(),
            str(hint.get("archetype") or "").strip(),
        )
        if s
    )
    described = f"{qualifier} {tr['role_noun']}" if qualifier else tr["role_noun"]
    return (
        f"No specific opening: the candidate is preparing for {described} "
        "roles in general. Do not invent a company or a job description — "
        "keep the advice at the role-family level."
    )


# --- Model calls (one careful structured-output call each) --------------------


def extract_target(
    client: Any, jd_text: str, model: str, track_key: str = "pm"
) -> TargetProfile:
    tr = track_config(track_key)
    prompt = fill_prompt(
        load_prompt("extract-target.md"),
        ROLE_CONTEXT=tr["target_context"],
        TAXONOMY=", ".join(tr["taxonomy"]),
        SENIORITY_LADDER=" | ".join(tr["seniority"]),
        ARCHETYPES=" / ".join(tr["archetypes"]),
        JOB_DESCRIPTION=jd_text,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_format=TargetProfile,
    )
    return sanitize_target(resp.parsed_output, track_key=tr["key"])


def tune_cv(
    client: Any,
    cv_text: str,
    model: str,
    track_key: str = "pm",
    target: Optional[TargetProfile] = None,
    role_hint: Optional[dict] = None,
) -> CVReview:
    tr = track_config(track_key)
    prompt = fill_prompt(
        load_prompt("tune-cv.md"),
        ROLE_LENS=tr["review_lens"],
        ROLE_NOUN=tr["role_noun"],
        TARGET_CONTEXT=role_context(track_key, target, role_hint),
        ISSUE_TAGS=", ".join(ISSUE_TAGS),
        CV=cv_text,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},  # judging how a line reads deserves care
        messages=[{"role": "user", "content": prompt}],
        output_format=CVReview,
    )
    return sanitize_review(resp.parsed_output.model_dump(), cv_text)


def intro_story(
    client: Any,
    answers: list[dict],
    cv_text: str,
    model: str,
    track_key: str = "pm",
    target: Optional[TargetProfile] = None,
    role_hint: Optional[dict] = None,
    prior: Optional[StoryKit] = None,
    note: str = "",
) -> StoryKit:
    """Craft (or, with `prior` + `note`, revise) the intro StoryKit from the
    candidate's own answers and CV. Refinement is the same call shape: the
    prior kit and the user's note ride along, and the model revises instead
    of starting over."""
    tr = track_config(track_key)
    qa = "\n\n".join(
        f"Q: {a['question']}\nA: {a['answer']}" for a in answers
    ) or "(none)"
    if prior is not None:
        revision = (
            "PRIOR VERSION (revise it — keep what works, do not start over):\n"
            + json.dumps(prior.model_dump())
            + "\nWHAT THE CANDIDATE WANTS CHANGED: "
            + (note or "tighten and sharpen it")
        )
    else:
        revision = "(first draft — there is no prior version)"
    prompt = fill_prompt(
        load_prompt("intro-story.md"),
        ROLE_LENS=tr["story_lens"],
        ROLE_NOUN=tr["role_noun"],
        TARGET_CONTEXT=role_context(track_key, target, role_hint),
        CV=cv_text.strip() or "(no CV pasted)",
        ANSWERS=qa,
        REVISION=revision,
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=4000,
        thinking={"type": "adaptive"},  # storycraft benefits from a beat of thought
        messages=[{"role": "user", "content": prompt}],
        output_format=StoryKit,
    )
    sources = "\n".join(
        [
            cv_text or "",
            qa,
            json.dumps(target.model_dump()) if target is not None else "",
            note or "",
        ]
    )
    return audit_kit(resp.parsed_output, sources)

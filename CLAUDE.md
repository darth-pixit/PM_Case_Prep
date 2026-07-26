# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An AI-first PM interview-prep product: **six separate experiments running on one
FastAPI deploy, one domain, one SQLite-backed login, one PostHog project** — each
experiment has its own page, UX, and analytics namespace so results never bleed
into each other.

| Route | Experiment | Code home |
|---|---|---|
| `/` | **Tutor** — live voice case interview (mic → Deepgram → interviewer agent → graded scorecard) | `web/app.py` WS `/ws`, `interviewer.py`, `grader.py` |
| `/arena` | **Case Arena** — 5 PM tracks × 5 cases, pick-your-case, same interview room | `case_loader.py`, `cases/arena/*.json`, `static/arena.js` |
| `/recruiter` | **Recruiter Copilot** — chat grounded in a hand-researched KB | `recruiter_kb.py`, `static/recruiter.js` |
| `/referrals` | **Referral Paths** — client-side referral mapping + multiplayer "pods" | `static/referrals.js` (solo, 100% browser), `web/pods.py` |
| `/prep` | **Prep Engine** — CV-point presentation review (honest rewrites, `[ADD: …]` placeholders) + the candidate's own intro story; JD optional | `prep_engine.py`, `prep_bank.py`, `static/prep.js`, `prompts/*.md` |
| `/prep-ds` | **Prep Engine · Data Science** — same two tools through the DS hiring lens (own taxonomy, pickers, prompt framing) | `prep_tracks.py`, `static/prep-ds.html` (shares `prep.js`) |

`main` is the **Render deploy branch** — merging to `main` ships to production
(`render.yaml` blueprint: `uvicorn pmcaseprep.web.app:app`, persistent disk at
`/data`, health check `/health`). Work on a feature branch, PR into `main`.

## Commands

```bash
pip install -r requirements.txt      # includes pytest
python3 -m pytest tests/ -q          # full suite — OFFLINE by design, no API keys needed
python3 -m pytest tests/test_prep.py -q            # one file
python3 -m pytest tests/test_prep.py::test_extractor_golden_shape -q   # one test
python run_web.py                    # local web app on http://127.0.0.1:8000
python -m pmcaseprep.cli             # text CLI, one case end-to-end (/hint /done /quit)
PMCP_DEV_DOCS=1 python run_web.py    # re-enables /docs + email-code dev mode (code shown in UI)
```

No linter/formatter is configured. Tests must stay offline: stub model calls
(assign over the imported function in `web/app.py`, or feed fixture dicts to the
sanitizers) and use `tmp_path` sqlite files. Live model calls get exercised on
Render, not in CI.

Secrets come from `.env` (see `.env.example`): `ANTHROPIC_API_KEY`,
`DEEPGRAM_API_KEY` (voice), `PMCP_GOOGLE_CLIENT_ID` / `PMCP_RESEND_KEY` (login
doors), `PMCP_POSTHOG_KEY` (analytics). `PMCP_MODEL` overrides every model;
per-role overrides exist (`PMCP_INTERVIEWER_MODEL`, `PMCP_GRADER_MODEL`,
`PMCP_RECRUITER_MODEL`, `PMCP_PREP_MODEL`). Defaults: fast conversational roles
on `claude-sonnet-5`, the end-of-case grader on `claude-opus-4-8`.

## Architecture — the shared spine

`pmcaseprep/web/app.py` is the single FastAPI app holding **every** HTTP/WS
endpoint, all rate limiters, and the abuse guards. Everything user-facing is a
static page in `web/static/` (no build step, no framework): each page loads
`hub.css` + `shared.js`, calls `PMCP.experiment("<name>")` (registers the
PostHog `experiment` super property AND prefixes event names `<name>_*`), and
mounts login with `PMCP.mountAuth(el, {reason, onLogin})`.

**Auth** (`web/auth.py`): one passwordless login for all experiments — Google
ID-token verification + emailed 6-digit codes (Resend). The verified email is
linked to the visitor's `pmcp_uid` cookie in SkillGraph's `users` table;
`_email_for_request()` in app.py is the session check every gated endpoint uses.

**Money guards**: every endpoint that triggers a paid model call is gated by
login + a per-IP `SlidingLimit`; cheap sqlite CRUD (pods, prep bank) gets its
own generous limiter. Client IP behind Render's proxy = **last** hop of
`X-Forwarded-For` (first hop is client-forgeable). Errors return
`{"ok": false, "error": "<generic msg>"}` with the real exception printed
server-side only. `/docs`,`/redoc`,`/openapi.json` are disabled unless
`PMCP_DEV_DOCS=1`.

**Persistence**: two SQLite files that live side by side (Render disk `/data`):
`PMCP_DB` → `skill_graph.db` (scores, sessions, users) and `prep_bank.db`
(derived from `PMCP_DB`'s directory; override `PMCP_PREP_DB`). Both stores are
opened per request and closed in `finally`.

### The interview loop (tutor + arena)

One WebSocket (`/ws`) per session ties together mic audio → `DeepgramLive`
(nova-3 default; Flux semantic turn-detection via `PMCP_STT=flux`) → coalesced
turns → `Interviewer` (a manual Messages-API tool-use loop with a phase machine
that logs **silent observations** — never shown mid-session) → at `/done`, one
careful `grader.py` call using **structured outputs**
(`client.messages.parse(output_format=ScoreCard)`) → `SkillGraph` for
longitudinal analytics. Delivery metrics (`delivery.py` — pure, offline-testable
pace/pause/filler math) accumulate silently and surface only in the scorecard.
The interviewer's "say nothing" sentinel is `(listening)` and is suppressed
server-side. `/arena/room` injects `window.PMCP_EXPERIMENT/PMCP_CASE_ID` at the
`<!-- PMCP_INJECT` marker in `index.html` — don't remove that marker.

Two prompt systems, deliberately separate (`prompts.py`): the interviewer is
encouraging and never grades; the grader is harsh, rubric-anchored
(`rubric.py`: six dimensions scored 1-4, verdict *gated* on any dimension ≤ 2),
and only sees the transcript at the end.

### The Prep Engine

The present-yourself experiment: you already did the work — the engine helps
you *present* it. Two tools per page: the CV-point review (how each line
reads through the role family's hiring lens + the strongest honest rewrite)
and the intro StoryKit (tell-me-about-yourself / why-this-craft / why-this-
role, from guided answers + the CV, with a revise loop). The contract:

- **The JD is optional by design.** A pasted JD decodes into a
  `TargetProfile` that tunes the advice; without one, `role_context()`
  builds an honest role-family line from the archetype+seniority hint (or
  nothing). No endpoint may require a target — people prep for roles, not
  only for specific openings.
- **Data model is camelCase on purpose** (`prep_engine.py`: `CVReview`,
  `PointReview`, `StoryKit`, `TargetProfile`, …) — it mirrors a TS client's
  types byte-for-byte. Do not snake_case it. (The tutor's models in
  `models.py` are snake_case; the two coexist intentionally.)
- **All 3 LLM prompts live in `/prompts/*.md`** (`tune-cv`, `intro-story`,
  `extract-target`), loaded from disk via `load_prompt()`/`fill_prompt()`
  (raises on a missing `<PLACEHOLDER>`). Never inline a prompt in code.
  Tests pin the load-bearing guardrail phrases inside the prompt files —
  edit wording freely, keep those phrases.
- **Truthfulness is enforced in code, not just prompts**: deterministic
  audits run on every model response — `sanitize_review` DROPS any reviewed
  point whose `original` isn't actually in the pasted CV, flags rewrite
  numbers that appear nowhere in the CV, and kills off-list issue tags;
  `audit_kit` flags story numbers found in none of the candidate's inputs.
  Missing facts become explicit `[ADD: …]` placeholders, never guesses.
  Extending the engine means extending the guards; the model must never be
  able to fabricate *silently*.
- **Model calls are stateless; the latest docs persist server-side** in
  `prep_bank.py` (one `prep_docs` table keyed (owner=login email, kind ∈
  review|story, track)) — saving overwrites, the page restores on login,
  and `bank/clear` deletes one doc. Files from the story-bank era carry
  legacy tables (`prep_units`, `prep_targets`, `prep_stories`,
  `prep_debriefs`) — leave them untouched.
- **Tracks** (`prep_tracks.py`): `/prep` = PM, `/prep-ds` = Data Science —
  per-track hiring lenses (`review_lens`, `story_lens`), taxonomy,
  seniority ladder, and archetype picker; `Competency` is the Literal UNION
  of both taxonomies and an import-time assert keeps it in sync with the
  track tuples. Targets are stamped with their track server-side
  (`sanitize_target`, off-track competency rows drop), and `prep.js` is one
  track-aware script driven by `window.PREP_TRACK`.

### Privacy contracts (enforced by code, mirrored in page copy)

- **Pods** (`web/pods.py`): members share only SHA-256 hashes of connection
  profile URLs + company names; endpoints reject anything not hash-shaped.
  Names never reach the server. Solo referral mapping is entirely client-side.
- **Prep export**: the .md prep sheet is assembled in the browser from state
  already on the page — the export button sends nothing extra to the server.

If you change one of these flows, keep the code-level enforcement and the page
copy in sync.

## Conventions worth knowing

- Structured model output = `client.messages.parse(..., output_format=PydanticModel)`
  (needs `anthropic>=0.49`); wrap bare arrays in a container model. Careful/judgy
  calls add `thinking={"type": "adaptive"}`. Conversational calls use
  `messages.create` with a cached (`cache_control: ephemeral`) system prompt.
- Client-supplied data that round-trips through the browser (prep units, chat
  history) is re-validated server-side as untrusted input; chat histories are
  normalized (first turn user, consecutive same-role turns merged) before
  hitting the Messages API.
- Static pages escape ALL interpolated content with `PMCP.esc`.
- Case JSON banks: `cases/` (tutor) and `cases/arena/` (arena +
  `_categories.json`) are separate on purpose; `hidden_facts` /
  `ideal_answer_notes` are interviewer/grader-only and must never reach the
  candidate UI.
- The README's experiment table and per-experiment paragraphs are the public
  story — update them when an experiment's surface changes.

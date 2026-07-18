# PM Case Prep

An AI-first **product-manager case-interview tutor** — the counterpart to the AI
consulting-case tools (casewithai / casestudyprep / mbb.ai), built for the open-ended
world of PM cases where there is no single right answer.

This repo is a **runnable prototype** of the core loop. Two ways to run it: a text
CLI, and a **live web app** with an always-on mic, live transcript, delivery
meters (pace/pauses/fillers), and simultaneous typing. Spoken feedback (TTS) is
the remaining voice piece (see [Roadmap](#roadmap)).

```
clarify  ->  solve (candidate drives)  ->  graduated hints on demand
         ->  rubric-graded scorecard  ->  longitudinal skill graph
```

## Four experiments, one deploy

The site runs **four separate experiments on one Render service, one domain,
one database, and one login system** — but each experiment has its own page,
its own user experience, and its own analytics namespace, so results never
bleed into each other:

| Route | Experiment | Login | Analytics namespace |
|---|---|---|---|
| `/` | **Tutor** — the original single-case interview (unchanged) | optional, at scorecard | `experiment=tutor` |
| `/arena` | **Case Arena** — 5 PM tracks × 5 cases each, pick-your-case | **required at start** | `experiment=arena`, `arena_*` events |
| `/recruiter` | **Recruiter Copilot** — hiring for AI/DS without being an expert | required for chat; field guide open | `experiment=recruiter`, `recruiter_*` events |
| `/referrals` | **Referral Paths** — closeness-ranked referral map from your own data exports, plus multiplayer job-hunt pods | solo: none (all client-side) · pods: required | `experiment=referrals`, `referrals_*` events |

Every PostHog event carries an `experiment` super property, so per-experiment
dashboards are one filter away while a single (free-tier) PostHog project and
one publishable key serve everything.

**One login, two passwordless doors** (`pmcaseprep/web/auth.py`): "Continue
with Google" (a Google-signed ID token verified server-side — set
`PMCP_GOOGLE_CLIENT_ID`) and "email me a 6-digit code" via Resend (set
`PMCP_RESEND_KEY`; free tier is 3,000 emails/month). No password ever exists,
so there is nothing to forget and no reset flow to build. Both doors land on
the same `users` table the tutor already used, and anonymous work done before
signing in merges into the account.

**The arena's case bank** lives in `cases/arena/` (the tutor's bank at
`cases/` is untouched): 25 original cases across the five highest-hiring PM
tracks of 2025-26 — Core/Generalist, AI PM, Growth, Platform/Technical, and
Data PM (taxonomy grounded in Lenny's job-market reports + prep-platform
coverage). Each track grades through its own rubric tilt
(`rubric.ARCHETYPE_WEIGHTS`).

**The recruiter copilot** (`pmcaseprep/recruiter_kb.py`) is grounded in a
researched map of what AI / GenAI / Data-Science interviews actually test
today — question archetypes, plain-english concept explainers, evaluation
techniques for non-experts, and 40 URL-verified learning resources — and the
chat folds that knowledge base into every reply.

**Referral Paths** parses official data exports **entirely in the browser**
(LinkedIn killed its connections API in 2015; the DMA portability API is
EU-only — the legally-mandated exports are the one ToS-clean path that works
everywhere). It ingests the full LinkedIn archive ZIP (connections, messages,
education, positions, invitations, recommendations, endorsements), phone
contacts (.vcf / Google CSV), and Instagram/Facebook export ZIPs (friends,
close-friends list, DM partners — including Meta's mojibake fix), then
cross-references everything into a **relationship-strength score**: DM
frequency/recency/bidirectionality, referral-talk detection, who recommended
whom, who invited whom, and who also shows up in your phone/IG/FB. Buckets
rank accordingly ("they owe you one", "referral talk already happened",
"inner circle", recruiters/senior people flagged as ⚡ doors). Names never
touch the server in solo mode.

**Pods** (`pmcaseprep/web/pods.py`, `/api/pods/*`) are the opt-in multiplayer
layer: friends job-hunting together pool (1) who can refer directly where
(everyone's work history becomes a referral exchange) and (2) who knows
people at which companies. A member shares only SHA-256 hashes of connection
profile URLs + company names — the endpoints **reject anything that isn't
hash-shaped**, so the server can count ("Rahul knows 3 people at Stripe")
but can never name; only Rahul's own browser holds the hash→person mapping.
Equal hashes across members double as mutual-connection counts. Login-gated,
rate-limited, and leaving a pod deletes your rows.

## Why not fine-tune?

You don't need to fine-tune a model, and the frontier Claude models aren't
fine-tunable anyway. The behavior we want — reasoning about open-ended answers
against a rubric — is a **context + prompting** problem, not a weights problem.
So this scaffold uses: a strong system prompt (persona + rubric), per-case context
loaded at runtime (RAG-ready), a tool loop for the agent behavior, and structured
outputs for machine-readable grading. Adding a case = dropping a JSON file in
`cases/`, not retraining.

## Architecture

Two deliberately separated agents:

| Agent | Role | File |
|---|---|---|
| **Interviewer** | In-character, Socratic, never grades mid-flow. Answers clarifications from a hidden facts sheet, gives graduated hints only on request, and **silently logs observations** against the rubric while you work. | `pmcaseprep/interviewer.py` |
| **Grader** | Out-of-character. Runs once at the end against calibration anchors and returns a structured `ScoreCard`. | `pmcaseprep/grader.py` |

Supporting pieces:

- `pmcaseprep/rubric.py` — the **two-layer rubric**: 6 universal dimensions scored
  1-4 (gated: any dimension ≤2 caps the verdict at *no hire*) + per-`type` category
  checklists + red-flag caps + per-archetype weightings.
- `pmcaseprep/models.py` — typed `Case` / `Observation` / `ScoreCard` (the scorecard
  doubles as the structured-output schema).
- `pmcaseprep/skill_graph.py` — cross-case analytics over a **SQLite scores table**
  (never over raw transcripts): per-dimension averages, trends, and weak-spot
  detection. The moat feature.
- `pmcaseprep/vision.py` — whiteboard/photo input seam (Claude reads sketches,
  funnels, 2×2s natively — no OCR).
- `cases/*.json` — a case = candidate prompt + interviewer-only hidden facts +
  grader-only ideal-answer notes + calibration anchors.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY

python -m pmcaseprep.cli    # runs the default AI-PM case
```

During a case: type your thinking out loud; `/hint` for a graduated nudge,
`/done` to finish and get your scorecard, `/quit` to abort.

Offline wiring check (no API key needed):

```bash
python -m pytest -q        # or: python tests/test_smoke.py
```

## Live web app (voice + delivery + typing) — recommended

The web app is the real surface: an **always-on mic**, a **live transcript**,
**live delivery meters** (pace, pauses, filler rate), and a **text box that works
at the same time** — type or talk, both feed one conversation. It reuses the same
interviewer, grader, and skill graph as the CLI, and the final scorecard **fuses
delivery (how you speak) with substance (the rubric)**.

```bash
pip install -r requirements.txt      # now includes fastapi / uvicorn / websockets
# .env needs ANTHROPIC_API_KEY (required) and DEEPGRAM_API_KEY (for voice)
python run_web.py
# then open http://127.0.0.1:8000 in Chrome
```

- **Use Chrome** and allow the mic when prompted. `localhost` is a secure context,
  so the mic works over plain http locally — no HTTPS needed for dev.
- Voice uses **Deepgram streaming (Turn-based / endpointing)**: it transcribes live
  *and* detects when you finish a thought, so Maya knows when to respond.
- No Deepgram key? The app still runs — typing works, voice is just disabled.
- Click **Done & grade** for the fused scorecard + your delivery summary.

```
browser mic ──audio──▶ FastAPI ──▶ Deepgram (live transcript + word timings)
     │                    │                      │
   text box ──────────────┤               delivery metrics
                          ▼
            Interviewer ─▶ Grader (rubric + delivery) ─▶ Skill graph
```

Files: `pmcaseprep/web/app.py` (backend + one WebSocket per session),
`web/deepgram_live.py` (streaming client), `web/static/*` (the browser UI),
`delivery.py` (pace/pause/filler metrics — pure and unit-tested).

## Going online

The app is deploy-ready — same code, hosted. The UI is tuned for phones and
desktops, and every visitor gets their own progress (cookie identity + the
scorecard's "save your progress" email login).

### Deploy on Render (recommended, ~5 minutes)

1. [render.com](https://render.com) → sign up with your GitHub account.
2. **New → Blueprint**, pick this repository (and the working branch). Render
   reads `render.yaml` and configures everything.
3. It will prompt for the secrets: `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`,
   `PMCP_POSTHOG_KEY`. Paste the same values as your local `.env`.
4. Deploy. You get `https://pm-case-prep.onrender.com` — HTTPS included, so the
   mic works and the frontend auto-switches to `wss://`.

Free-tier honesty: the instance sleeps after ~15 idle minutes (first visit
wakes it in ~30s), and the SQLite file is wiped on each deploy/restart — so
saved progress survives a session but not a redeploy. For real persistence:
paid instance + a Render Disk (set `PMCP_DB=/data/skill_graph.db`), or the
roadmap Postgres move.

### Deploy anywhere else

`Dockerfile` included — Railway, Fly.io, Cloud Run, or any VPS:
`docker build -t pmcaseprep . && docker run -p 8000:8000 --env-file .env pmcaseprep`.
Keys are environment variables — **server-side only; the browser never sees them.**

### Accounts & saved progress (MVP)

Each browser gets an anonymous identity cookie, so scores never mix between
visitors. The scorecard ends with **"Save your progress"**: entering an email
links it to that identity; entering the same email on another device restores
it. This is deliberately password-less for now — fine for a prep tool MVP,
but add real auth (Google OAuth / magic links via Clerk or Auth0) before
promoting it widely, since anyone who knows an email could claim it.
(`/api/login` is rate-limited per IP so claiming can't be scripted at scale.)

### Abuse guards (public deploys)

Every interview session spends real money (Claude per turn + a Deepgram
stream), so the WebSocket is gated: connections must come from the app's own
origin with a visitor cookie, and are capped — hourly opens per IP
(`PMCP_WS_HOURLY_PER_IP`), concurrent sessions per IP / per visitor / global
(`PMCP_MAX_SESSIONS_PER_IP` / `PMCP_MAX_SESSIONS_PER_UID` /
`PMCP_MAX_SESSIONS`), model calls per session (`PMCP_MAX_TURNS`), session
length (`PMCP_MAX_SESSION_MIN`), idle time (`PMCP_IDLE_MIN`), and typed-turn
size (`PMCP_MAX_TEXT_CHARS`). Hitting a session limit grades what exists, so
a real candidate still gets their scorecard. API docs (`/docs`, `/redoc`,
`/openapi.json`) and verbose `/health` are disabled in production; set
`PMCP_DEV_DOCS=1` locally to get them back. Belt-and-braces: also set spend
caps + alerts in the Anthropic console and Deepgram dashboard — those hold
even if the app-level guards fail.

### Turn detection: Flux (default) vs nova-3

Knowing *when the candidate is done talking* is the hardest part of a
thinking-out-loud interview, and pure silence timers can't tell a pause from a
finished thought. So the app defaults to Deepgram **Flux**, a conversational
model with **native semantic end-of-turn detection** — it reads the speech
itself (words + prosody + pauses) to decide the turn is over, and we commit
immediately when it says so (no timer). Tune its patience with `PMCP_FLUX_EOT`
(0–1, higher = waits longer; default 0.8).

If Flux is unavailable on your account the channel **auto-falls back to nova-3**,
which uses a single *debounced* pause timer (`PMCP_SILENCE_S`, default 2.5s):
the turn commits only after that much true silence, and any speech re-arms it,
so an answer with internal pauses stays one turn and never fires mid-thought.
Force nova-3 with `PMCP_STT=nova`. `/health` reports which is active.

### Visitor analytics (PostHog)

Set `PMCP_POSTHOG_KEY` (and optionally `PMCP_POSTHOG_HOST`, default
`https://us.i.posthog.com`) in the server's environment and every visitor is
tracked automatically: pageviews, **every click** (autocapture), plus the
interview funnel — `case_started → hint_requested → interview_finished →
scorecard_viewed → resource_opened → new_case_clicked`. PostHog distinguishes
visitors with a persistent per-device ID (more reliable than IP, which changes
on the same person and collides across an office/NAT); each event also carries
the visitor's IP and GeoIP location. The key is a *publishable* write-only
token, so serving it to the browser is safe. **No transcript content is ever
sent** — only event names and coarse properties like the band.

## Voice & photo input (CLI)

The text CLI (`python -m pmcaseprep.cli`) is the quick, no-browser option. It
announces its input modes at the start of every case — you can answer three ways:

| Mode | How | Key needed |
|---|---|---|
| **Type** | Just type and press Enter | — |
| **Voice** | `/voice <audio-file>` — record on your phone (Voice Memos → `.m4a`) or QuickTime, then point to the file. Or `/record [seconds]` to capture from your mic. | **Deepgram** (speech-to-text) |
| **Photo** | `/photo <image> [note]` — a whiteboard/sketch photo (funnel, 2×2, metric tree). Tip: drag the file into the terminal to paste its path. | Uses your **Anthropic** key (Claude vision) — nothing extra |

Feedback is text for now (no spoken output yet — that's the TTS roadmap item).

### API keys — what and where

- **Anthropic** (required): reasoning, grading, and photo/whiteboard vision.
  [console.anthropic.com](https://console.anthropic.com) → Settings → API keys.
  Put it in `.env` as `ANTHROPIC_API_KEY`.
- **Deepgram** (only for voice): speech-to-text. Free tier includes ~$200 credit.
  [console.deepgram.com](https://console.deepgram.com) → API keys. Put it in
  `.env` as `DEEPGRAM_API_KEY`. Leave it blank and typing/photo still work fully.

`/record` additionally needs `pip install sounddevice numpy` (macOS: `brew install
portaudio`). `/voice <file>` needs no audio libraries.

> Swapping speech-to-text: `transcribe.py` uses Deepgram over plain HTTPS. Moving
> to OpenAI Whisper or a local `faster-whisper` model is a small, isolated change.

## The sample case

`cases/ai_pm_thumbs_down_spike.json` — an **AI-PM execution / root-cause** case
("thumbs-down rate jumped 4% → 9%"). It exercises metric definition, MECE
internal/external diagnosis, segmenting to a model A/B arm, and AI-specific
signals (eval regression, quality-vs-latency tradeoff, guardrail metrics).

**Legally clean by construction**: the product ("Quill"), the interviewer, the
numbers, and every fact are invented for this repo. No text is reproduced from
any book or question bank (Lewis Lin, Exponent, PMExercises, …) — the case only
follows the *format* of an execution interview, and formats aren't ownable.
Keep new cases to the same standard: original scenario, original wording.

## Learning resources & trajectory

- `pmcaseprep/resources.py` holds a short, curated map of gold-standard free
  articles/videos per rubric dimension (issue trees, JTBD, RICE, Pyramid
  Principle, North Star metrics, …) and per case concept tag (`resource_tags`
  in the case JSON — e.g. metric debugging, A/B testing, LLM evals). The
  scorecard shows "level up" links on dimensions where the candidate scored
  ≤3, and a "go deeper" section for the case's concepts. Clicks are tracked.
- The skill graph projects a **trajectory**: a least-squares trend over your
  per-case scores answers "at this pace, roughly how many more cases to the
  HIRE (2.75) / STRONG HIRE (3.5) bar?" It refuses to extrapolate flat trends
  or fewer than two cases, and is labeled an estimate (the real band also
  gates on your weakest dimension).

## Grading model

- **Layer 1** — Structure, User Empathy, Prioritization, Creativity, Communication,
  Data/Business, each 1-4, weighted per archetype. Band is recomputed locally from
  the numeric scores (deterministic and auditable), not taken from model prose.
- **Layer 2** — a category checklist (e.g. CIRCLES for design, MECE-RCA for
  execution) marked met/not-met with quote-anchored notes.
- **Red-flag caps** — e.g. "jumped to features before defining the user" caps
  Structure & Empathy; "no success metric named" caps Data/Business.
- **Anchors** — the grader scores by comparison to strong/at-bar/weak exemplars,
  which keeps LLM grading stable.

## Roadmap

Marked `# TODO` in the code where relevant:

- **Voice** (your spec): live streaming input is wired in the **web app**
  (Deepgram Turn-based) with live **delivery analytics**. Still to do: spoken
  output (**ElevenLabs/Cartesia TTS**) so the coach reads the scorecard aloud.
- **Whiteboard**: photo input works in the CLI (`/photo`); the interactive
  annotate-and-send-back canvas is the next web-client feature.
- **Adaptive case selection**: the skill graph flags weak dimensions; wire it to
  pick the next case that drills them.
- **Company personas**: "Meta Product Sense", "Google Generalist", "Amazon Bar
  Raiser", "OpenAI AI-PM" — different question style, follow-up aggressiveness, and
  rubric weighting (a field on `Case` + persona prompt fragments).
- **Case bank + RAG**: `case_loader.py` is the retrieval seam; seed from free,
  IP-safe sources and author original variants (see notes below).

## A note on case sources & IP

Learn the taxonomy and rubric from the canon (Decode and Conquer / CIRCLES,
Cracking the PM Interview, Exponent/PMExercises/IGotAnOffer, Lenny's product-sense
rubrics), but **author original questions/answers** — the books are copyrighted and
the big banks' ToS prohibit scraping. Do not train on or ship scraped Q&A.

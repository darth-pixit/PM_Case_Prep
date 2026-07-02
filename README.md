# PM Case Prep

An AI-first **product-manager case-interview tutor** — the counterpart to the AI
consulting-case tools (casewithai / casestudyprep / mbb.ai), built for the open-ended
world of PM cases where there is no single right answer.

This repo is a **runnable prototype scaffold** of the core loop. It implements the
reasoning and grading end-to-end today; voice and whiteboard input are marked as
seams (see [Roadmap](#roadmap)).

```
clarify  ->  solve (candidate drives)  ->  graduated hints on demand
         ->  rubric-graded scorecard  ->  longitudinal skill graph
```

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

## Voice & photo input

The CLI announces the available input modes at the start of every case. You can
answer three ways:

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
signals (eval regression, quality-vs-latency tradeoff, guardrail metrics). All
wording is original — no copyrighted question/answer text is reproduced.

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

- **Voice** (your spec): input is wired — **Deepgram STT** via `/voice` and
  `/record`. Still to do: spoken output (**ElevenLabs/Cartesia TTS**) and a
  streaming, "feels-live" loop (Pipecat/Vapi/LiveKit). Text output for now.
- **Whiteboard**: photo input works today (`/photo`, `vision.py`); the interactive
  annotate-and-send-back canvas is the v2 web-client feature.
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

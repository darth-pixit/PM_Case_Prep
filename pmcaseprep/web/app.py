"""FastAPI backend.

One WebSocket per session ties together:
  * always-on mic audio (from the browser) -> Deepgram streaming -> word timings,
  * a text box (typed input) that feeds the SAME conversation,
  * the Interviewer, Grader (rubric + delivery fusion), and SkillGraph.

Design choices that matter for the interview feel and stability:
  * Voice runs on its own supervised channel (`Voice`) with KeepAlive + auto
    reconnect. A Deepgram hiccup never tears down the session — text keeps working.
  * Spoken fragments are COALESCED: we only hand a turn to the interviewer after a
    real pause (SILENCE_S), so thinking-out-loud doesn't trigger a reply per
    sentence. The interviewer is also prompted to stay silent by default and emits
    "(listening)" when it should say nothing — we suppress that.
  * Delivery metrics accumulate silently and surface only in the final scorecard.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections import deque
from pathlib import Path
from typing import Awaitable, Callable

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..case_loader import default_case_path, load_case
from ..delivery import FILLERS_CORE, DeliveryTracker, Word
from ..grader import grade, weighted_result
from ..interviewer import Interviewer
from ..resources import resources_for
from ..skill_graph import SkillGraph
from .deepgram_live import DeepgramLive

MODEL = os.environ.get("PMCP_MODEL", "claude-opus-4-8")
# Turn-taking is ADAPTIVE. An utterance that addresses the interviewer (a
# question, "let's move on", "that's my answer") commits after QUESTION_S — you
# shouldn't wait long for an answer you asked for. Anything else is treated as
# thinking out loud and gets the patient SILENCE_S window.
SILENCE_S = float(os.environ.get("PMCP_SILENCE_S", "6.0"))
QUESTION_S = float(os.environ.get("PMCP_QUESTION_S", "1.5"))
# Utterances below this Deepgram confidence are treated as noise (keyboard
# clatter, coughs, background voices) and never become turns.
MIN_CONFIDENCE = float(os.environ.get("PMCP_MIN_CONFIDENCE", "0.55"))
# Product analytics (PostHog). The project key is publishable by design — it can
# only ingest events, never read them — so serving it to the browser is safe.
POSTHOG_KEY = os.environ.get("PMCP_POSTHOG_KEY", "")
POSTHOG_HOST = os.environ.get("PMCP_POSTHOG_HOST", "https://us.i.posthog.com")
STATIC_DIR = Path(__file__).resolve().parent / "static"
HINT_PROMPT = (
    "[The candidate asks for a hint. Give ONE graduated nudge for where they are "
    "right now — a question or a pointer to the missing dimension. Do not solve it.]"
)

app = FastAPI(title="PM Case Prep")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _is_silence(reply: str) -> bool:
    """True if the interviewer chose to stay quiet. If the "(listening)" sentinel
    appears ANYWHERE, treat the whole turn as silence — any text around it is the
    model narrating to itself, never something for the candidate to read."""
    if "(listening)" in reply.lower():
        return True
    return "".join(c for c in reply.lower() if c.isalpha()) in ("", "listening")


# Signals that the candidate is talking TO the interviewer and expects a fast
# response, rather than thinking out loud. Deepgram's smart_format adds "?" for
# question phrasing, which catches most of these on its own.
_ADDRESS_RE = re.compile(
    r"(\?\s*$)"
    r"|^(what|why|how|when|where|who|which|can|could|do|does|did|is|are|was|were|should|would|will)\b"
    r"|\b(tell me|give me|do we know|do we have|what about|your thoughts|does that make sense"
    r"|is that (right|fair|correct)|am i right|let'?s move on|i'?m done|i am done"
    r"|that'?s my (answer|framework|plan|approach)|moving on|next question"
    r"|any (data|numbers?|info|information)|clarify)\b",
    re.IGNORECASE,
)


def _addresses_interviewer(text: str) -> bool:
    return bool(_ADDRESS_RE.search(text.strip()))


# Pure disfluencies — an utterance made only of these is a murmur, not a turn.
_MURMURS = FILLERS_CORE | {"mm", "mhm", "hm", "huh"}


def _is_noise(text: str, confidence: float) -> bool:
    """Keyboard taps, coughs, murmurs, and cross-talk show up as short
    low-confidence fragments or bare fillers. They must never become turns —
    each junk turn is a model call that blocks the queue and can trip a
    spurious reply."""
    words = [w.lower() for w in re.findall(r"[a-zA-Z']+", text)]
    real = [w for w in words if len(w) >= 2 and w not in _MURMURS]
    return confidence < MIN_CONFIDENCE or not real


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config")
async def config() -> JSONResponse:
    """Public, browser-safe config. No secrets — the PostHog key is publishable."""
    return JSONResponse({"posthog_key": POSTHOG_KEY, "posthog_host": POSTHOG_HOST})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "voice": bool(os.environ.get("DEEPGRAM_API_KEY")),
            "anthropic_key": bool(
                os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            ),
            "model": MODEL,
        }
    )


class Voice:
    """Supervised Deepgram streaming channel: KeepAlive + auto-reconnect, and it
    never raises into the session (voice can drop without killing text)."""

    def __init__(
        self,
        api_key: str,
        handle_event: Callable[[dict], Awaitable[None]],
        notify: Callable[[str], Awaitable[None]],
    ):
        self._key = api_key
        self._handle = handle_event
        self._notify = notify
        self._dg: DeepgramLive | None = None
        self._task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._supervise())

    async def _supervise(self) -> None:
        backoff = 1.0
        while not self._closed:
            keeper = None
            try:
                self._dg = DeepgramLive(self._key)
                await self._dg.__aenter__()
                backoff = 1.0
                keeper = asyncio.create_task(self._keepalive())
                async for evt in self._dg.events():
                    await self._handle(evt)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 - any drop -> reconnect below
                pass
            finally:
                if keeper is not None:
                    keeper.cancel()
                if self._dg is not None:
                    try:
                        await self._dg.__aexit__()
                    except Exception:  # noqa: BLE001
                        pass
                self._dg = None
            if self._closed:
                break
            try:
                await self._notify("voice reconnecting…")
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(min(backoff, 5.0))
            backoff *= 2

    async def _keepalive(self) -> None:
        # Deepgram closes an idle stream ~10s after audio stops; this heartbeat is
        # what keeps "always listening" true through long thinking pauses. One
        # failed send must NOT kill the loop — skip the tick and keep beating.
        while not self._closed:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return
            dg = self._dg
            if dg is not None:
                try:
                    await dg.keepalive()
                except Exception:  # noqa: BLE001 - supervisor reconnects; keep ticking
                    pass

    async def send(self, data: bytes) -> None:
        dg = self._dg
        if self._closed or dg is None:
            return
        try:
            await dg.send_audio(data)
        except Exception:  # noqa: BLE001 - supervisor will reconnect
            pass

    async def stop(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
        if self._dg is not None:
            try:
                await self._dg.__aexit__()
            except Exception:  # noqa: BLE001
                pass


@app.websocket("/ws")
async def session_ws(ws: WebSocket) -> None:
    await ws.accept()

    case = load_case(default_case_path())
    client = anthropic.Anthropic()
    interviewer = Interviewer(client, case, MODEL)
    tracker = DeliveryTracker()
    graph = SkillGraph()
    session_id = uuid.uuid4().hex[:8]
    voice_on = bool(os.environ.get("DEEPGRAM_API_KEY"))

    await ws.send_json(
        {
            "type": "case",
            "title": case.title,
            "prompt": case.prompt,
            "interviewer_name": case.interviewer_name,
            "archetype": case.archetype,
            "case_type": case.type,
            "voice": voice_on,
        }
    )
    await ws.send_json({"type": "state", "state": "listening"})

    turn_queue: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    current_words: list[Word] = []  # words for the in-progress utterance
    current_conf: list[float] = []  # Deepgram confidence per finalized chunk
    speech_buffer: list[str] = []  # finalized utterances awaiting the silence flush
    flush_task: asyncio.Task | None = None

    async def send_json(payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            pass

    # --- turn coalescing (pause before a spoken turn commits) ----------------

    async def flush_speech() -> None:
        nonlocal speech_buffer, flush_task
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
        flush_task = None
        text = " ".join(speech_buffer).strip()
        speech_buffer = []
        if text:
            await turn_queue.put({"source": "voice", "text": text})

    async def _delayed_flush(delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await flush_speech()

    def schedule_flush(delay: float) -> None:
        nonlocal flush_task
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
        flush_task = asyncio.create_task(_delayed_flush(delay))

    async def finalize_utterance() -> None:
        nonlocal current_words, current_conf
        words, confs = current_words, current_conf
        current_words, current_conf = [], []
        if not words:
            return
        text = " ".join(w.text for w in words).strip()
        if not text or _is_noise(text, max(confs) if confs else 0.0):
            return  # background noise — no metrics, no turn, no reply
        tracker.add_turn(words)  # metrics only — not shown live
        speech_buffer.append(text)
        # A question gets answered fast; thinking-out-loud gets patience.
        schedule_flush(QUESTION_S if _addresses_interviewer(text) else SILENCE_S)

    async def handle_dg(evt: dict) -> None:
        nonlocal current_words, current_conf
        etype = evt.get("type")
        if etype == "Results":
            alt = evt.get("channel", {}).get("alternatives", [{}])[0]
            transcript = alt.get("transcript", "")
            conf = float(alt.get("confidence") or 0.0)
            if len(transcript.strip()) >= 3 and conf >= 0.45:
                await send_json({"type": "listening"})  # pulse indicator, no words
            if evt.get("is_final") and transcript:
                current_conf.append(conf)
                for w in alt.get("words", []):
                    current_words.append(
                        Word(w.get("word", ""), float(w.get("start", 0)), float(w.get("end", 0)))
                    )
            if evt.get("speech_final"):
                await finalize_utterance()
        elif etype == "UtteranceEnd":
            await finalize_utterance()

    # --- grading + interviewer worker ----------------------------------------

    async def do_grade() -> None:
        await send_json({"type": "state", "state": "grading"})
        delivery_summary = tracker.summary_text()
        try:
            card = await asyncio.to_thread(
                grade,
                client,
                case,
                interviewer.transcript(),
                interviewer.observations_text(),
                MODEL,
                delivery_summary,
            )
        except Exception as exc:  # noqa: BLE001
            await send_json({"type": "error", "text": f"Grading failed: {exc}"})
            return
        weighted, _min_dim, band = weighted_result(case, card)
        graph.record(session_id, case.id, case.archetype, card, band)
        await send_json(
            {
                "type": "scorecard",
                "band": band,
                "weighted": round(weighted, 2),
                "card": card.model_dump(),
                "delivery": tracker.snapshot(),
                "delivery_summary": delivery_summary,
                "skill_graph": graph.render_summary(),
                "trajectory": graph.projection(),
                "resources": resources_for(card, case),
            }
        )

    async def interviewer_worker() -> None:
        # Turns can arrive faster than the model answers. Consecutive queued
        # turns are MERGED into one model call — so asking twice while a reply
        # is in flight yields one good answer, not a serial backlog of calls.
        pending: deque = deque()
        while not stop.is_set():
            if not pending:
                pending.append(await turn_queue.get())
            while True:
                try:
                    pending.append(turn_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            item = pending.popleft()
            if item.get("cmd") == "__stop__":
                break
            if item.get("cmd") == "done":
                await do_grade()
                stop.set()
                break
            if item.get("cmd") == "hint":
                text = HINT_PROMPT
            else:
                texts = [item.get("text", "")]
                while pending and "cmd" not in pending[0]:
                    texts.append(pending.popleft().get("text", ""))
                text = "\n".join(t for t in texts if t.strip())
            if not text.strip():
                continue
            await send_json({"type": "state", "state": "responding"})
            try:
                reply = await asyncio.to_thread(interviewer.respond_content, text)
            except Exception as exc:  # noqa: BLE001
                await send_json({"type": "error", "text": f"Model error: {exc}"})
                await send_json({"type": "state", "state": "listening"})
                continue
            if reply and not _is_silence(reply):
                await send_json({"type": "reply", "text": reply})
            if interviewer.concluded:
                await do_grade()
                stop.set()
                break
            await send_json({"type": "state", "state": "listening"})

    worker = asyncio.create_task(interviewer_worker())
    voice = None
    try:
        if voice_on:
            voice = Voice(
                os.environ["DEEPGRAM_API_KEY"],
                handle_dg,
                lambda msg: send_json({"type": "status", "text": msg}),
            )
            await voice.start()

        while not stop.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if voice is not None:
                    await voice.send(msg["bytes"])  # never raises
            elif msg.get("text") is not None:
                data = json.loads(msg["text"])
                mtype = data.get("type")
                if mtype == "text" and data.get("text", "").strip():
                    await flush_speech()  # commit any pending spoken thoughts first
                    await turn_queue.put({"source": "text", "text": data["text"].strip()})
                elif mtype == "hint":
                    await turn_queue.put({"cmd": "hint"})
                elif mtype == "done":
                    await flush_speech()
                    await turn_queue.put({"cmd": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        await send_json({"type": "error", "text": str(exc)})
    finally:
        stop.set()
        if flush_task is not None:
            flush_task.cancel()
        if voice is not None:
            await voice.stop()
        await turn_queue.put({"cmd": "__stop__"})
        await asyncio.gather(worker, return_exceptions=True)
        graph.close()

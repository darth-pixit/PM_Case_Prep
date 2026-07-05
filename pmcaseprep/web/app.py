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
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..case_loader import default_case_path, load_case
from ..delivery import FILLERS_CORE, DeliveryTracker, Word
from ..grader import grade, weighted_result
from ..interviewer import Interviewer
from ..resources import resources_for
from ..skill_graph import SkillGraph
from .deepgram_live import DG_URL, FLUX_ACTIVE, FLUX_URL, NOVA_URL, DeepgramLive

# Two model tiers: the interviewer runs on a FAST model (conversational turns,
# snappy replies); the grader runs on the deepest model (one careful call at
# the end). PMCP_MODEL overrides both; the specific vars override per-role.
_MODEL_OVERRIDE = os.environ.get("PMCP_MODEL")
INTERVIEWER_MODEL = os.environ.get(
    "PMCP_INTERVIEWER_MODEL", _MODEL_OVERRIDE or "claude-sonnet-5"
)
GRADER_MODEL = os.environ.get("PMCP_GRADER_MODEL", _MODEL_OVERRIDE or "claude-opus-4-8")
# Turn-taking. With Flux (the default STT), turn boundaries come from Deepgram's
# SEMANTIC end-of-turn model and we commit immediately — no timer. With nova-3
# we fall back to a single DEBOUNCED pause timer: the turn commits only after
# PAUSE_S of true silence since your last words, and any speech RE-ARMS it, so a
# whole answer (with internal thinking pauses) is one turn and it never fires
# mid-thought. One clock, not the old two-timer split that interrupted people.
PAUSE_S = float(os.environ.get("PMCP_SILENCE_S", "2.5"))
# Utterances below this Deepgram confidence are treated as noise (keyboard
# clatter, coughs, background voices) and never become turns.
MIN_CONFIDENCE = float(os.environ.get("PMCP_MIN_CONFIDENCE", "0.6"))
# Product analytics (PostHog). The project key is publishable by design — it can
# only ingest events, never read them — so serving it to the browser is safe.
POSTHOG_KEY = os.environ.get("PMCP_POSTHOG_KEY", "")
POSTHOG_HOST = os.environ.get("PMCP_POSTHOG_HOST", "https://us.i.posthog.com")
DB_PATH = os.environ.get("PMCP_DB", "skill_graph.db")
UID_COOKIE = "pmcp_uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 730  # two years
STATIC_DIR = Path(__file__).resolve().parent / "static"
HINT_PROMPT = (
    "[The candidate asks for a hint. Give ONE graduated nudge for where they are "
    "right now — a question or a pointer to the missing dimension. Do not solve it.]"
)

app = FastAPI(title="PM Case Prep")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


_SENTINEL_RE = re.compile(r"\(\s*listening\.?\s*\)", re.IGNORECASE)


def _visible_reply(reply: str) -> str:
    """What the candidate should actually SEE. Empty string = stay silent.

    The model is told a silent turn is exactly "(listening)". But if it wraps a
    real answer around the sentinel, swallowing everything would drop an answer
    the model believes it delivered — the candidate then hears "as I said…"
    about words that never reached the screen. So: strip the sentinel, and if
    substantial text remains, show that text; only near-empty remainders are
    true silence."""
    if not reply:
        return ""
    if _SENTINEL_RE.search(reply):
        remainder = " ".join(_SENTINEL_RE.sub(" ", reply).split())
        return remainder if len(remainder) >= 60 else ""
    if "".join(c for c in reply.lower() if c.isalpha()) in ("", "listening"):
        return ""
    return reply.strip()


def _flux_words(evt: dict) -> list[Word]:
    """Build Word objects from a Flux EndOfTurn event.

    Flux returns word text + confidence but (unlike nova-3) NO per-word
    start/end times — only a turn-level audio window. So when timing is absent,
    spread the words evenly across [audio_window_start, audio_window_end]. That
    keeps words-per-minute honest (total duration is real); per-word pause
    detection is necessarily coarser on Flux, which we accept for its far
    better turn-taking."""
    raw = [w for w in (evt.get("words") or []) if isinstance(w, dict)]
    tokens = [w.get("word", "") for w in raw]
    if raw and all(("start" in w and "end" in w) for w in raw):
        return [Word(w["word"], float(w["start"] or 0), float(w["end"] or 0)) for w in raw]
    if not tokens:
        tokens = (evt.get("transcript") or "").split()
    start = float(evt.get("audio_window_start") or 0)
    end = float(evt.get("audio_window_end") or 0)
    n = len(tokens)
    if n == 0:
        return []
    step = (end - start) / n if end > start else 0.0
    return [Word(t, start + i * step, start + (i + 1) * step) for i, t in enumerate(tokens)]


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
async def index(request: Request) -> FileResponse:
    """Serve the app and give every visitor a stable anonymous identity, so
    their skill graph is theirs alone even before they log in."""
    resp = FileResponse(STATIC_DIR / "index.html")
    if not request.cookies.get(UID_COOKIE):
        resp.set_cookie(
            UID_COOKIE, uuid.uuid4().hex, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return resp


@app.get("/config")
async def config(request: Request) -> JSONResponse:
    """Public, browser-safe config. No secrets — the PostHog key is publishable."""
    email = None
    uid = request.cookies.get(UID_COOKIE)
    if uid:
        g = SkillGraph(DB_PATH, uid)
        email = g.email_for_uid(uid)
        g.close()
    return JSONResponse(
        {"posthog_key": POSTHOG_KEY, "posthog_host": POSTHOG_HOST, "email": email}
    )


@app.post("/api/login")
async def login(request: Request) -> JSONResponse:
    """Email-linked progress (MVP — no password yet, see README).

    New email  -> links this browser's uid to it ("save my progress").
    Known email -> switches this browser to the saved uid ("restore my progress").
    """
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad request"}, status_code=400)
    email = str(data.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1] or len(email) > 254:
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)

    anon_uid = request.cookies.get(UID_COOKIE) or uuid.uuid4().hex
    uid = anon_uid
    g = SkillGraph(DB_PATH, uid)
    try:
        existing = g.uid_for_email(email)
        restored = bool(existing and existing != uid)
        if restored:
            uid = existing
        else:
            g.link_email(email, uid)
        g2 = SkillGraph(DB_PATH, uid)
        if restored:
            # Cases finished on this device BEFORE logging in (e.g. the one
            # just graded) must follow the person into their saved account.
            g2.merge_from(anon_uid)
        sessions = g2.sessions_count()
        g2.close()
    finally:
        g.close()

    resp = JSONResponse(
        {"ok": True, "email": email, "restored": restored, "sessions": sessions}
    )
    resp.set_cookie(UID_COOKIE, uid, max_age=COOKIE_MAX_AGE, samesite="lax")
    return resp


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "voice": bool(os.environ.get("DEEPGRAM_API_KEY")),
            "stt": "flux" if FLUX_ACTIVE else "nova-3",
            "anthropic_key": bool(
                os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            ),
            "interviewer_model": INTERVIEWER_MODEL,
            "grader_model": GRADER_MODEL,
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
        url = DG_URL
        fast_fails = 0  # consecutive near-instant drops (bad model/params)
        while not self._closed:
            keeper = None
            started = asyncio.get_event_loop().time()
            try:
                self._dg = DeepgramLive(self._key, url)
                await self._dg.__aenter__()
                backoff = 1.0
                keeper = asyncio.create_task(self._keepalive())
                async for evt in self._dg.events():
                    fast_fails = 0
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
            # Experimental Flux model failing on connect? Fall back to nova-3
            # rather than looping — voice must keep working no matter what.
            if url == FLUX_URL and asyncio.get_event_loop().time() - started < 5.0:
                fast_fails += 1
                if fast_fails >= 2:
                    url = NOVA_URL
                    try:
                        await self._notify("voice: flux unavailable — using standard model")
                    except Exception:  # noqa: BLE001
                        pass
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
    interviewer = Interviewer(client, case, INTERVIEWER_MODEL)
    tracker = DeliveryTracker()
    # Scope every score to this visitor's cookie identity — on a public host,
    # skill graphs must never mix across users.
    uid = ws.cookies.get(UID_COOKIE) or uuid.uuid4().hex
    graph = SkillGraph(DB_PATH, uid)
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
    current_words: list[Word] = []  # words accumulated for the in-progress turn
    current_conf: list[float] = []  # Deepgram confidence per finalized chunk
    commit_task: asyncio.Task | None = None

    async def send_json(payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            pass

    # --- turn commit ---------------------------------------------------------
    # ONE clock. commit_pending() hands the accumulated turn to the interviewer.
    # nova-3 arms a debounce (re-armed by any speech) so it fires only after a
    # real pause; Flux calls it directly from its semantic end-of-turn.

    async def commit_pending() -> None:
        nonlocal current_words, current_conf, commit_task
        if commit_task is not None and not commit_task.done():
            commit_task.cancel()
        commit_task = None
        words, confs = current_words, current_conf
        current_words, current_conf = [], []
        if not words:
            return
        text = " ".join(w.text for w in words).strip()
        if not text or _is_noise(text, max(confs) if confs else 0.0):
            return  # background noise — no metrics, no turn, no reply
        tracker.add_turn(words)  # metrics only — not shown live
        await turn_queue.put({"source": "voice", "text": text})

    async def _debounced_commit() -> None:
        try:
            await asyncio.sleep(PAUSE_S)
        except asyncio.CancelledError:
            return
        await commit_pending()

    def arm_commit() -> None:
        """(Re)start the pause countdown. Called on every bit of speech, so the
        turn commits only once you've genuinely stopped for PAUSE_S."""
        nonlocal commit_task
        if commit_task is not None and not commit_task.done():
            commit_task.cancel()
        commit_task = asyncio.create_task(_debounced_commit())

    async def handle_dg(evt: dict) -> None:
        nonlocal current_words, current_conf
        etype = evt.get("type")
        if etype == "Results":
            # nova-3 path: accumulate words; the pause timer decides the turn.
            alt = evt.get("channel", {}).get("alternatives", [{}])[0]
            transcript = alt.get("transcript", "")
            conf = float(alt.get("confidence") or 0.0)
            if len(transcript.strip()) >= 3 and conf >= 0.45:
                await send_json({"type": "listening"})  # pulse indicator
                arm_commit()  # still talking → push the commit later
            if evt.get("is_final") and transcript:
                current_conf.append(conf)
                for w in alt.get("words", []):
                    current_words.append(
                        Word(w.get("word", ""), float(w.get("start", 0)), float(w.get("end", 0)))
                    )
                arm_commit()
        elif etype == "TurnInfo":
            # Flux path: the model tells us when the turn is semantically over —
            # commit immediately, no timer. This is the whole point of Flux.
            event = evt.get("event", "")
            transcript = (evt.get("transcript") or "").strip()
            if transcript and event in ("Update", "StartOfTurn", "EagerEndOfTurn"):
                await send_json({"type": "listening"})
            if event == "EndOfTurn" and transcript:
                current_words.extend(_flux_words(evt))
                current_conf.append(float(evt.get("end_of_turn_confidence") or 1.0))
                await commit_pending()

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
                GRADER_MODEL,
                delivery_summary,
            )
        except Exception as exc:  # noqa: BLE001
            await send_json({"type": "error", "text": f"Grading failed: {exc}"})
            return
        weighted, _min_dim, band = weighted_result(case, card)
        graph.record(
            session_id,
            case.id,
            case.archetype,
            card,
            band,
            weighted=round(weighted, 2),
            transcript=interviewer.transcript(),
            delivery={
                "snapshot": tracker.snapshot(),
                "summary": delivery_summary,
            },
        )
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
            shown = _visible_reply(reply)
            # The model's memory must match the candidate's screen, always.
            interviewer.align_shown(shown or "(listening)")
            if shown:
                await send_json({"type": "reply", "text": shown})
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
                # Drop empty frames: a zero-byte binary message is Deepgram's
                # end-of-stream signal and would close the voice connection.
                if voice is not None and msg["bytes"]:
                    await voice.send(msg["bytes"])  # never raises
            elif msg.get("text") is not None:
                data = json.loads(msg["text"])
                mtype = data.get("type")
                if mtype == "text" and data.get("text", "").strip():
                    await commit_pending()  # commit any pending spoken thoughts first
                    await turn_queue.put({"source": "text", "text": data["text"].strip()})
                elif mtype == "hint":
                    await turn_queue.put({"cmd": "hint"})
                elif mtype == "done":
                    await commit_pending()
                    await turn_queue.put({"cmd": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        await send_json({"type": "error", "text": str(exc)})
    finally:
        stop.set()
        if commit_task is not None:
            commit_task.cancel()
        if voice is not None:
            await voice.stop()
        await turn_queue.put({"cmd": "__stop__"})
        await asyncio.gather(worker, return_exceptions=True)
        graph.close()

"""FastAPI backend.

One WebSocket per session ties together:
  * always-on mic audio (from the browser) -> Deepgram streaming -> live
    transcript + delivery metrics,
  * a text box (typed input) that feeds the SAME conversation,
  * the existing Interviewer (Socratic, logs observations), Grader (rubric +
    delivery fusion), and SkillGraph.

Voice-final turns and typed turns are both pushed onto ONE queue and processed
in order by a single worker — so speaking and typing coexist cleanly.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

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
from ..delivery import DeliveryTracker, Word
from ..grader import grade, weighted_result
from ..interviewer import Interviewer
from ..skill_graph import SkillGraph
from .deepgram_live import DeepgramLive

MODEL = os.environ.get("PMCP_MODEL", "claude-opus-4-8")
STATIC_DIR = Path(__file__).resolve().parent / "static"
HINT_PROMPT = (
    "[The candidate asks for a hint. Give ONE graduated nudge for where they are "
    "right now — a question or a pointer to the missing dimension. Do not solve it.]"
)

app = FastAPI(title="PM Case Prep")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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

    turn_queue: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    current_words: list[Word] = []  # words for the in-progress spoken utterance

    async def do_grade() -> None:
        await ws.send_json({"type": "status", "text": "grading"})
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
            await ws.send_json({"type": "error", "text": f"Grading failed: {exc}"})
            return
        weighted, _min_dim, band = weighted_result(case, card)
        graph.record(session_id, case.id, case.archetype, card, band)
        await ws.send_json(
            {
                "type": "scorecard",
                "band": band,
                "weighted": round(weighted, 2),
                "card": card.model_dump(),
                "delivery": tracker.snapshot(),
                "delivery_summary": delivery_summary,
                "skill_graph": graph.render_summary(),
            }
        )

    async def interviewer_worker() -> None:
        while not stop.is_set():
            item = await turn_queue.get()
            if item.get("cmd") == "__stop__":
                break
            if item.get("cmd") == "done":
                await do_grade()
                stop.set()
                break
            text = HINT_PROMPT if item.get("cmd") == "hint" else item.get("text", "")
            if not text.strip():
                continue
            try:
                reply = await asyncio.to_thread(interviewer.respond_content, text)
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"type": "error", "text": f"Model error: {exc}"})
                continue
            if reply:
                await ws.send_json({"type": "reply", "text": reply})
            if interviewer.concluded:
                await do_grade()
                stop.set()
                break

    async def flush_utterance() -> None:
        nonlocal current_words
        if not current_words:
            return
        snap = tracker.add_turn(current_words)
        await ws.send_json({"type": "delivery", **snap})
        text = " ".join(w.text for w in current_words).strip()
        current_words = []
        if text:
            await ws.send_json({"type": "final_turn", "text": text})
            await turn_queue.put({"source": "voice", "text": text})

    async def deepgram_consumer(dg: DeepgramLive) -> None:
        nonlocal current_words
        async for evt in dg.events():
            etype = evt.get("type")
            if etype == "Results":
                alt = evt.get("channel", {}).get("alternatives", [{}])[0]
                transcript = alt.get("transcript", "")
                is_final = evt.get("is_final", False)
                speech_final = evt.get("speech_final", False)
                if transcript:
                    await ws.send_json(
                        {"type": "transcript", "text": transcript, "is_final": is_final}
                    )
                if is_final:
                    for w in alt.get("words", []):
                        current_words.append(
                            Word(w.get("word", ""), float(w.get("start", 0)), float(w.get("end", 0)))
                        )
                if speech_final:
                    await flush_utterance()
            elif etype == "UtteranceEnd":
                await flush_utterance()

    worker = asyncio.create_task(interviewer_worker())
    dg_obj = None
    consumer = None
    try:
        if voice_on:
            try:
                dg_obj = DeepgramLive(os.environ["DEEPGRAM_API_KEY"])
                await dg_obj.__aenter__()
                consumer = asyncio.create_task(deepgram_consumer(dg_obj))
            except Exception as exc:  # noqa: BLE001
                dg_obj = None
                await ws.send_json(
                    {"type": "error", "text": f"Voice unavailable (text still works): {exc}"}
                )

        while not stop.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if dg_obj is not None:
                    await dg_obj.send_audio(msg["bytes"])
            elif msg.get("text") is not None:
                data = json.loads(msg["text"])
                mtype = data.get("type")
                if mtype == "text" and data.get("text", "").strip():
                    await turn_queue.put({"source": "text", "text": data["text"].strip()})
                elif mtype == "hint":
                    await turn_queue.put({"cmd": "hint"})
                elif mtype == "done":
                    await turn_queue.put({"cmd": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await ws.send_json({"type": "error", "text": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        stop.set()
        await turn_queue.put({"cmd": "__stop__"})
        if consumer is not None:
            consumer.cancel()
        if dg_obj is not None:
            await dg_obj.__aexit__()
        await asyncio.gather(worker, return_exceptions=True)
        graph.close()

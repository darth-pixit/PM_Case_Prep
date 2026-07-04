"""Async Deepgram streaming client (Turn-based / endpointing).

Hand-rolled over the `websockets` library so there's no Deepgram SDK version
churn. We ask for interim results (live partial transcript), word timestamps
(delivery metrics), and endpointing + utterance-end events (turn detection —
so Maya knows when you've finished a thought).

Two speech models are supported:
  * nova-3 (default) — classic streaming STT; turn boundaries come from
    silence heuristics (endpointing + utterance_end_ms) that WE tune.
  * flux (opt-in: PMCP_STT=flux) — Deepgram's conversational model with
    NATIVE turn detection: it models whether a pause is "mid-thought" vs
    "done talking" from the speech itself, not just silence length. Better
    for interview-style thinking-out-loud. Experimental here: if the Flux
    connection fails, the supervisor falls back to nova-3 automatically.

Audio expected: 16 kHz, mono, linear16 (PCM). The browser sends exactly that.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator

import websockets

NOVA_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3"
    "&smart_format=true"
    "&punctuate=true"
    "&interim_results=true"
    "&endpointing=300"
    "&utterance_end_ms=1000"
    "&vad_events=true"
    "&encoding=linear16"
    "&sample_rate=16000"
    "&channels=1"
)

# Flux: eot_threshold is the confidence the model needs before declaring the
# turn over — higher = more patient with thinking pauses.
FLUX_URL = (
    "wss://api.deepgram.com/v2/listen"
    "?model=flux-general-en"
    "&encoding=linear16"
    "&sample_rate=16000"
    f"&eot_threshold={os.environ.get('PMCP_FLUX_EOT', '0.8')}"
)

DG_URL = FLUX_URL if os.environ.get("PMCP_STT", "").lower() == "flux" else NOVA_URL


async def _connect(url: str, api_key: str):
    """Connect, tolerating the websockets header-kwarg rename across versions."""
    headers = {"Authorization": f"Token {api_key}"}
    try:
        return await websockets.connect(url, additional_headers=headers)  # websockets >= 12
    except TypeError:
        return await websockets.connect(url, extra_headers=headers)  # websockets < 12


class DeepgramLive:
    def __init__(self, api_key: str, url: str = DG_URL):
        self.api_key = api_key
        self.url = url
        self.ws = None

    async def __aenter__(self) -> "DeepgramLive":
        self.ws = await _connect(self.url, self.api_key)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def send_audio(self, data: bytes) -> None:
        if self.ws is not None:
            await self.ws.send(data)

    async def keepalive(self) -> None:
        """Deepgram closes an idle stream after ~10s of no audio; a periodic
        KeepAlive holds it open while the candidate is silent/thinking."""
        if self.ws is not None:
            await self.ws.send(json.dumps({"type": "KeepAlive"}))

    async def finish(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:  # noqa: BLE001
                pass

    async def events(self) -> AsyncIterator[dict]:
        if self.ws is None:
            return
        async for msg in self.ws:
            if isinstance(msg, (bytes, bytearray)):
                continue
            try:
                yield json.loads(msg)
            except json.JSONDecodeError:
                continue

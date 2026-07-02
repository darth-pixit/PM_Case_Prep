"""Async Deepgram streaming client (Turn-based / endpointing).

Hand-rolled over the `websockets` library so there's no Deepgram SDK version
churn. We ask for interim results (live partial transcript), word timestamps
(delivery metrics), and endpointing + utterance-end events (turn detection —
so Maya knows when you've finished a thought).

Audio expected: 16 kHz, mono, linear16 (PCM). The browser sends exactly that.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import websockets

DG_URL = (
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


async def _connect(url: str, api_key: str):
    """Connect, tolerating the websockets header-kwarg rename across versions."""
    headers = {"Authorization": f"Token {api_key}"}
    try:
        return await websockets.connect(url, additional_headers=headers)  # websockets >= 12
    except TypeError:
        return await websockets.connect(url, extra_headers=headers)  # websockets < 12


class DeepgramLive:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws = None

    async def __aenter__(self) -> "DeepgramLive":
        self.ws = await _connect(DG_URL, self.api_key)
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

"""Whiteboard / photo input seam (multimodal).

Claude reads handwriting, sketches, funnels, 2x2 matrices, and metric trees
natively via vision — no OCR pipeline needed. This helper builds the image
content block so a candidate can submit a photo of their scratch work as a turn.

Wire it into the CLI/interviewer by appending the block to a candidate message:

    from .vision import image_turn
    interviewer.messages.append(image_turn("whiteboard.png",
        "Here's my prioritization 2x2 — walk you through it?"))
    reply = interviewer._run_loop()

Roadmap: the full "interactive whiteboard" (AI draws, candidate annotates and
sends back) builds on this same block plus a canvas surface in the web client.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


def image_turn(image_path: str | Path, text: str) -> dict[str, Any]:
    """Return a user message with an image block + a text block."""
    path = Path(image_path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            },
            {"type": "text", "text": text},
        ],
    }

"""Whiteboard / photo input (multimodal).

Claude reads handwriting, sketches, funnels, 2x2 matrices, and metric trees
natively via vision — no OCR pipeline needed. These helpers build the image
content so a candidate can submit a photo of their scratch work as a turn.

Roadmap: the full "interactive whiteboard" (AI draws, candidate annotates and
sends back) builds on this same block plus a canvas surface in the web client.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


def image_content(image_path: str | Path, text: str) -> list[dict[str, Any]]:
    """Return content blocks: [image, text] — ready to send as a user turn."""
    path = Path(image_path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        },
        {"type": "text", "text": text},
    ]


def image_turn(image_path: str | Path, text: str) -> dict[str, Any]:
    """Return a full user message with an image + text block."""
    return {"role": "user", "content": image_content(image_path, text)}

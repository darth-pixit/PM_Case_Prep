"""Speech-to-text for voice input.

Primary path: Deepgram (Nova-3) over a plain HTTPS POST — no SDK dependency, so
nothing new to `pip install`; you just need a DEEPGRAM_API_KEY. Swapping to
OpenAI Whisper or a local faster-whisper model is a small change (see README).

Optional: record from the mic directly if `sounddevice` is installed.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path

DEEPGRAM_URL = (
    "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true"
)

# Deepgram autodetects most formats, but sending an accurate Content-Type helps.
_AUDIO_MIME = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".webm": "audio/webm",
    ".aac": "audio/aac",
}


class TranscriptionError(RuntimeError):
    pass


def voice_configured() -> bool:
    return bool(os.environ.get("DEEPGRAM_API_KEY"))


def transcribe(audio_path: str | Path) -> str:
    """Transcribe an audio file to text with Deepgram."""
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise TranscriptionError(
            "Voice input needs a Deepgram key. Set DEEPGRAM_API_KEY in your .env "
            "(get one free at https://console.deepgram.com)."
        )
    path = Path(audio_path)
    if not path.exists():
        raise TranscriptionError(f"Audio file not found: {path}")

    mime = (
        _AUDIO_MIME.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )
    req = urllib.request.Request(
        DEEPGRAM_URL,
        data=path.read_bytes(),
        method="POST",
        headers={"Authorization": f"Token {key}", "Content-Type": mime},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        raise TranscriptionError(f"Deepgram error {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001 - surface any network/parse failure
        raise TranscriptionError(f"Transcription failed: {exc}") from exc

    try:
        return payload["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError) as exc:
        raise TranscriptionError("Unexpected Deepgram response shape.") from exc


# --- Optional: record from the microphone -----------------------------------


def mic_available() -> bool:
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401

        return True
    except Exception:
        return False


def record(seconds: float | None = None, samplerate: int = 16000) -> str:
    """Record mono audio from the default mic to a temp WAV; return its path.

    If `seconds` is None, records until the user presses Enter.
    Requires `sounddevice` + `numpy` (see requirements.txt optional extras).
    """
    import tempfile
    import wave

    import numpy as np
    import sounddevice as sd

    frames: list = []

    def _callback(indata, _frames, _time, _status):  # pragma: no cover - realtime
        frames.append(indata.copy())

    with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", callback=_callback):
        if seconds:
            sd.sleep(int(seconds * 1000))
        else:
            input()  # blocks until Enter

    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(audio.tobytes())
    return tmp.name

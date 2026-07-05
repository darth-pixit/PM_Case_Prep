"""Runnable text CLI that drives one full case end-to-end.

    python -m pmcaseprep.cli                # runs the default (first) case
    python -m pmcaseprep.cli cases/foo.json # runs a specific case

Commands during a case:  /hint   ask for a graduated nudge
                         /done   finish and get your scorecard
                         /quit   abort without grading

Voice mode (STT in / TTS out) and whiteboard photo input are marked TODO; see
README "Roadmap". The reasoning + grading loop below is provider-complete today.
"""

from __future__ import annotations

import os
import shlex
import sys
import uuid
from pathlib import Path

from .case_loader import default_case_path, load_case
from .grader import grade, weighted_result
from .interviewer import Interviewer
from .models import ScoreCard
from .skill_graph import SkillGraph
from .transcribe import TranscriptionError, mic_available, record, transcribe, voice_configured
from .vision import image_content

MODEL = os.environ.get("PMCP_MODEL", "claude-opus-4-8")

_BAND_LABEL = {
    "strong_hire": "STRONG HIRE",
    "hire": "HIRE",
    "no_hire": "NO HIRE",
    "strong_no_hire": "STRONG NO HIRE",
}
_HINT_PROMPT = (
    "[The candidate asks for a hint. Give ONE graduated nudge for where they are "
    "right now — a question or a pointer to the missing dimension. Do not solve it.]"
)


def _make_client():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # dotenv is optional; env vars still work
    try:
        import anthropic
    except ImportError:
        sys.exit("The 'anthropic' package is not installed. Run: pip install -r requirements.txt")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        sys.exit(
            "No Anthropic credentials found. Set ANTHROPIC_API_KEY in your environment "
            "or a .env file (see .env.example)."
        )
    return anthropic.Anthropic()


def _print_scorecard(card: ScoreCard, weighted: float, band: str) -> None:
    print("\n" + "=" * 64)
    print(f"  SCORECARD — {_BAND_LABEL.get(band, band)}   (weighted {weighted:.2f}/4)")
    print("=" * 64)
    for ds in card.dimension_scores:
        print(f"  {ds.dimension:<16} {ds.score}/4  — {ds.justification}")
    print("\n  Category checklist:")
    for item in card.category_checklist:
        mark = "PASS" if item.met else "MISS"
        print(f"   [{mark}] {item.criterion}")
        if item.note:
            print(f"          {item.note}")
    if card.red_flags:
        print("\n  Red flags:")
        for rf in card.red_flags:
            print(f"   ! {rf}")
    print(f"\n  Top improvement: {card.top_improvement}")
    print(f"\n  {card.summary}")
    print("=" * 64)


def _print_input_help(voice_on: bool, mic_on: bool) -> None:
    print("How to answer — you can type, speak, or sketch:")
    print("  • just type your thinking out loud and press Enter")
    print("  • /voice <audio-file>    speak your answer, then point to the recording")
    if mic_on:
        print("  • /record [seconds]      record from your mic right now")
    print("  • /photo <image> [note]  share a whiteboard/sketch (funnels, 2x2s, metric trees)")
    print("  • /hint   nudge      /done   finish & grade      /quit   abort")
    voice = "ready" if voice_on else "off — add DEEPGRAM_API_KEY to enable /voice and /record"
    print(f"  [voice input: {voice}]   [photo input: ready via Claude vision]\n")


def _photo_turn(argstr: str):
    parts = shlex.split(argstr)
    if not parts:
        print("Usage: /photo <image-file> [optional note]   (tip: drag the file into the terminal)")
        return None
    path = parts[0]
    note = " ".join(parts[1:]) or "Here's a sketch of my thinking — take a look."
    if not Path(path).exists():
        print(f"Image not found: {path}")
        return None
    try:
        content = image_content(path, note)
    except Exception as exc:  # noqa: BLE001
        print(f"Couldn't read image: {exc}")
        return None
    print(f"(sent photo: {path})")
    return content


def _voice_turn(argstr: str):
    parts = shlex.split(argstr)
    if not parts:
        print("Usage: /voice <audio-file>   (e.g. a Voice Memo .m4a, or .mp3/.wav)")
        return None
    try:
        text = transcribe(parts[0])
    except TranscriptionError as exc:
        print(str(exc))
        return None
    if not text:
        print("(no speech detected)")
        return None
    print(f'(transcribed) "{text}"')
    return text


def _record_turn(argstr: str, mic_on: bool):
    if not mic_on:
        print(
            "Mic recording needs the optional 'sounddevice' package: pip install sounddevice numpy "
            "(on Mac also: brew install portaudio). Or record on your phone and use /voice <file>."
        )
        return None
    if not voice_configured():
        print("Recording also needs a Deepgram key to transcribe. Set DEEPGRAM_API_KEY in .env.")
        return None
    parts = shlex.split(argstr)
    seconds = float(parts[0]) if parts else None
    print(f"Recording for {seconds:.0f}s..." if seconds else "Recording... press Enter to stop.")
    try:
        text = transcribe(record(seconds))
    except TranscriptionError as exc:
        print(str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"Recording failed: {exc}")
        return None
    if not text:
        print("(no speech detected)")
        return None
    print(f'(transcribed) "{text}"')
    return text


def run(case_path: Path) -> None:
    case = load_case(case_path)
    client = _make_client()
    interviewer = Interviewer(client, case, MODEL)
    graph = SkillGraph()
    session_id = uuid.uuid4().hex[:8]

    voice_on = voice_configured()
    mic_on = mic_available()

    print(f"\n=== {case.title}  [{case.archetype} / {case.type}] ===\n")
    print(f"{case.interviewer_name}: {case.prompt}\n")
    _print_input_help(voice_on, mic_on)

    while True:
        try:
            raw = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue

        cmd, _, argstr = raw.partition(" ")
        content = None  # what we send to the interviewer this turn

        if cmd == "/quit":
            print("Aborted (not graded).")
            graph.close()
            return
        elif cmd == "/done":
            break
        elif cmd == "/hint":
            content = _HINT_PROMPT
        elif cmd == "/photo":
            content = _photo_turn(argstr)
        elif cmd == "/voice":
            content = _voice_turn(argstr)
        elif cmd == "/record":
            content = _record_turn(argstr, mic_on)
        elif cmd.startswith("/"):
            print(f"Unknown command: {cmd}. Try /voice, /record, /photo, /hint, /done, /quit.")
        else:
            content = raw

        if content is None:  # command failed or was informational — reprompt
            continue

        reply = interviewer.respond_content(content)
        if reply:
            print(f"\n{case.interviewer_name}: {reply}\n")
        if interviewer.concluded:
            break

    print("\nGrading your case...")
    card = grade(client, case, interviewer.transcript(), interviewer.observations_text(), MODEL)
    weighted, _min_dim, band = weighted_result(case, card)
    _print_scorecard(card, weighted, band)

    graph.record(session_id, case.id, case.archetype, card, band)
    print("\n" + graph.render_summary())
    graph.close()


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    case_path = Path(arg) if arg else default_case_path()
    run(case_path)


if __name__ == "__main__":
    main()

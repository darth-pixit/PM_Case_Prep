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
import sys
import uuid
from pathlib import Path

from .case_loader import default_case_path, load_case
from .grader import grade, weighted_result
from .interviewer import Interviewer
from .models import ScoreCard
from .skill_graph import SkillGraph

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


def run(case_path: Path) -> None:
    case = load_case(case_path)
    client = _make_client()
    interviewer = Interviewer(client, case, MODEL)
    graph = SkillGraph()
    session_id = uuid.uuid4().hex[:8]

    print(f"\n=== {case.title}  [{case.archetype} / {case.type}] ===\n")
    print(f"{case.interviewer_name}: {case.prompt}\n")
    print("(Type your thinking out loud. /hint for a nudge, /done to finish, /quit to abort.)\n")

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user == "/quit":
            print("Aborted (not graded).")
            graph.close()
            return
        if user == "/done":
            break
        turn = _HINT_PROMPT if user == "/hint" else user
        reply = interviewer.respond(turn)
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

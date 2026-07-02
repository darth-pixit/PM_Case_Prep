"""Delivery analytics — the "how you speak" layer.

From Deepgram's word-level timestamps we derive pace (words/min), pauses (gaps
between words), and filler usage. This is the axis Yoodli grades and Exponent
doesn't; fusing it with the rubric is a differentiator, not a nice-to-have.

Pure and dependency-free so it unit-tests offline.
"""

from __future__ import annotations

from dataclasses import dataclass

# Hard disfluencies — high precision, count them exactly.
FILLERS_CORE = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mmm"}
# Soft/hedge fillers — heuristic (these are also legitimate words), reported
# separately so the signal stays honest.
FILLERS_SOFT = {"like", "so", "basically", "actually", "literally", "right", "yeah", "okay"}

PAUSE_THRESHOLD_S = 0.7  # a gap this long or longer counts as a notable pause


@dataclass
class Word:
    text: str
    start: float  # seconds from stream start
    end: float


def _norm(token: str) -> str:
    return "".join(c for c in token.lower() if c.isalpha())


def turn_metrics(words: list[Word], pause_threshold: float = PAUSE_THRESHOLD_S) -> dict:
    """Metrics for a single spoken turn (one utterance)."""
    if not words:
        return {
            "words": 0, "duration_s": 0.0, "wpm": 0.0,
            "core_fillers": 0, "soft_fillers": 0,
            "pause_count": 0, "longest_pause_s": 0.0,
        }
    n = len(words)
    duration = max(0.0, words[-1].end - words[0].start)
    core = sum(1 for w in words if _norm(w.text) in FILLERS_CORE)
    soft = sum(1 for w in words if _norm(w.text) in FILLERS_SOFT)
    gaps = [max(0.0, words[i + 1].start - words[i].end) for i in range(n - 1)]
    pauses = [g for g in gaps if g >= pause_threshold]
    wpm = (n / (duration / 60)) if duration > 0 else 0.0
    return {
        "words": n,
        "duration_s": round(duration, 2),
        "wpm": round(wpm, 1),
        "core_fillers": core,
        "soft_fillers": soft,
        "pause_count": len(pauses),
        "longest_pause_s": round(max(gaps) if gaps else 0.0, 2),
    }


class DeliveryTracker:
    """Accumulates delivery metrics across every spoken turn in a session."""

    def __init__(self) -> None:
        self.turns = 0
        self.total_words = 0
        self.total_speaking_s = 0.0
        self.core = 0
        self.soft = 0
        self.pause_count = 0
        self.longest_pause_s = 0.0

    def add_turn(self, words: list[Word]) -> dict:
        m = turn_metrics(words)
        self.turns += 1
        self.total_words += m["words"]
        self.total_speaking_s += m["duration_s"]
        self.core += m["core_fillers"]
        self.soft += m["soft_fillers"]
        self.pause_count += m["pause_count"]
        self.longest_pause_s = max(self.longest_pause_s, m["longest_pause_s"])
        return self.snapshot()

    def snapshot(self) -> dict:
        wpm = (self.total_words / (self.total_speaking_s / 60)) if self.total_speaking_s > 0 else 0.0
        filler_total = self.core + self.soft
        rate = (filler_total / self.total_words * 100) if self.total_words else 0.0
        return {
            "words": self.total_words,
            "wpm": round(wpm, 1),
            "core_fillers": self.core,
            "soft_fillers": self.soft,
            "filler_rate_per_100": round(rate, 1),
            "pause_count": self.pause_count,
            "longest_pause_s": round(self.longest_pause_s, 2),
            "speaking_s": round(self.total_speaking_s, 1),
        }

    def summary_text(self) -> str:
        s = self.snapshot()
        if s["words"] == 0:
            return "No spoken input captured (text-only session)."
        pace = "rushed" if s["wpm"] > 175 else ("slow" if s["wpm"] < 110 else "well-paced")
        return (
            f"Spoke {s['words']} words at {s['wpm']} wpm ({pace}); "
            f"{s['core_fillers']} hard fillers (um/uh) plus {s['soft_fillers']} soft "
            f"(like/so), {s['filler_rate_per_100']} per 100 words; "
            f"{s['pause_count']} notable pauses, longest {s['longest_pause_s']}s."
        )

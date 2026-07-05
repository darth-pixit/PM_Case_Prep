"""Load and validate case files. This is the seam where RAG/retrieval would plug
in for a truly large case bank — for now the bank is a directory of JSON files
and "retrieval" is unseen-first random selection."""

from __future__ import annotations

import json
import random
from collections.abc import Collection
from pathlib import Path

from .models import Case

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


def load_case(path: str | Path) -> Case:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Case.model_validate(data)


def list_cases() -> list[Path]:
    return sorted(CASES_DIR.glob("*.json"))


def default_case_path() -> Path:
    cases = list_cases()
    if not cases:
        raise FileNotFoundError(f"No cases found in {CASES_DIR}")
    return cases[0]


def pick_case_path(
    done_case_ids: Collection[str] | None = None,
    rng: random.Random | None = None,
) -> Path:
    """Pick the next case for a user: a random one they haven't been graded on
    yet, falling back to a random case once they've seen the whole bank.

    `done_case_ids` comes from the user's skill-graph history; abandoned
    (ungraded) sessions deliberately don't count as "done"."""
    paths = list_cases()
    if not paths:
        raise FileNotFoundError(f"No cases found in {CASES_DIR}")
    chooser = rng or random
    if done_case_ids:
        done = set(done_case_ids)
        unseen = [p for p in paths if load_case(p).id not in done]
        if unseen:
            return chooser.choice(unseen)
    return chooser.choice(paths)

"""Load and validate case files. This is the seam where RAG/retrieval would plug
in for a large case bank — for the prototype we read a single JSON file."""

from __future__ import annotations

import json
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

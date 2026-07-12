"""Load and validate case files. This is the seam where RAG/retrieval would plug
in for a large case bank — for the prototype we read a single JSON file.

Two banks, deliberately separate so experiments never bleed into each other:
  * cases/*.json        — the original tutor experiment at `/` (one case).
  * cases/arena/*.json  — the category arena at `/arena` (5 categories x 5
    cases), with `_categories.json` describing the categories themselves.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .models import Case

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"
ARENA_DIR = CASES_DIR / "arena"
CATEGORIES_PATH = ARENA_DIR / "_categories.json"


def load_case(path: str | Path) -> Case:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Case.model_validate(data)


def list_cases() -> list[Path]:
    # Underscore-prefixed files are metadata (e.g. _categories.json), not cases.
    return sorted(p for p in CASES_DIR.glob("*.json") if not p.name.startswith("_"))


def default_case_path() -> Path:
    cases = list_cases()
    if not cases:
        raise FileNotFoundError(f"No cases found in {CASES_DIR}")
    return cases[0]


# --- Arena bank ----------------------------------------------------------------

def arena_case_paths() -> list[Path]:
    if not ARENA_DIR.is_dir():
        return []
    return sorted(p for p in ARENA_DIR.glob("*.json") if not p.name.startswith("_"))


def arena_categories() -> list[dict]:
    """The category manifest, in display order. Empty when the arena isn't built."""
    if not CATEGORIES_PATH.exists():
        return []
    return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))["categories"]


@lru_cache(maxsize=1)
def _arena_bank() -> tuple[Case, ...]:
    """The whole arena bank, parsed and validated ONCE per process. It sits on
    hot paths (catalog per page load, lookup per room visit AND per socket
    open) and the files are immutable per deploy — re-reading 25 JSON files
    from disk inside async handlers would just block the event loop."""
    return tuple(load_case(p) for p in arena_case_paths())


def arena_case_by_id(case_id: str) -> Optional[Case]:
    """Find one arena case by its `id` field."""
    for case in _arena_bank():
        if case.id == case_id:
            return case
    return None


def arena_catalog() -> list[dict]:
    """Categories with their cases' PUBLIC metadata only — titles and teasers,
    never hidden facts or grading notes (this JSON is served to the browser)."""
    cases = list(_arena_bank())
    by_cat: dict[str, list[Case]] = {}
    for c in cases:
        by_cat.setdefault(c.archetype, []).append(c)
    catalog = []
    for cat in arena_categories():
        listed = sorted(by_cat.get(cat["key"], []), key=lambda c: c.id)
        catalog.append(
            {
                **cat,
                "cases": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "type": c.type,
                        "teaser": c.teaser,
                        "minutes": c.minutes,
                    }
                    for c in listed
                ],
            }
        )
    return catalog

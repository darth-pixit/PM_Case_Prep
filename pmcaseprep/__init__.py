"""PM Case Prep — an AI-first product-manager case-interview tutor (prototype).

The package implements the core loop:

    clarify -> solve (candidate drives) -> graduated hints on demand
            -> rubric-graded scorecard -> longitudinal skill graph

Two agents, deliberately separated (see prompts.py):
  * Interviewer  — in-character, Socratic, never grades mid-flow, logs
                   observations silently while the candidate works.
  * Grader       — out-of-character, rubric-driven, runs once at the end
                   against anchor exemplars and returns a structured scorecard.

Voice (STT/TTS), vision (whiteboard photo input) and the company-persona
library are marked as TODO seams; the text loop is fully runnable today.
"""

__version__ = "0.1.0"

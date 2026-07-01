"""The interviewer agent: a manual Claude tool-use loop with a phase machine.

This is where the Claude Agent SDK / Managed Agents would slot in for a
production build. We use the raw Messages API tool loop here for full control
over mode transitions and the silent observation channel.
"""

from __future__ import annotations

from typing import Any

from .models import Case, Observation
from .prompts import build_interviewer_system
from .rubric import DIMENSION_KEYS

# Tools the interviewer can call. `log_observation` is a silent side-channel;
# `conclude_case` flips the session into grading.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "log_observation",
        "description": (
            "Silently record a strength or gap in the candidate's reasoning against a "
            "rubric dimension. Private — never surfaced to the candidate. Call this "
            "whenever you notice something scoreable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": DIMENSION_KEYS},
                "note": {"type": "string", "description": "What you observed, specifically."},
                "polarity": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                },
            },
            "required": ["dimension", "note", "polarity"],
        },
    },
    {
        "name": "conclude_case",
        "description": (
            "Call this when the candidate has finished or asked to wrap up. Signals "
            "the session to move to grading. Do not grade or give feedback yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the case is concluding."},
            },
            "required": ["reason"],
        },
    },
]


class Interviewer:
    """Holds the conversation, runs the tool loop, and accumulates observations."""

    def __init__(self, client: Any, case: Case, model: str, max_tokens: int = 16000):
        self.client = client
        self.case = case
        self.model = model
        self.max_tokens = max_tokens
        # Prompt caching: the system prompt (persona + case + facts) is a stable
        # prefix reused every turn — cache it so repeat reads are ~10% cost.
        self.system = [
            {
                "type": "text",
                "text": build_interviewer_system(case),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self.messages: list[dict[str, Any]] = []
        self.observations: list[Observation] = []
        self.concluded = False

    def respond(self, user_text: str) -> str:
        """Feed one candidate turn; run the tool loop; return the spoken reply."""
        self.messages.append({"role": "user", "content": user_text})
        return self._run_loop()

    def _run_loop(self) -> str:
        reply_parts: list[str] = []
        while True:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system,
                messages=self.messages,
                tools=TOOLS,
                # Interviewer stays snappy — no extended thinking for chat turns.
            )
            self.messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for block in resp.content:
                if block.type == "text":
                    reply_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_results.append(self._handle_tool(block))

            if resp.stop_reason == "tool_use":
                self.messages.append({"role": "user", "content": tool_results})
                continue
            break

        return "\n".join(p for p in reply_parts if p.strip())

    def _handle_tool(self, block: Any) -> dict[str, Any]:
        result = "ok"
        if block.name == "log_observation":
            try:
                self.observations.append(Observation(**block.input))
                result = "logged"
            except Exception as exc:  # pragma: no cover - defensive
                result = f"ignored ({exc})"
        elif block.name == "conclude_case":
            self.concluded = True
            result = "acknowledged — session will move to grading"
        return {"type": "tool_result", "tool_use_id": block.id, "content": result}

    # --- helpers for the grader -------------------------------------------

    def transcript(self) -> str:
        """Render the candidate/interviewer dialogue (text only, tools stripped)."""
        lines: list[str] = []
        for msg in self.messages:
            speaker = "Candidate" if msg["role"] == "user" else "Interviewer"
            content = msg["content"]
            if isinstance(content, str):
                lines.append(f"{speaker}: {content}")
            elif isinstance(content, list):
                for block in content:
                    text = getattr(block, "text", None)
                    if text is None and isinstance(block, dict):
                        text = block.get("text")
                    if text:
                        lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    def observations_text(self) -> str:
        return "\n".join(
            f"[{o.polarity}] {o.dimension}: {o.note}" for o in self.observations
        )

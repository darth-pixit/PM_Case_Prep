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
        self._turn_start = 0  # index of the first message of the current turn

    def respond(self, user_text: str) -> str:
        """Feed one text candidate turn; run the tool loop; return the reply."""
        return self.respond_content(user_text)

    def respond_content(self, content: Any) -> str:
        """Feed one candidate turn of any shape (text string or content blocks,
        e.g. an image + text for a whiteboard photo); run the loop; return reply."""
        self.messages.append({"role": "user", "content": content})
        self._turn_start = len(self.messages)
        return self._run_loop()

    def align_shown(self, shown_text: str) -> None:
        """Rewrite this turn's assistant messages so the model's memory contains
        EXACTLY what the candidate saw (or "(listening)" when nothing was shown).

        Without this, suppressed narration and swallowed replies stay in the
        conversation — the model then believes it said things that never reached
        the screen ("as I already mentioned…"), and the grader reads a transcript
        that differs from the candidate's actual experience."""
        last_assistant = None
        for i in range(self._turn_start, len(self.messages)):
            if self.messages[i]["role"] == "assistant":
                last_assistant = i
        if last_assistant is None:
            return
        for i in range(self._turn_start, len(self.messages)):
            msg = self.messages[i]
            if msg["role"] != "assistant":
                continue
            blocks: list[Any] = [
                {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                for b in msg["content"]
                if getattr(b, "type", "") == "tool_use"
            ]
            if i == last_assistant:
                blocks.insert(0, {"type": "text", "text": shown_text})
            elif not blocks:
                blocks = [{"type": "text", "text": shown_text}]
            msg["content"] = blocks

    def _run_loop(self) -> str:
        # Text emitted ALONGSIDE tool calls is usually the model narrating to
        # itself ("I'll note that...") — never meant for the candidate. So the
        # reply is the text of the FINAL response only; earlier text is kept as
        # a fallback in case the model front-loaded its whole answer.
        all_text: list[str] = []
        last_text: list[str] = []
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

            last_text = []
            tool_results = []
            for block in resp.content:
                if block.type == "text":
                    last_text.append(block.text)
                    all_text.append(block.text)
                elif block.type == "tool_use":
                    tool_results.append(self._handle_tool(block))

            if resp.stop_reason == "tool_use":
                self.messages.append({"role": "user", "content": tool_results})
                continue
            break

        parts = last_text if any(p.strip() for p in last_text) else all_text
        return "\n".join(p for p in parts if p.strip())

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

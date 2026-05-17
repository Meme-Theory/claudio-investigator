"""Claude tool-use orchestration loop.

The agent owns one investigation end-to-end. It is *not* a fixed pipeline —
the model picks which tools to call and in what order, constrained only by
the system prompt, the tool schemas, and the budget.

The loop terminates on any of:
  - `submit_verdict` tool call (success)
  - `stop_reason == "end_turn"` with no tool calls (treat as low confidence)
  - Budget exhaustion (token, iteration, or USD cap)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from anthropic import Anthropic

from .budget import Budget
from .rubric import SUBMIT_VERDICT_TOOL, SYSTEM_PROMPT, build_initial_prompt
from .schema import Verdict
from .tools import TOOLS, TOOL_RUNNERS

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.2


class InvestigationResult:
    """Bundle of what one investigation produced."""

    def __init__(
        self,
        verdict: Verdict | None,
        budget: Budget,
        transcript: list[dict],
        model: str,
        terminated_by: str,
    ) -> None:
        self.verdict = verdict
        self.budget = budget
        self.transcript = transcript
        self.model = model
        self.terminated_by = terminated_by  # 'submit_verdict' | 'end_turn' | 'budget_exhausted' | 'no_tools'
        self.completed_at = datetime.now(UTC)


def investigate(
    artist_name: str,
    hints: dict[str, Any] | None = None,
    *,
    client: Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    budget: Budget | None = None,
) -> InvestigationResult:
    """Run one investigation. Returns a populated InvestigationResult.

    The caller is responsible for persistence (writing the record, posting the
    GitHub comment, opening the PR). This function is pure inputs -> outputs.
    """
    raise NotImplementedError(
        "Phase 2 implementation. The skeleton below shows the intended loop shape."
    )

    # --- Reference skeleton — implement in Phase 2 ----------------------------
    # client = client or Anthropic()
    # budget = budget or Budget()
    # tools_schema = [*TOOLS, SUBMIT_VERDICT_TOOL]
    # # The last tool gets `cache_control` so the whole tools array caches with
    # # the system prompt — both are stable per investigation.
    # tools_schema[-1] = {**tools_schema[-1], "cache_control": {"type": "ephemeral"}}
    #
    # messages: list[dict] = [
    #     {"role": "user", "content": build_initial_prompt(artist_name, hints or {})}
    # ]
    # transcript: list[dict] = []
    #
    # while budget.has_remaining():
    #     response = client.messages.create(
    #         model=model,
    #         max_tokens=DEFAULT_MAX_TOKENS,
    #         temperature=DEFAULT_TEMPERATURE,
    #         system=[{
    #             "type": "text",
    #             "text": SYSTEM_PROMPT,
    #             "cache_control": {"type": "ephemeral"},
    #         }],
    #         tools=tools_schema,
    #         messages=messages,
    #     )
    #     budget.charge(response.usage)
    #     transcript.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
    #
    #     if response.stop_reason == "end_turn":
    #         return InvestigationResult(None, budget, transcript, model, "end_turn")
    #
    #     tool_uses = [b for b in response.content if b.type == "tool_use"]
    #     if not tool_uses:
    #         return InvestigationResult(None, budget, transcript, model, "no_tools")
    #
    #     # Terminal action — submit_verdict — intercepted, never executed as a tool.
    #     for block in tool_uses:
    #         if block.name == "submit_verdict":
    #             verdict = Verdict(**block.input)
    #             return InvestigationResult(verdict, budget, transcript, model, "submit_verdict")
    #
    #     # Execute requested tools and feed results back.
    #     tool_results = []
    #     for block in tool_uses:
    #         runner = TOOL_RUNNERS.get(block.name)
    #         if runner is None:
    #             result = {"error": f"unknown tool: {block.name}"}
    #         else:
    #             try:
    #                 result = runner(budget=budget, **block.input)
    #             except Exception as e:  # tool errors are passed back to the model, not fatal
    #                 logger.exception("tool %s raised", block.name)
    #                 result = {"error": str(e), "tool": block.name}
    #         tool_results.append({
    #             "type": "tool_result",
    #             "tool_use_id": block.id,
    #             "content": json.dumps(result),
    #         })
    #
    #     messages.append({"role": "assistant", "content": response.content})
    #     messages.append({"role": "user", "content": tool_results})
    #
    # return InvestigationResult(None, budget, transcript, model, "budget_exhausted")

"""Claude tool-use orchestration loop.

The agent owns one investigation end-to-end. It is *not* a fixed pipeline —
the model picks which tools to call and in what order, constrained only by
the system prompt, the tool schemas, and the budget.

The loop terminates on any of:
  - `submit_verdict` tool call (success)
  - `stop_reason == "end_turn"` with no tool calls (agent gave up)
  - `stop_reason == "refusal"` (model refused for safety reasons)
  - Budget exhaustion (iteration, token, or USD cap)
  - Anthropic API error (after SDK retries)
  - Invalid verdict payload (model called submit_verdict with bad input)

The SDK auto-retries 429 / 5xx with exponential backoff per its `max_retries`
default; we don't need extra retry logic here.

Cache strategy: `cache_control: {type: "ephemeral"}` on the system text block.
Tools render before system in the prompt prefix (see prompt-caching docs), so
that single breakpoint caches both `tools` and `system` together — they're the
stable prefix across iterations within one investigation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from anthropic import Anthropic, APIError

from .budget import Budget
from .rubric import (
    REQUEST_ESCALATION_TOOL,
    SONNET_ADDENDUM,
    SUBMIT_VERDICT_TOOL,
    SYSTEM_PROMPT,
    build_initial_prompt,
)
from .schema import Verdict
from .tools import TOOL_RUNNERS, TOOLS

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5"
ESCALATION_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.2

# Loop terminated_by values — keep stable; downstream code switches on these.
TERMINATED_SUBMIT_VERDICT = "submit_verdict"
TERMINATED_END_TURN = "end_turn"
TERMINATED_REFUSAL = "refusal"
TERMINATED_NO_TOOLS = "no_tools"
TERMINATED_BUDGET = "budget_exhausted"
TERMINATED_API_ERROR = "api_error"
TERMINATED_INVALID_VERDICT = "invalid_verdict"


@dataclass
class InvestigationResult:
    """Bundle of what one investigation produced."""

    verdict: Verdict | None
    budget: Budget
    transcript: list[dict] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    terminated_by: str = ""
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


# --- Helpers ----------------------------------------------------------------


def _block_to_dict(block: Any) -> dict:
    """Best-effort serialize a content block for the transcript record.

    SDK content blocks are Pydantic v2 models with `.model_dump()`. Tests pass
    `MagicMock` blocks — fall back to attribute-by-attribute serialization.
    """
    if hasattr(block, "model_dump"):
        try:
            return block.model_dump()
        except Exception:
            pass
    out: dict[str, Any] = {}
    for key in ("type", "text", "id", "name", "input", "thinking"):
        value = getattr(block, key, None)
        if value is not None:
            out[key] = value
    return out


def _execute_tool(name: str, input_data: dict, budget: Budget) -> tuple[dict, bool]:
    """Run one non-terminal tool; capture exceptions as structured errors.

    Returns (payload, is_error). On error, the payload is shaped so the model
    can read why it failed without crashing the loop.
    """
    runner = TOOL_RUNNERS.get(name)
    if runner is None:
        return ({"error": f"unknown tool: {name}"}, True)
    try:
        # The vision tool needs the budget to enforce its per-investigation cap.
        if name == "analyze_album_art":
            return (runner(budget=budget, **input_data), False)
        return (runner(**input_data), False)
    except Exception as e:
        logger.exception("tool %s raised", name)
        return ({"error": str(e), "tool": name}, True)


def _build_system_blocks(escalated: bool = False) -> list[dict]:
    """System prompt with a cache breakpoint covering tools+system.

    When `escalated=True`, the Sonnet addendum is appended to the prompt.
    The cache breakpoint moves with it — Haiku's cached prefix is invalidated
    on escalation (different model, different prefix), which is fine: the
    handover is rare and the addendum is worth the cache miss.
    """
    text = SYSTEM_PROMPT + SONNET_ADDENDUM if escalated else SYSTEM_PROMPT
    return [{
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }]


# --- Main loop --------------------------------------------------------------


def investigate(
    artist_name: str,
    hints: dict[str, Any] | None = None,
    *,
    client: Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    budget: Budget | None = None,
) -> InvestigationResult:
    """Run one investigation. Pure inputs -> outputs.

    Caller is responsible for persistence — writing the curated record, posting
    the GitHub comment, opening the PR. This function just produces the
    verdict (or a structured failure).
    """
    client = client or Anthropic()
    budget = budget or Budget()
    # Haiku starts with request_escalation available; Sonnet doesn't (terminal
    # for it). We rebuild tools_schema on escalation to drop it. If the caller
    # explicitly starts from a non-Haiku model, treat that as already-escalated.
    starts_at_haiku = model == DEFAULT_MODEL
    tools_schema = [*TOOLS, SUBMIT_VERDICT_TOOL]
    if starts_at_haiku:
        tools_schema.append(REQUEST_ESCALATION_TOOL)
    system_blocks = _build_system_blocks(escalated=not starts_at_haiku)

    messages: list[dict] = [
        {"role": "user", "content": build_initial_prompt(artist_name, hints or {})}
    ]
    transcript: list[dict] = []

    while budget.has_remaining():
        try:
            response = client.messages.create(
                model=model,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=DEFAULT_TEMPERATURE,
                system=system_blocks,
                tools=tools_schema,
                messages=messages,
            )
        except APIError as e:
            logger.exception("Anthropic API error")
            return InvestigationResult(
                verdict=None,
                budget=budget,
                transcript=transcript,
                model=model,
                terminated_by=TERMINATED_API_ERROR,
                error=str(e),
            )

        budget.charge(response.usage)
        transcript.append({
            "role": "assistant",
            "stop_reason": getattr(response, "stop_reason", None),
            "content": [_block_to_dict(b) for b in (response.content or [])],
        })

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            return InvestigationResult(
                verdict=None, budget=budget, transcript=transcript,
                model=model, terminated_by=TERMINATED_REFUSAL,
            )
        if stop_reason == "end_turn":
            return InvestigationResult(
                verdict=None, budget=budget, transcript=transcript,
                model=model, terminated_by=TERMINATED_END_TURN,
            )

        tool_uses = [b for b in (response.content or []) if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            return InvestigationResult(
                verdict=None, budget=budget, transcript=transcript,
                model=model, terminated_by=TERMINATED_NO_TOOLS,
            )

        # submit_verdict is terminal — intercept BEFORE executing any other tool
        # this turn. Doing it first means the agent doesn't waste a tool call
        # if it submits alongside another action.
        for block in tool_uses:
            if getattr(block, "name", None) == "submit_verdict":
                try:
                    verdict = Verdict(**(block.input or {}))
                except Exception as e:
                    logger.exception("invalid verdict payload from submit_verdict")
                    return InvestigationResult(
                        verdict=None, budget=budget, transcript=transcript,
                        model=model, terminated_by=TERMINATED_INVALID_VERDICT,
                        error=str(e),
                    )
                return InvestigationResult(
                    verdict=verdict, budget=budget, transcript=transcript,
                    model=model, terminated_by=TERMINATED_SUBMIT_VERDICT,
                )

        # request_escalation is "soft-terminal" — Haiku stops, Sonnet picks up.
        # Swap model + budget + system prompt + tools, acknowledge the call as
        # a tool_result, and continue the loop. The next iteration calls Sonnet
        # with the full Haiku transcript visible to it.
        escalation_block = next(
            (b for b in tool_uses if getattr(b, "name", None) == "request_escalation"),
            None,
        )
        if escalation_block is not None:
            budget.escalate_to_sonnet()
            model = ESCALATION_MODEL
            system_blocks = _build_system_blocks(escalated=True)
            tools_schema = [*TOOLS, SUBMIT_VERDICT_TOOL]  # drop request_escalation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": escalation_block.id,
                    "content": json.dumps({
                        "status": "escalated",
                        "active_model": ESCALATION_MODEL,
                        "note": (
                            "You are now Sonnet 4.6. Apply the stricter "
                            "requirements in the SONNET ESCALATION ADDENDUM in "
                            "your system prompt. Continue the investigation; "
                            "submit_verdict is your terminal action."
                        ),
                    }),
                    "is_error": False,
                }],
            })
            continue

        # Execute requested tools and feed results back.
        tool_results = []
        for block in tool_uses:
            payload, is_error = _execute_tool(
                name=block.name,
                input_data=block.input or {},
                budget=budget,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(payload, default=str),
                "is_error": is_error,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return InvestigationResult(
        verdict=None, budget=budget, transcript=transcript,
        model=model, terminated_by=TERMINATED_BUDGET,
    )

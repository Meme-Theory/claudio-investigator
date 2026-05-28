"""Tests for the agent tool-use loop.

Strategy: stub the Anthropic client with `MagicMock` and have it return
scripted `Message` objects that exercise each loop branch (tool call →
result → next iteration; submit_verdict terminal; end_turn without verdict;
refusal; budget exhaustion).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from investigator.agent import (
    TERMINATED_BUDGET,
    TERMINATED_END_TURN,
    TERMINATED_INVALID_VERDICT,
    TERMINATED_NO_TOOLS,
    TERMINATED_REFUSAL,
    TERMINATED_SUBMIT_VERDICT,
    investigate,
)
from investigator.budget import Budget


# --- Mock helpers ----------------------------------------------------------


def _tool_use_block(name: str, input_data: dict, block_id: str = "toolu_1"):
    """Build a content block that quacks like the SDK's `ToolUseBlock`."""
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=input_data)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _make_response(
    content: list,
    *,
    stop_reason: str = "tool_use",
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Build a Message-like object the agent loop can consume."""
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def _make_client(scripted_responses):
    """A MagicMock Anthropic client that returns each scripted response in turn."""
    client = MagicMock()
    client.messages.create.side_effect = scripted_responses
    return client


# --- Budget --------------------------------------------------------------- #


def test_budget_starts_with_remaining() -> None:
    b = Budget()
    assert b.has_remaining()


def test_budget_charge_increments_iterations() -> None:
    b = Budget()
    b.charge({"input_tokens": 100, "output_tokens": 50})
    assert b.iterations == 1
    assert b.input_tokens == 100
    assert b.output_tokens == 50


def test_budget_usd_calculated_at_haiku_pricing() -> None:
    b = Budget()
    b.charge({"input_tokens": 1_000_000, "output_tokens": 0})
    assert abs(b.usd_spent - 1.0) < 1e-6


def test_budget_iterations_cap() -> None:
    b = Budget(max_iterations=2)
    b.charge({"input_tokens": 1, "output_tokens": 1})
    b.charge({"input_tokens": 1, "output_tokens": 1})
    assert not b.has_remaining()
    assert b.exhaustion_reason == "max_iterations"


def test_budget_usd_cap() -> None:
    b = Budget(max_usd=0.5, max_tokens_total=10_000_000)
    b.charge({"input_tokens": 500_000, "output_tokens": 0})
    assert not b.has_remaining()
    assert b.exhaustion_reason == "max_usd"


def test_budget_vision_pass_cap() -> None:
    b = Budget(max_vision_passes=1)
    assert b.can_use_vision()
    b.record_vision_pass()
    assert not b.can_use_vision()


def test_budget_total_excludes_cache_reads() -> None:
    """cache_read_tokens are re-reads of already-counted content; they must
    NOT count toward the iteration cap or we trip prematurely on rich tool
    results."""
    b = Budget(max_tokens_total=10_000)
    # Mostly cache reads — should NOT exhaust the cap.
    b.charge({
        "input_tokens": 500,
        "output_tokens": 100,
        "cache_read_input_tokens": 50_000,  # massive, but doesn't count
        "cache_creation_input_tokens": 200,
    })
    assert b.has_remaining()
    assert b.total_tokens == 500 + 100 + 200  # excludes cache_read
    # ...but the report still includes it under billable_tokens for
    # cost-tracking visibility:
    summary = b.summary()
    assert summary["cache_read_tokens"] == 50_000
    assert summary["billable_tokens"] == 500 + 100 + 50_000 + 200


# --- Agent loop ---------------------------------------------------------- #


def _valid_verdict_input() -> dict:
    return {
        "verdict": "likely_ai",
        "confidence": 0.82,
        "markers": ["2024-onwards", "no-musicbrainz"],
        "reasoning": "Catalog originates 2025 with no MusicBrainz entry.",
    }


def test_agent_terminates_on_submit_verdict() -> None:
    client = _make_client([
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input())],
            stop_reason="tool_use",
        ),
    ])
    result = investigate("Test Artist", client=client)
    assert result.terminated_by == TERMINATED_SUBMIT_VERDICT
    assert result.verdict is not None
    assert result.verdict.verdict == "likely_ai"
    assert result.verdict.confidence == 0.82
    # One API call was enough
    assert client.messages.create.call_count == 1


def test_agent_terminates_on_end_turn_without_verdict() -> None:
    client = _make_client([
        _make_response([_text_block("Done.")], stop_reason="end_turn"),
    ])
    result = investigate("Test Artist", client=client)
    assert result.terminated_by == TERMINATED_END_TURN
    assert result.verdict is None


def test_agent_terminates_on_refusal() -> None:
    client = _make_client([
        _make_response([_text_block("I cannot help with this.")], stop_reason="refusal"),
    ])
    result = investigate("Test Artist", client=client)
    assert result.terminated_by == TERMINATED_REFUSAL


def test_agent_terminates_on_no_tool_blocks() -> None:
    """stop_reason is tool_use but no tool_use blocks present — abnormal but defensive."""
    client = _make_client([
        _make_response([_text_block("hmm")], stop_reason="tool_use"),
    ])
    result = investigate("Test Artist", client=client)
    assert result.terminated_by == TERMINATED_NO_TOOLS


def test_agent_executes_tool_then_continues() -> None:
    """First response: tool call. Second response: submit_verdict. Verify the
    tool result actually flows back into the next API call's message history."""
    client = _make_client([
        _make_response(
            [_tool_use_block("lookup_itunes", {"artist_name": "X"}, block_id="toolu_a")],
            stop_reason="tool_use",
        ),
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input(), block_id="toolu_b")],
            stop_reason="tool_use",
        ),
    ])

    # Patch lookup_itunes so it doesn't hit the live network.
    from investigator.tools import TOOL_RUNNERS

    fake_result = {"found": False, "query": "X"}
    real_lookup = TOOL_RUNNERS["lookup_itunes"]
    TOOL_RUNNERS["lookup_itunes"] = lambda **_: fake_result
    try:
        result = investigate("X", client=client)
    finally:
        TOOL_RUNNERS["lookup_itunes"] = real_lookup

    assert result.terminated_by == TERMINATED_SUBMIT_VERDICT
    assert result.verdict is not None
    # Two API calls; the second saw the tool result.
    assert client.messages.create.call_count == 2
    second_call_kwargs = client.messages.create.call_args_list[1].kwargs
    messages = second_call_kwargs["messages"]
    # Last user message in iteration 2 should be the tool_result for toolu_a
    last_user = messages[-1]
    assert last_user["role"] == "user"
    tool_results = last_user["content"]
    assert any(
        tr.get("tool_use_id") == "toolu_a" and not tr.get("is_error")
        for tr in tool_results
    )


def test_agent_handles_unknown_tool_with_error_flag() -> None:
    """Model picks a tool not in our registry → tool_result returned with is_error=True."""
    client = _make_client([
        _make_response(
            [_tool_use_block("imaginary_tool", {}, block_id="toolu_x")],
            stop_reason="tool_use",
        ),
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input())],
            stop_reason="tool_use",
        ),
    ])
    result = investigate("X", client=client)
    assert result.terminated_by == TERMINATED_SUBMIT_VERDICT
    second_call_kwargs = client.messages.create.call_args_list[1].kwargs
    tool_results = second_call_kwargs["messages"][-1]["content"]
    assert tool_results[0]["is_error"] is True
    assert "unknown tool" in tool_results[0]["content"]


def test_agent_terminates_after_persistent_invalid_verdict_payloads() -> None:
    """Three malformed submit_verdict calls in a row → terminate with INVALID_VERDICT.

    MAX_INVALID_SUBMIT_ATTEMPTS=2 means the first two bad submits get fed back
    as tool_results for retry; the third one exceeds the cap and the loop gives
    up. This protects against a model stuck in a malformed-submit loop.
    """
    bad_input = {
        "verdict": "ai",
        "confidence": 1.5,  # out of [0, 1] range — Pydantic Field constraint
        "markers": [],
        "reasoning": "x",
    }
    client = _make_client([
        _make_response([_tool_use_block("submit_verdict", bad_input, block_id="b1")], stop_reason="tool_use"),
        _make_response([_tool_use_block("submit_verdict", bad_input, block_id="b2")], stop_reason="tool_use"),
        _make_response([_tool_use_block("submit_verdict", bad_input, block_id="b3")], stop_reason="tool_use"),
    ])
    result = investigate("X", client=client)
    assert result.terminated_by == TERMINATED_INVALID_VERDICT
    assert result.verdict is None
    assert result.error is not None
    assert client.messages.create.call_count == 3


def test_agent_retries_invalid_verdict_payload_then_succeeds() -> None:
    """A single malformed submit_verdict gets fed back as a tool_result error;
    the agent's next response submits a valid verdict and the loop succeeds.

    This is the normal-recovery path: agents that truncate mid-call (e.g. hit
    max_tokens before writing `reasoning`) should retry once and land it.
    """
    bad_input = {
        "verdict": "ai",
        "confidence": 0.85,
        "markers": [],
        # reasoning missing — typical max_tokens-truncation failure
    }
    client = _make_client([
        _make_response([_tool_use_block("submit_verdict", bad_input, block_id="b1")], stop_reason="tool_use"),
        _make_response([_tool_use_block("submit_verdict", _valid_verdict_input(), block_id="b2")], stop_reason="tool_use"),
    ])
    result = investigate("X", client=client)
    assert result.terminated_by == TERMINATED_SUBMIT_VERDICT
    assert result.verdict is not None
    assert result.verdict.verdict == "likely_ai"
    assert client.messages.create.call_count == 2


def test_agent_terminates_on_budget_exhaustion() -> None:
    b = Budget(max_iterations=0)  # already exhausted before the first call
    client = _make_client([])
    result = investigate("X", client=client, budget=b)
    assert result.terminated_by == TERMINATED_BUDGET
    # Loop never entered, so no API call was made.
    assert client.messages.create.call_count == 0


def test_agent_passes_cache_control_on_system_block() -> None:
    client = _make_client([
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input())],
            stop_reason="tool_use",
        ),
    ])
    investigate("X", client=client)
    first_kwargs = client.messages.create.call_args_list[0].kwargs
    system_blocks = first_kwargs["system"]
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_agent_includes_hints_in_initial_prompt() -> None:
    client = _make_client([
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input())],
            stop_reason="tool_use",
        ),
    ])
    investigate(
        "Echo",
        hints={"spotify_url": "https://open.spotify.com/artist/abc"},
        client=client,
    )
    first_kwargs = client.messages.create.call_args_list[0].kwargs
    initial_user_msg = first_kwargs["messages"][0]
    assert initial_user_msg["role"] == "user"
    assert "spotify.com/artist/abc" in initial_user_msg["content"]


def test_agent_records_budget_usage_across_iterations() -> None:
    client = _make_client([
        _make_response(
            [_tool_use_block("lookup_itunes", {"artist_name": "X"}, block_id="t1")],
            stop_reason="tool_use",
            input_tokens=300,
            output_tokens=80,
        ),
        _make_response(
            [_tool_use_block("submit_verdict", _valid_verdict_input(), block_id="t2")],
            stop_reason="tool_use",
            input_tokens=420,
            output_tokens=60,
        ),
    ])

    from investigator.tools import TOOL_RUNNERS

    real_lookup = TOOL_RUNNERS["lookup_itunes"]
    TOOL_RUNNERS["lookup_itunes"] = lambda **_: {"found": False}
    try:
        result = investigate("X", client=client)
    finally:
        TOOL_RUNNERS["lookup_itunes"] = real_lookup

    assert result.budget.iterations == 2
    assert result.budget.input_tokens == 720
    assert result.budget.output_tokens == 140

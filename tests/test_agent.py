"""Tests for the agent tool-use loop.

Strategy: stub the Anthropic client to return scripted `Message` objects that
exercise each loop branch (tool call → result → next iteration; submit_verdict
terminal; end_turn without verdict; budget exhaustion).

All three test_budget_* tests below are pure-Python and can run today against
the implemented `Budget` class. The loop tests are skipped until Phase 2.
"""

from __future__ import annotations

import pytest

from investigator.budget import Budget


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
    # $1/MTok input
    assert abs(b.usd_spent - 1.0) < 1e-6


def test_budget_iterations_cap() -> None:
    b = Budget(max_iterations=2)
    b.charge({"input_tokens": 1, "output_tokens": 1})
    b.charge({"input_tokens": 1, "output_tokens": 1})
    assert not b.has_remaining()
    assert b.exhaustion_reason == "max_iterations"


def test_budget_usd_cap() -> None:
    b = Budget(max_usd=0.5)
    # 500k input tokens at $1/MTok = $0.50 — triggers cap.
    b.charge({"input_tokens": 500_000, "output_tokens": 0})
    assert not b.has_remaining()
    assert b.exhaustion_reason == "max_usd"


def test_budget_vision_pass_cap() -> None:
    b = Budget(max_vision_passes=1)
    assert b.can_use_vision()
    b.record_vision_pass()
    assert not b.can_use_vision()


@pytest.mark.skip(reason="Phase 2 — implement agent.investigate() then enable.")
def test_agent_terminates_on_submit_verdict() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Phase 2 — implement agent.investigate() then enable.")
def test_agent_terminates_on_budget_exhaustion() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Phase 2 — implement agent.investigate() then enable.")
def test_agent_executes_requested_tools() -> None:
    raise NotImplementedError

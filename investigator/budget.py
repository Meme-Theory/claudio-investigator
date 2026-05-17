"""Per-investigation budget enforcement.

Three independent caps, any one of which terminates the loop:
  - iterations (number of Claude API round-trips)
  - total tokens (input + output, summed across iterations)
  - USD spent (computed from token usage at Haiku 4.5 pricing)

`charge` is called after every Claude response; `has_remaining` is checked
before the next round-trip. The agent loop must respect both signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Haiku 4.5 pricing as of 2025-10 — source of truth: https://www.anthropic.com/pricing
# If pricing changes, update here. Cache-write/cache-read have their own rates and
# should be priced from the same source when prompt caching is wired in.
HAIKU_4_5_INPUT_USD_PER_MTOK = 1.0
HAIKU_4_5_OUTPUT_USD_PER_MTOK = 5.0
HAIKU_4_5_CACHE_READ_USD_PER_MTOK = 0.10
HAIKU_4_5_CACHE_WRITE_USD_PER_MTOK = 1.25


@dataclass
class Budget:
    """Mutable counters; instantiate one per investigation."""

    max_iterations: int = 12
    max_tokens_total: int = 20_000
    max_usd: float = 0.50

    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    usd_spent: float = 0.0

    exhaustion_reason: str | None = None

    # Tracked outside token/USD caps but enforced by the agent.
    vision_passes_used: int = 0
    max_vision_passes: int = 2

    notes: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def has_remaining(self) -> bool:
        """True iff none of the caps have been hit. Sets `exhaustion_reason` on False."""
        if self.iterations >= self.max_iterations:
            self.exhaustion_reason = "max_iterations"
            return False
        if self.total_tokens >= self.max_tokens_total:
            self.exhaustion_reason = "max_tokens"
            return False
        if self.usd_spent >= self.max_usd:
            self.exhaustion_reason = "max_usd"
            return False
        return True

    def charge(self, usage: Any) -> None:
        """Increment counters from one Anthropic `Usage` object.

        Accepts either the SDK's typed Usage or a plain dict — both are duck-typed.
        Unknown fields are tolerated (forward-compat for new usage subfields).
        """
        self.iterations += 1

        def _g(key: str) -> int:
            if isinstance(usage, dict):
                return int(usage.get(key) or 0)
            return int(getattr(usage, key, 0) or 0)

        in_tok = _g("input_tokens")
        out_tok = _g("output_tokens")
        cache_read = _g("cache_read_input_tokens")
        cache_write = _g("cache_creation_input_tokens")

        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.cache_read_tokens += cache_read
        self.cache_creation_tokens += cache_write

        self.usd_spent += (
            in_tok * HAIKU_4_5_INPUT_USD_PER_MTOK / 1_000_000
            + out_tok * HAIKU_4_5_OUTPUT_USD_PER_MTOK / 1_000_000
            + cache_read * HAIKU_4_5_CACHE_READ_USD_PER_MTOK / 1_000_000
            + cache_write * HAIKU_4_5_CACHE_WRITE_USD_PER_MTOK / 1_000_000
        )

    def can_use_vision(self) -> bool:
        return self.vision_passes_used < self.max_vision_passes

    def record_vision_pass(self) -> None:
        self.vision_passes_used += 1

    def summary(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "total_tokens": self.total_tokens,
            "usd_spent": round(self.usd_spent, 4),
            "vision_passes_used": self.vision_passes_used,
            "exhaustion_reason": self.exhaustion_reason,
        }

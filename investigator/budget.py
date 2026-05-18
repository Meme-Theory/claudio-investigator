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

# Pricing as of 2026-05 — source of truth: https://claude.com/pricing
# Cache-write multiplier is 1.25x base input, cache-read is 0.1x base input
# (5-minute cache; 1h cache would be 2x but we don't use it).
HAIKU_4_5_INPUT_USD_PER_MTOK = 1.0
HAIKU_4_5_OUTPUT_USD_PER_MTOK = 5.0
HAIKU_4_5_CACHE_READ_USD_PER_MTOK = 0.10
HAIKU_4_5_CACHE_WRITE_USD_PER_MTOK = 1.25

# Sonnet 4.6 is the escalation target. 5x Haiku's base rate; we only spend
# it on the hard cases where Haiku triggers request_escalation.
SONNET_4_6_INPUT_USD_PER_MTOK = 3.0
SONNET_4_6_OUTPUT_USD_PER_MTOK = 15.0
SONNET_4_6_CACHE_READ_USD_PER_MTOK = 0.30
SONNET_4_6_CACHE_WRITE_USD_PER_MTOK = 3.75


@dataclass
class Budget:
    """Mutable counters; instantiate one per investigation.

    Caps are inclusive: when an iteration is escalated to Sonnet, the
    iteration / token / USD caps are bumped by their `*_sonnet_extra` values
    rather than reset, so the combined cost ceiling is Haiku-cap +
    Sonnet-cap. usd_spent / token counters keep accumulating across the
    handover; only the rate at which they grow changes.
    """

    max_iterations: int = 12
    # 100K aligns the token cap with `max_iterations=12` given typical
    # per-iteration growth (~3–8K new tokens). The USD cap is the real
    # safety bound: at Haiku 4.5 pricing ($1/MTok input, $5/MTok output),
    # even a pathological 100K-token investigation costs ~$0.10 — 5x
    # under the $0.50 USD ceiling. Earlier defaults (20K, then 40K) were
    # conservative legacies of the dev plan's unknown cost model;
    # observed cost is $0.02–0.06 per investigation, so we can give the
    # agent more rope without practical risk.
    max_tokens_total: int = 100_000
    max_usd: float = 0.50

    # Extra headroom granted when Haiku escalates to Sonnet. Combined ceiling
    # is max_usd + sonnet_extra_usd ($1.50) and max_iterations + sonnet_extra
    # iterations (18) once escalated.
    sonnet_extra_iterations: int = 6
    sonnet_extra_tokens: int = 50_000
    sonnet_extra_usd: float = 1.00

    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    usd_spent: float = 0.0

    # Which model is being billed against right now. `charge()` applies the
    # rate table for whichever model is active. Default = Haiku; flipped to
    # "sonnet" via escalate_to_sonnet().
    active_model: str = "haiku"
    escalated: bool = False

    exhaustion_reason: str | None = None

    # Tracked outside token/USD caps but enforced by the agent.
    vision_passes_used: int = 0
    max_vision_passes: int = 2

    notes: list[str] = field(default_factory=list)

    def escalate_to_sonnet(self) -> None:
        """Switch billing to Sonnet rates and grant the additional caps.

        Idempotent — calling twice doesn't double-bump. Existing usd_spent
        and token counters are preserved; only the caps and pricing change.
        """
        if self.escalated:
            return
        self.escalated = True
        self.active_model = "sonnet"
        self.max_iterations += self.sonnet_extra_iterations
        self.max_tokens_total += self.sonnet_extra_tokens
        self.max_usd += self.sonnet_extra_usd
        self.notes.append(
            f"escalated to sonnet at iter={self.iterations}, "
            f"usd_spent={self.usd_spent:.4f}"
        )

    @property
    def total_tokens(self) -> int:
        """Tokens representing genuinely-new model work this investigation.

        Deliberately excludes `cache_read_tokens` — those are re-reads of
        content the model first processed (and that we already counted via
        `cache_creation_tokens` or `input_tokens`) on an earlier iteration.
        Counting them double-bills the same context against the iteration
        cap, causing investigations with rich tool results to trip the cap
        prematurely even when no actual runaway is happening.

        The intent of `max_tokens_total` is to bound runaway context growth,
        not to penalize the prompt cache.
        """
        return (
            self.input_tokens
            + self.output_tokens
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

        # Apply rates for whichever model is currently active. Pre-escalation
        # iterations were charged at Haiku rates; post-escalation iterations
        # are charged at Sonnet rates. Counters accumulate either way.
        if self.active_model == "sonnet":
            in_rate = SONNET_4_6_INPUT_USD_PER_MTOK
            out_rate = SONNET_4_6_OUTPUT_USD_PER_MTOK
            cr_rate = SONNET_4_6_CACHE_READ_USD_PER_MTOK
            cw_rate = SONNET_4_6_CACHE_WRITE_USD_PER_MTOK
        else:
            in_rate = HAIKU_4_5_INPUT_USD_PER_MTOK
            out_rate = HAIKU_4_5_OUTPUT_USD_PER_MTOK
            cr_rate = HAIKU_4_5_CACHE_READ_USD_PER_MTOK
            cw_rate = HAIKU_4_5_CACHE_WRITE_USD_PER_MTOK

        self.usd_spent += (
            in_tok * in_rate / 1_000_000
            + out_tok * out_rate / 1_000_000
            + cache_read * cr_rate / 1_000_000
            + cache_write * cw_rate / 1_000_000
        )

    def can_use_vision(self) -> bool:
        return self.vision_passes_used < self.max_vision_passes

    def record_vision_pass(self) -> None:
        self.vision_passes_used += 1

    def summary(self) -> dict[str, Any]:
        # cache_read_tokens is reported but NOT included in total_tokens —
        # see the docstring on `total_tokens` for the rationale.
        return {
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "total_tokens": self.total_tokens,
            "billable_tokens": (
                self.input_tokens
                + self.output_tokens
                + self.cache_read_tokens
                + self.cache_creation_tokens
            ),
            "usd_spent": round(self.usd_spent, 4),
            "vision_passes_used": self.vision_passes_used,
            "escalated": self.escalated,
            "active_model": self.active_model,
            "exhaustion_reason": self.exhaustion_reason,
        }

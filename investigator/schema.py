"""Pydantic schemas for verdicts and curated artist records.

The verdict shape is what the agent's `submit_verdict` tool produces.
The record shape is what lands in `src/{slug}.json` and what `dist/artists.json`
concatenates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VerdictLabel = Literal["ai", "likely_ai", "unclear", "likely_human", "human"]
EvidenceWeight = Literal["low", "medium", "high"]

# Confidence is a discrete 4-bucket scale (see rubric SYSTEM_PROMPT rule 0).
# The model is not calibrated well enough for a continuous 0.0-1.0 number to
# carry meaning — outputting 0.87 vs 0.92 across runs for similar evidence is
# fabrication. Enforcing the bucket set at the schema level means a verdict
# with a non-bucket value (0.80, 0.85, 0.92, etc.) gets rejected at
# Verdict() construction time and fed back through the agent's retry loop.
CONFIDENCE_BUCKETS: tuple[float, ...] = (0.50, 0.70, 0.90, 0.95)


class Evidence(BaseModel):
    """One supporting datum the agent used to reach the verdict."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="API or tool name, e.g. 'musicbrainz'")
    finding: str = Field(description="Short factual claim, written for human readers")
    weight: EvidenceWeight = "medium"


class Platforms(BaseModel):
    """Platform IDs we've identified for this artist."""

    model_config = ConfigDict(extra="forbid")

    spotify_id: str | None = None
    youtube_channel: str | None = None
    apple_id: str | None = None
    deezer_id: str | None = None
    musicbrainz_mbid: str | None = None
    discogs_id: str | None = None
    lastfm_url: str | None = None
    genius_id: str | None = None


class Verdict(BaseModel):
    """What `submit_verdict` returns — the terminal output of one investigation."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    markers: list[str] = Field(
        default_factory=list,
        description="Slugs from the signal taxonomy in docs/SIGNALS.md",
    )
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = Field(description="One paragraph, written for human readers")
    auto_merge_recommended: bool = False

    @field_validator("markers")
    @classmethod
    def _markers_lowercase_hyphen(cls, v: list[str]) -> list[str]:
        for m in v:
            if m != m.lower() or " " in m:
                raise ValueError(f"marker must be lowercase-hyphenated: {m!r}")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_in_bucket(cls, v: float) -> float:
        if v not in CONFIDENCE_BUCKETS:
            raise ValueError(
                f"confidence must be one of {CONFIDENCE_BUCKETS} "
                f"(got {v}). The model is not calibrated well enough to "
                f"distinguish intermediate values; pick a bucket — 0.50 "
                f"for toss-up/unclear, 0.70 for directional with "
                f"contradicting evidence, 0.90 for confident verdicts, "
                f"0.95 for explicit self-disclosure only."
            )
        return v


class ArtistRecord(BaseModel):
    """One curated entry written to src/{slug}.json."""

    model_config = ConfigDict(extra="forbid")

    name: str
    slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
    verdict: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    markers: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    platforms: Platforms = Field(default_factory=Platforms)
    investigated_at: datetime
    model: str = Field(description="e.g. 'claude-haiku-4-5-20251001'")
    investigation_issue: int | None = None
    reasoning: str

    @classmethod
    def from_verdict(
        cls,
        *,
        name: str,
        slug: str,
        verdict: Verdict,
        platforms: Platforms,
        model: str,
        investigation_issue: int | None,
        investigated_at: datetime,
    ) -> ArtistRecord:
        return cls(
            name=name,
            slug=slug,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            markers=verdict.markers,
            evidence=verdict.evidence,
            platforms=platforms,
            investigated_at=investigated_at,
            model=model,
            investigation_issue=investigation_issue,
            reasoning=verdict.reasoning,
        )

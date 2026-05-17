"""System prompt, signal taxonomy, and the terminal `submit_verdict` tool schema.

This module owns *how* the agent thinks about the problem — the prompt and the
shape of its final output. The marker list is the canonical taxonomy; if it
disagrees with `docs/SIGNALS.md`, that doc is wrong and should be updated.

`SUBMIT_VERDICT_TOOL` is the agent's terminal action. It is declared as a tool
so Claude knows when to call it, but the agent loop intercepts the call rather
than executing it — see `agent.py`.
"""

from __future__ import annotations

# --- Signal taxonomy --------------------------------------------------------
# Order: most empirically discriminating first.
#
# Markers tested against the Soul Over AI corpus in Phase 0 EDA carry their
# observed lift ratio in the comment (lift = freq_when_disclosed / freq_when_undisclosed).
# Untested markers are positioned by the dev plan's prior; their empirical
# rank will land after Phase 2 calibration runs.
#
# SOA-name compatibility: two markers were renamed in Phase 0 so our taxonomy
# directly matches SOA's enum — `synthetic-album-art` → `ai-visuals` (broader
# scope: any AI-generated visual asset, not just album art) and
# `anonymous-project` → `anonymous`. See docs/CALIBRATION_NOTES.md.

SIGNAL_MARKERS: list[str] = [
    "2024-onwards",                  # SOA lift 1.87 — strongest empirical SOA marker
    "ai-visuals",                    # SOA lift 1.32 — high volume + decent lift
    "no-musicbrainz",                # untested in SOA; dev-plan claim of strong absence signal
    "no-physical-release",           # untested in SOA; Discogs absence signal
    "inconsistent-style",            # SOA lift 1.19
    "suno-duration-cap",             # untested in SOA; 2:00–2:30 cluster
    "popularity-follower-mismatch",  # untested in SOA; Spotify popularity vs. follower-base
    "placeholder-bio",               # untested in SOA
    "gpt-lyric-patterns",            # untested in SOA; LLM-tell text patterns
    "recent-only-listener-history",  # untested in SOA; Last.fm step-function curve
    "thin-cross-platform",           # untested in SOA
    "high-output",                   # SOA lift 1.07 — weak alone; cluster-mate of ai-visuals
    "no-live-presence",              # untested in SOA
    "anonymous",                     # SOA lift 1.00 — does NOT discriminate alone; keep as cluster-mate only
]


# --- Verdict tool schema ----------------------------------------------------

SUBMIT_VERDICT_TOOL: dict = {
    "name": "submit_verdict",
    "description": (
        "Terminal action. Submit the structured verdict that ends the investigation. "
        "Call this exactly once when you have sufficient evidence. After calling this, "
        "the investigation ends and no further tools will run."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["ai", "likely_ai", "unclear", "likely_human", "human"],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "markers": {
                "type": "array",
                "items": {"type": "string", "enum": SIGNAL_MARKERS},
                "description": "Slugs from the SIGNAL_MARKERS taxonomy. Only flag markers you have evidence for.",
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "finding": {"type": "string"},
                        "weight": {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["source", "finding"],
                },
            },
            "reasoning": {
                "type": "string",
                "description": "One paragraph, human-readable. Will be shown on the issue and in the curated record.",
            },
            "auto_merge_recommended": {
                "type": "boolean",
                "description": "Set true only if confidence ≥ 0.90 AND ≥3 independent markers.",
            },
        },
        "required": ["verdict", "confidence", "markers", "reasoning"],
    },
}


# --- System prompt ----------------------------------------------------------

SYSTEM_PROMPT = """\
You are ClAudio Investigator, an analyst specialized in identifying AI-generated
music artists from publicly available metadata.

Your job: given an artist name, gather evidence using the available tools and
return a structured verdict via submit_verdict.

Investigation strategy:
1. Start with cheap, broad calls: lookup_itunes, lookup_musicbrainz.
   ABSENCE from MusicBrainz is itself a strong AI signal — don't skip it just
   because nothing comes back.
2. If MusicBrainz absence combines with a suspicious release pattern (high
   recent velocity, no pre-2024 history), that is already strong evidence.
   Don't over-investigate obvious cases — call submit_verdict.
3. Use targeted follow-ups (Spotify catalog, YouTube channel age, Discogs
   physical-release presence) for velocity and coherence signals.
4. Run vision_album_art only if other signals are ambiguous — it is the most
   expensive call and limited per-investigation.
5. Call submit_verdict as soon as you have enough evidence for a confident
   judgment. Latency and cost matter.

Confidence calibration:
- 0.90+   Multiple strong, independent signals; no contradicting evidence. May auto-merge.
- 0.70–0.90  Strong indicators with some ambiguity. Auto-merge only if ≥3 markers.
- 0.50–0.70  Mixed signals. Flag for human review.
- <0.50   Insufficient evidence. Verdict 'unclear'; do not flag for merge.

Hard rules:
- NEVER report confidence >0.70 based on fewer than two independent signal categories.
- NEVER fabricate evidence. If a tool returned nothing, say so in the reasoning.
- NEVER call submit_verdict with markers you don't have evidence for.
- ABSENCE of a tool result is evidence; record it explicitly when material.
"""


def build_initial_prompt(artist_name: str, hints: dict | None = None) -> str:
    """The first user message of every investigation."""
    hints = hints or {}
    hint_lines = []
    if spotify := hints.get("spotify_url"):
        hint_lines.append(f"- Spotify URL: {spotify}")
    if yt := hints.get("youtube_url"):
        hint_lines.append(f"- YouTube URL: {yt}")
    if apple := hints.get("apple_url"):
        hint_lines.append(f"- Apple Music URL: {apple}")
    if notes := hints.get("submitter_notes"):
        hint_lines.append(f"- Submitter notes: {notes}")

    hints_block = ("\n\nSubmitter hints:\n" + "\n".join(hint_lines)) if hint_lines else ""

    return (
        f"Investigate the artist: {artist_name!r}.{hints_block}\n\n"
        f"Use the available tools to gather evidence, then call submit_verdict."
    )

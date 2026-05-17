"""Tests for the rubric: signal taxonomy, prompt structure, verdict tool schema.

These are pure-Python tests with no external deps — safe to run in any env.
"""

from __future__ import annotations

from investigator.rubric import (
    SIGNAL_MARKERS,
    SUBMIT_VERDICT_TOOL,
    SYSTEM_PROMPT,
    build_initial_prompt,
)


def test_signal_markers_are_unique_and_kebab_case() -> None:
    assert len(SIGNAL_MARKERS) == len(set(SIGNAL_MARKERS)), "duplicate markers"
    for m in SIGNAL_MARKERS:
        assert m == m.lower(), f"marker not lowercase: {m}"
        assert " " not in m, f"marker has whitespace: {m}"
        assert "_" not in m, f"marker has underscore (use hyphen): {m}"


def test_submit_verdict_schema_markers_match_taxonomy() -> None:
    """If you add a marker, update both SIGNAL_MARKERS and the enum in the schema.

    This test makes that coupling explicit so neither side drifts silently.
    """
    schema_enum = SUBMIT_VERDICT_TOOL["input_schema"]["properties"]["markers"]["items"]["enum"]
    assert schema_enum == SIGNAL_MARKERS


def test_system_prompt_mentions_submit_verdict() -> None:
    assert "submit_verdict" in SYSTEM_PROMPT


def test_build_initial_prompt_includes_artist_name() -> None:
    prompt = build_initial_prompt("Kaizuken")
    assert "Kaizuken" in prompt


def test_build_initial_prompt_renders_hints() -> None:
    prompt = build_initial_prompt(
        "Echo",
        {
            "spotify_url": "https://open.spotify.com/artist/abc",
            "submitter_notes": "rapid release cadence",
        },
    )
    assert "spotify.com/artist/abc" in prompt
    assert "rapid release cadence" in prompt

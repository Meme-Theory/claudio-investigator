"""Per-source tool tests.

Pattern: each test feeds a canned HTTP response from `tests/fixtures/` to the
real tool function and asserts the normalized output. Don't mock the parsing.

Phase 1 implements the first three tools (itunes, musicbrainz, spotify); the
later sources are stubbed and these tests should be marked xfail or skipped
until their phases land.
"""

from __future__ import annotations

import pytest

from investigator.tools import TOOLS, TOOL_RUNNERS


def test_tool_registry_is_consistent() -> None:
    """Every schema has a runner; every runner has a schema. Enforced at import."""
    schema_names = {t["name"] for t in TOOLS}
    assert schema_names == set(TOOL_RUNNERS)


def test_every_tool_schema_has_required_fields() -> None:
    for tool in TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]


@pytest.mark.skip(reason="Phase 1 — implement once tools/itunes.py is real.")
def test_itunes_lookup_known_ai_artist(itunes_known_ai_response) -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Phase 1 — implement once tools/musicbrainz.py is real.")
def test_musicbrainz_absence_returns_found_false() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Phase 1 — implement once tools/spotify.py is real.")
def test_spotify_search_returns_top_matches() -> None:
    raise NotImplementedError

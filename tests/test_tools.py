"""Per-source tool tests.

Pattern: feed canned API responses from `tests/fixtures/` to the real tool
function via the `responses` library and assert the normalized output. The
parsing code runs for real; only the network is mocked.

Phases 2+ source tools (youtube, discogs, deezer, lastfm, genius, vision)
remain xfailed until their phases land.
"""

from __future__ import annotations

import json
import time

import pytest
import responses

from investigator.tools import TOOLS, TOOL_RUNNERS
from investigator.tools.itunes import LOOKUP_URL as ITUNES_LOOKUP_URL
from investigator.tools.itunes import SEARCH_URL as ITUNES_SEARCH_URL
from investigator.tools.itunes import lookup_itunes
from investigator.tools.musicbrainz import SEARCH_URL as MB_SEARCH_URL
from investigator.tools.musicbrainz import lookup_musicbrainz
from investigator.tools.spotify import (
    API_BASE as SPOTIFY_API_BASE,
)
from investigator.tools.spotify import (
    TOKEN_URL as SPOTIFY_TOKEN_URL,
)
from investigator.tools.spotify import (
    get_spotify_albums,
    get_spotify_artist,
    search_spotify_artist,
)


# --- Registry consistency ---------------------------------------------------


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


# --- iTunes ----------------------------------------------------------------


@responses.activate
def test_itunes_lookup_known_human_returns_normalized_data(load_fixture) -> None:
    responses.add(
        responses.GET, ITUNES_SEARCH_URL, json=load_fixture("itunes_search_known_human.json")
    )
    responses.add(
        responses.GET, ITUNES_LOOKUP_URL, json=load_fixture("itunes_lookup_known_human.json")
    )

    result = lookup_itunes("Aphex Twin")

    assert result["found"] is True
    assert result["canonical_name"] == "Aphex Twin"
    assert result["artist_id"] == 82636
    assert result["primary_genre"] == "Electronic"
    assert result["album_count"] == 2
    assert result["earliest_release_date"].startswith("1992-")
    assert result["latest_release_date"].startswith("2001-")
    assert all("name" in a for a in result["albums"])


@responses.activate
def test_itunes_lookup_returns_not_found_on_empty(load_fixture) -> None:
    responses.add(responses.GET, ITUNES_SEARCH_URL, json=load_fixture("itunes_search_empty.json"))

    result = lookup_itunes("Nonexistent Artist 12345")

    assert result["found"] is False
    assert result["query"] == "Nonexistent Artist 12345"


@responses.activate
def test_itunes_lookup_known_ai_surfaces_2025_only_catalog(load_fixture) -> None:
    """Smoke test that the canonical AI-shape fixture parses into a 2025-onwards catalog."""
    responses.add(
        responses.GET, ITUNES_SEARCH_URL, json=load_fixture("itunes_search_known_ai.json")
    )
    responses.add(
        responses.GET, ITUNES_LOOKUP_URL, json=load_fixture("itunes_lookup_known_ai.json")
    )

    result = lookup_itunes("Synthwave Phantom")

    assert result["found"] is True
    assert result["earliest_release_date"].startswith("2025-")
    # Four albums in 2025 — fits the high-output pattern the rubric flags
    assert result["album_count"] == 4


# --- MusicBrainz -----------------------------------------------------------


@responses.activate
def test_musicbrainz_exact_match_for_known_artist(load_fixture) -> None:
    responses.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_found.json"))

    result = lookup_musicbrainz("Aphex Twin")

    assert result["found"] is True
    assert result["found_exact"] is True
    assert result["exact_match"]["mbid"] == "f27ec8db-af05-4f36-916e-3d57f91ecf5e"
    assert result["exact_match"]["country"] == "GB"
    assert "AFX" in result["exact_match"]["aliases"]


@responses.activate
def test_musicbrainz_absence_returns_found_false(load_fixture) -> None:
    responses.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_empty.json"))

    result = lookup_musicbrainz("Synthwave Phantom")

    assert result["found"] is False
    assert result["found_exact"] is False
    assert result["candidates"] == []
    assert result["exact_match"] is None


@responses.activate
def test_musicbrainz_loose_match_no_exact(load_fixture) -> None:
    """Score-80 candidate exists but no exact-name match → found=True, found_exact=False."""
    responses.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_loose_match.json"))

    result = lookup_musicbrainz("Synthwave Phantom")

    assert result["found"] is True
    assert result["found_exact"] is False
    assert result["exact_match"] is None
    assert len(result["candidates"]) == 2


def test_musicbrainz_rate_limit_floor_enforced(load_fixture) -> None:
    """Two consecutive calls must take at least 1 second total (1 req/sec limit)."""
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_empty.json"))
        rsps.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_empty.json"))
        start = time.monotonic()
        lookup_musicbrainz("a")
        lookup_musicbrainz("b")
        elapsed = time.monotonic() - start
    assert elapsed >= 1.0, f"expected ≥1s between calls, got {elapsed:.3f}s"


# --- Spotify ---------------------------------------------------------------


@responses.activate
def test_spotify_search_returns_top_matches(load_fixture, fake_spotify_env) -> None:
    responses.add(responses.POST, SPOTIFY_TOKEN_URL, json=load_fixture("spotify_token.json"))
    responses.add(
        responses.GET, f"{SPOTIFY_API_BASE}/search", json=load_fixture("spotify_search.json")
    )

    result = search_spotify_artist("Aphex Twin")

    assert result["found"] is True
    assert result["found_exact"] is True
    assert result["exact_match"]["id"] == "6kBDZFXuLrZgHnvmPu9NsG"
    assert result["exact_match"]["popularity"] == 72
    assert result["exact_match"]["followers_count"] == 1487412


@responses.activate
def test_spotify_get_artist(load_fixture, fake_spotify_env) -> None:
    responses.add(responses.POST, SPOTIFY_TOKEN_URL, json=load_fixture("spotify_token.json"))
    responses.add(
        responses.GET,
        f"{SPOTIFY_API_BASE}/artists/6kBDZFXuLrZgHnvmPu9NsG",
        json=load_fixture("spotify_artist.json"),
    )

    result = get_spotify_artist("6kBDZFXuLrZgHnvmPu9NsG")

    assert result["id"] == "6kBDZFXuLrZgHnvmPu9NsG"
    assert result["name"] == "Aphex Twin"
    assert result["popularity"] == 72
    assert result["followers_count"] == 1487412
    assert "electronic" in result["genres"]


@responses.activate
def test_spotify_get_albums(load_fixture, fake_spotify_env) -> None:
    responses.add(responses.POST, SPOTIFY_TOKEN_URL, json=load_fixture("spotify_token.json"))
    responses.add(
        responses.GET,
        f"{SPOTIFY_API_BASE}/artists/6kBDZFXuLrZgHnvmPu9NsG/albums",
        json=load_fixture("spotify_albums.json"),
    )

    result = get_spotify_albums("6kBDZFXuLrZgHnvmPu9NsG")

    assert result["album_count"] == 2
    assert result["earliest_release_date"] == "1992-11-09"
    assert result["latest_release_date"] == "2001-10-22"


@responses.activate
def test_spotify_token_cached_across_calls(load_fixture, fake_spotify_env) -> None:
    """Two API calls should auth once (token cached), not twice."""
    responses.add(responses.POST, SPOTIFY_TOKEN_URL, json=load_fixture("spotify_token.json"))
    responses.add(
        responses.GET, f"{SPOTIFY_API_BASE}/search", json=load_fixture("spotify_search.json")
    )
    responses.add(
        responses.GET,
        f"{SPOTIFY_API_BASE}/artists/6kBDZFXuLrZgHnvmPu9NsG",
        json=load_fixture("spotify_artist.json"),
    )

    search_spotify_artist("Aphex Twin")
    get_spotify_artist("6kBDZFXuLrZgHnvmPu9NsG")

    # responses.calls includes every request made through the mocked session.
    token_calls = [c for c in responses.calls if c.request.url == SPOTIFY_TOKEN_URL]
    assert len(token_calls) == 1, f"expected 1 token request, got {len(token_calls)}"


def test_spotify_missing_credentials_raises(monkeypatch) -> None:
    """No env vars → clear error rather than mysterious 401 at the API."""
    from investigator.tools.spotify import _reset_token_cache_for_testing

    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    _reset_token_cache_for_testing()
    with pytest.raises(RuntimeError, match="SPOTIFY_CLIENT_ID"):
        search_spotify_artist("anything")


# --- Phase 2+ tools (still scaffolded) -------------------------------------


@pytest.mark.skip(reason="Phase 2 — tools/youtube.py is still scaffolded.")
def test_youtube_channel_lookup() -> None:
    raise NotImplementedError


@pytest.mark.skip(reason="Phase 2 — tools/discogs.py is still scaffolded.")
def test_discogs_lookup() -> None:
    raise NotImplementedError

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
from investigator.tools.musicbrainz import ARTIST_URL as MB_ARTIST_URL
from investigator.tools.musicbrainz import SEARCH_URL as MB_SEARCH_URL
from investigator.tools.musicbrainz import lookup_musicbrainz
from investigator.tools.deezer import ARTIST_TOP_URL as DEEZER_TOP_URL
from investigator.tools.deezer import SEARCH_URL as DEEZER_SEARCH_URL
from investigator.tools.deezer import lookup_deezer
from investigator.tools.discogs import ARTIST_URL as DISCOGS_ARTIST_URL
from investigator.tools.discogs import SEARCH_URL as DISCOGS_SEARCH_URL
from investigator.tools.discogs import lookup_discogs
from investigator.tools.genius import (
    ARTISTS_URL as GENIUS_ARTISTS_URL,
)
from investigator.tools.genius import (
    SEARCH_URL as GENIUS_SEARCH_URL,
)
from investigator.tools.genius import (
    get_genius_lyrics,
)
from investigator.tools.lastfm import API_URL as LASTFM_API_URL
from investigator.tools.lastfm import get_lastfm_artist
from investigator.tools.youtube import (
    CHANNELS_URL as YOUTUBE_CHANNELS_URL,
)
from investigator.tools.youtube import (
    PLAYLIST_ITEMS_URL as YOUTUBE_PLAYLIST_URL,
)
from investigator.tools.youtube import (
    SEARCH_URL as YOUTUBE_SEARCH_URL,
)
from investigator.tools.youtube import (
    VIDEOS_URL as YOUTUBE_VIDEOS_URL,
)
from investigator.tools.youtube import (
    _parse_iso_duration,
    get_youtube_channel,
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
    assert result["albums_truncated"] is False  # 4 < 15 sample limit


@responses.activate
def test_itunes_lookup_truncates_huge_catalog_with_histogram(load_fixture) -> None:
    """22-album AI catalog must truncate to the sample limit and surface a year histogram."""
    responses.add(responses.GET, ITUNES_SEARCH_URL, json=load_fixture("itunes_search_known_ai.json"))
    responses.add(responses.GET, ITUNES_LOOKUP_URL, json=load_fixture("itunes_lookup_huge_catalog.json"))

    result = lookup_itunes("Phantom Catalog")

    assert result["found"] is True
    assert result["album_count"] == 22
    assert result["albums_truncated"] is True
    assert result["albums_returned"] == 15  # ALBUM_SAMPLE_LIMIT
    assert len(result["albums"]) == 15
    # Histogram captures ALL releases by year, including the 21 truncated ones.
    histogram = result["release_year_histogram"]
    assert histogram.get("2025") == 21
    assert histogram.get("2024") == 1
    # Most-recent-first ordering
    sample_dates = [a["release_date"] for a in result["albums"]]
    assert sample_dates == sorted(sample_dates, reverse=True)


# --- MusicBrainz -----------------------------------------------------------


@responses.activate
def test_musicbrainz_exact_match_classifies_full_entry(load_fixture) -> None:
    """Real human artist with type/country/ISNI/relations → entry_quality=full."""
    responses.add(responses.GET, MB_SEARCH_URL, json=load_fixture("musicbrainz_found.json"))
    responses.add(
        responses.GET,
        f"{MB_ARTIST_URL}/f27ec8db-af05-4f36-916e-3d57f91ecf5e",
        json=load_fixture("musicbrainz_artist_full.json"),
    )

    result = lookup_musicbrainz("Aphex Twin")

    assert result["found"] is True
    assert result["found_exact"] is True
    em = result["exact_match"]
    assert em["mbid"] == "f27ec8db-af05-4f36-916e-3d57f91ecf5e"
    assert em["country"] == "GB"
    assert em["type"] == "Person"
    assert em["isni_count"] == 1
    assert em["life_span_begin"] == "1985"
    assert em["entry_quality"] == "full"
    # Meaningful relations (everything that isn't auto-import streaming).
    assert em["relation_count_meaningful"] >= 3
    assert "official homepage" in em["relation_types"]
    assert "wikipedia" in em["relation_types"]


@responses.activate
def test_musicbrainz_exact_match_classifies_stub(load_fixture) -> None:
    """Auto-imported distributor stub (no type/country/ISNI, only streaming
    URL relations) → entry_quality=stub. This is what AI artists look like
    in MB when distributors auto-submit their streaming presence."""
    responses.add(responses.GET, MB_SEARCH_URL, json={
        "created": "2026-05-17T15:00:00.000Z",
        "count": 1,
        "offset": 0,
        "artists": [{
            "id": "c4732cad-0916-4629-90ec-12b563180aed",
            "score": 100,
            "name": "Fall To Pieces",
            "sort-name": "Fall To Pieces",
        }],
    })
    responses.add(
        responses.GET,
        f"{MB_ARTIST_URL}/c4732cad-0916-4629-90ec-12b563180aed",
        json=load_fixture("musicbrainz_artist_stub.json"),
    )

    result = lookup_musicbrainz("Fall To Pieces")

    assert result["found"] is True
    assert result["found_exact"] is True
    em = result["exact_match"]
    assert em["type"] is None
    assert em["country"] is None
    assert em["isni_count"] == 0
    assert em["relation_count"] == 4
    assert em["relation_count_meaningful"] == 0   # all 4 are auto-import streaming
    assert em["entry_quality"] == "stub"


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


# --- YouTube --------------------------------------------------------------


@pytest.fixture
def fake_youtube_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-yt-key")


@responses.activate
def test_youtube_channel_by_id(load_fixture, fake_youtube_env) -> None:
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_by_id.json")
    )
    responses.add(
        responses.GET, YOUTUBE_PLAYLIST_URL, json=load_fixture("youtube_uploads_playlist.json")
    )
    responses.add(
        responses.GET, YOUTUBE_VIDEOS_URL, json=load_fixture("youtube_video_durations.json")
    )

    result = get_youtube_channel("UCQpsLlpUlsdkRoZyaSwUTuw")

    assert result["found"] is True
    assert result["resolved_via"] == "id"
    assert result["channel_id"] == "UCQpsLlpUlsdkRoZyaSwUTuw"
    assert result["title"] == "Aphex Twin"
    assert result["country"] == "GB"
    assert result["subscriber_count"] == 612000
    assert result["video_count"] == 47
    assert result["recent_uploads_sampled"] == 3
    assert result["recent_uploads_earliest"].startswith("2017-")
    assert result["recent_uploads_latest"].startswith("2024-")
    # Durations should be parsed into seconds for each recent upload —
    # feeds the suno-duration-cap marker as a secondary source.
    durations = {v["video_id"]: v["duration_seconds"] for v in result["recent_uploads"]}
    assert durations["vid_aisatsana_001"] == 322   # PT5M22S
    assert durations["vid_diskprep_002"] == 227    # PT3M47S
    assert durations["vid_fieldday_003"] == 4325   # PT1H12M5S


def test_parse_iso_duration() -> None:
    """Unit-test the ISO 8601 → seconds parser directly."""
    assert _parse_iso_duration("PT3M42S") == 222
    assert _parse_iso_duration("PT2M") == 120
    assert _parse_iso_duration("PT45S") == 45
    assert _parse_iso_duration("PT1H2M3S") == 3723
    assert _parse_iso_duration("PT0S") == 0
    assert _parse_iso_duration(None) is None
    assert _parse_iso_duration("") is None
    assert _parse_iso_duration("garbage") is None


@responses.activate
def test_youtube_channel_by_handle(load_fixture, fake_youtube_env) -> None:
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_by_handle.json")
    )
    responses.add(
        responses.GET, YOUTUBE_PLAYLIST_URL, json=load_fixture("youtube_uploads_playlist.json")
    )

    result = get_youtube_channel("@AphexTwin")

    assert result["found"] is True
    assert result["resolved_via"] == "handle"
    assert result["channel_id"] == "UCQpsLlpUlsdkRoZyaSwUTuw"


@responses.activate
def test_youtube_channel_by_url(load_fixture, fake_youtube_env) -> None:
    """A youtube.com URL containing a channel ID should extract it without a search call."""
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_by_id.json")
    )
    responses.add(
        responses.GET, YOUTUBE_PLAYLIST_URL, json=load_fixture("youtube_uploads_playlist.json")
    )

    result = get_youtube_channel(
        "https://www.youtube.com/channel/UCQpsLlpUlsdkRoZyaSwUTuw/about"
    )

    assert result["found"] is True
    assert result["resolved_via"] == "id"


@responses.activate
def test_youtube_channel_by_search_fallback(load_fixture, fake_youtube_env) -> None:
    """Arbitrary text input → search.list → channels.list (more quota)."""
    responses.add(
        responses.GET, YOUTUBE_SEARCH_URL, json=load_fixture("youtube_search_channels.json")
    )
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_by_id.json")
    )
    responses.add(
        responses.GET, YOUTUBE_PLAYLIST_URL, json=load_fixture("youtube_uploads_playlist.json")
    )

    result = get_youtube_channel("Aphex Twin")

    assert result["found"] is True
    assert result["resolved_via"] == "search"
    assert result["channel_id"] == "UCQpsLlpUlsdkRoZyaSwUTuw"


@responses.activate
def test_youtube_search_returns_no_match(load_fixture, fake_youtube_env) -> None:
    responses.add(
        responses.GET, YOUTUBE_SEARCH_URL, json=load_fixture("youtube_search_empty.json")
    )

    result = get_youtube_channel("Some Nonexistent Artist 998")

    assert result["found"] is False


@responses.activate
def test_youtube_channel_not_found_by_handle(load_fixture, fake_youtube_env) -> None:
    """forHandle lookup that returns no items → found=false (no search fallback)."""
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_empty.json")
    )

    result = get_youtube_channel("@nonexistent")

    assert result["found"] is False
    assert result["resolved_via"] == "handle"


@responses.activate
def test_youtube_playlist_fetch_failure_doesnt_kill_lookup(
    load_fixture, fake_youtube_env
) -> None:
    """If playlistItems errors, channel lookup still succeeds with empty uploads."""
    responses.add(
        responses.GET, YOUTUBE_CHANNELS_URL, json=load_fixture("youtube_channel_by_id.json")
    )
    responses.add(responses.GET, YOUTUBE_PLAYLIST_URL, status=500)

    result = get_youtube_channel("UCQpsLlpUlsdkRoZyaSwUTuw")

    assert result["found"] is True
    assert result["recent_uploads_sampled"] == 0
    assert result["subscriber_count"] == 612000


def test_youtube_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="YOUTUBE_API_KEY"):
        get_youtube_channel("UCQpsLlpUlsdkRoZyaSwUTuw")


# --- Genius ---------------------------------------------------------------


@pytest.fixture
def fake_genius_env(monkeypatch):
    monkeypatch.setenv("GENIUS_TOKEN", "test-genius-token")


@responses.activate
def test_genius_finds_artist_and_returns_top_songs(load_fixture, fake_genius_env) -> None:
    responses.add(responses.GET, GENIUS_SEARCH_URL, json=load_fixture("genius_search.json"))
    responses.add(
        responses.GET,
        f"{GENIUS_ARTISTS_URL}/47831/songs",
        json=load_fixture("genius_artist_songs.json"),
    )

    result = get_genius_lyrics("Aphex Twin", max_tracks=3)

    assert result["found"] is True
    assert result["artist_id"] == 47831
    assert result["artist_name"] == "Aphex Twin"
    assert result["song_count_returned"] == 3
    assert result["songs"][0]["title"] == "Windowlicker"
    assert result["songs"][0]["pageviews"] == 184321
    # Sanity: the documented limitation about lyric text is surfaced
    assert "lyric text" in result["note"].lower()


@responses.activate
def test_genius_no_hits_returns_not_found(load_fixture, fake_genius_env) -> None:
    responses.add(responses.GET, GENIUS_SEARCH_URL, json=load_fixture("genius_empty_search.json"))

    result = get_genius_lyrics("Synthwave Phantom 998")

    assert result["found"] is False
    assert "no search hits" in result["reason"]


def test_genius_missing_token_raises(monkeypatch) -> None:
    monkeypatch.delenv("GENIUS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GENIUS_TOKEN"):
        get_genius_lyrics("Anything")


# --- Deezer ----------------------------------------------------------------


@responses.activate
def test_deezer_finds_artist(load_fixture) -> None:
    responses.add(responses.GET, DEEZER_SEARCH_URL, json=load_fixture("deezer_found.json"))
    responses.add(
        responses.GET,
        DEEZER_TOP_URL.format(id=27),
        json=load_fixture("deezer_top_tracks.json"),
    )

    result = lookup_deezer("Daft Punk")

    assert result["found"] is True
    assert result["found_exact"] is True
    assert result["exact_match"]["id"] == 27
    assert result["exact_match"]["nb_fan"] == 5847234
    # Top tracks should be fetched for an exact match — durations feed
    # the suno-duration-cap marker, so the shape must include them.
    assert len(result["top_tracks"]) == 3
    assert result["top_tracks"][0]["title"] == "One More Time"
    assert result["top_tracks"][0]["duration_seconds"] == 320


@responses.activate
def test_deezer_top_tracks_failure_is_tolerated(load_fixture) -> None:
    """Top-tracks fetch failures should NOT sink the lookup itself.

    Fan-count is the primary signal from this tool; durations are secondary.
    A 5xx on /artist/{id}/top must leave the search result intact with
    `top_tracks: []` so the agent can still use the fan-count signal.
    """
    responses.add(responses.GET, DEEZER_SEARCH_URL, json=load_fixture("deezer_found.json"))
    responses.add(responses.GET, DEEZER_TOP_URL.format(id=27), status=500)

    result = lookup_deezer("Daft Punk")

    assert result["found_exact"] is True
    assert result["exact_match"]["nb_fan"] == 5847234
    assert result["top_tracks"] == []


@responses.activate
def test_deezer_no_matches(load_fixture) -> None:
    responses.add(responses.GET, DEEZER_SEARCH_URL, json=load_fixture("deezer_empty.json"))

    result = lookup_deezer("Nonexistent Synthwave 998")

    assert result["found"] is False
    assert result["candidates"] == []


# --- Discogs --------------------------------------------------------------


@pytest.fixture
def fake_discogs_env(monkeypatch):
    monkeypatch.setenv("DISCOGS_TOKEN", "test-discogs-token")


@responses.activate
def test_discogs_classifies_physical_releases(load_fixture, fake_discogs_env) -> None:
    responses.add(responses.GET, DISCOGS_SEARCH_URL, json=load_fixture("discogs_search.json"))
    responses.add(
        responses.GET,
        f"{DISCOGS_ARTIST_URL}/45/releases",
        json=load_fixture("discogs_releases_mixed.json"),
    )

    result = lookup_discogs("Aphex Twin")

    assert result["found"] is True
    assert result["has_physical_release"] is True
    # 3 vinyl/CD releases + 1 File/MP3 release in the fixture
    assert result["physical_release_count"] == 3
    assert result["digital_only_release_count"] == 1
    assert result["release_count"] == 4


@responses.activate
def test_discogs_flags_digital_only_catalog(load_fixture, fake_discogs_env) -> None:
    """The 'no-physical-release' shape: artist on Discogs but all digital."""
    responses.add(responses.GET, DISCOGS_SEARCH_URL, json={
        "pagination": {"per_page": 5, "items": 1, "page": 1, "pages": 1},
        "results": [{
            "id": 9001,
            "type": "artist",
            "title": "Synthwave Phantom",
            "uri": "/artist/9001",
            "resource_url": "..."
        }],
    })
    responses.add(
        responses.GET,
        f"{DISCOGS_ARTIST_URL}/9001/releases",
        json=load_fixture("discogs_releases_digital_only.json"),
    )

    result = lookup_discogs("Synthwave Phantom")

    assert result["found"] is True
    assert result["has_physical_release"] is False
    assert result["physical_release_count"] == 0
    assert result["digital_only_release_count"] == 3


@responses.activate
def test_discogs_no_match(load_fixture, fake_discogs_env) -> None:
    responses.add(responses.GET, DISCOGS_SEARCH_URL, json=load_fixture("discogs_empty_search.json"))

    result = lookup_discogs("Some Nonexistent Artist 998")

    assert result["found"] is False


def test_discogs_missing_token_raises(monkeypatch) -> None:
    monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCOGS_TOKEN"):
        lookup_discogs("anything")


# --- Last.fm --------------------------------------------------------------


@pytest.fixture
def fake_lastfm_env(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "test-lastfm-key")


@responses.activate
def test_lastfm_artist_info(load_fixture, fake_lastfm_env) -> None:
    responses.add(responses.GET, LASTFM_API_URL, json=load_fixture("lastfm_artist_found.json"))

    result = get_lastfm_artist("Aphex Twin")

    assert result["found"] is True
    assert result["name"] == "Aphex Twin"
    assert result["listeners"] == 1487412
    assert result["playcount"] == 62841593
    assert result["playcount_per_listener"] > 40  # heavy replay = engaged audience
    assert "electronic" in result["tags"]
    assert result["ai_tag_present"] is False
    assert result["bio_present"] is True


@responses.activate
def test_lastfm_ai_tag_detection(load_fixture, fake_lastfm_env) -> None:
    """Last.fm community tags like 'ai music' / 'suno' should surface as a flag."""
    responses.add(responses.GET, LASTFM_API_URL, json=load_fixture("lastfm_artist_ai_tagged.json"))

    result = get_lastfm_artist("Synthwave Phantom")

    assert result["found"] is True
    assert result["ai_tag_present"] is True
    assert "ai music" in result["tags"]


@responses.activate
def test_lastfm_artist_not_found(load_fixture, fake_lastfm_env) -> None:
    responses.add(responses.GET, LASTFM_API_URL, json=load_fixture("lastfm_artist_not_found.json"))

    result = get_lastfm_artist("Nonexistent")

    assert result["found"] is False


def test_lastfm_missing_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LASTFM_API_KEY"):
        get_lastfm_artist("anything")



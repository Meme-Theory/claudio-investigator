"""Deezer Public API — no auth, ~50 req per 5 seconds.

Docs: https://developers.deezer.com/api

Lightweight cross-platform presence check + the project's primary
track-duration source (post-Spotify-removal, 2026-05-18). Useful because:
  - It's the only un-gated source for fan-count signal (Last.fm paywalls
    listener counts behind keys; Spotify is gone).
  - Top-tracks endpoint returns clean audio-track durations in seconds,
    feeding the `suno-duration-cap` marker without needing YouTube
    video-duration deconfliction.
  - Absence from Deezer is a (weak) hint the artist isn't going through a
    full-funnel distributor.

Returns search candidates + an "exact match" flag + top-track durations
for the exact match (when one exists).
"""

from __future__ import annotations

from typing import Any

from ._http import get_json, make_session

SEARCH_URL = "https://api.deezer.com/search/artist"
ARTIST_TOP_URL = "https://api.deezer.com/artist/{id}/top"
TOP_TRACKS_LIMIT = 10


TOOLS = [
    {
        "name": "lookup_deezer",
        "description": (
            "Search Deezer for an artist. Returns existence, fan count, album "
            "coverage, Deezer ID, and (for an exact-name match) the artist's "
            "top tracks with audio durations in seconds. Track durations feed "
            "the `suno-duration-cap` marker — a catalog clustering in the "
            "2:00–2:30 range is the Suno free-tier signature."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def _normalize_candidate(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "link": entry.get("link"),
        "nb_fan": entry.get("nb_fan"),
        "nb_album": entry.get("nb_album"),
        "picture": entry.get("picture_medium") or entry.get("picture"),
    }


def _normalize_track(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "duration_seconds": entry.get("duration"),
        "rank": entry.get("rank"),
        "explicit_lyrics": entry.get("explicit_lyrics"),
    }


def _fetch_top_tracks(session, artist_id: int | str) -> list[dict]:
    """Pull the artist's top N tracks with durations. Returns [] on failure."""
    try:
        payload = get_json(
            session,
            ARTIST_TOP_URL.format(id=artist_id),
            params={"limit": TOP_TRACKS_LIMIT},
        )
    except Exception:
        # Top-tracks is best-effort — fan-count/album-count is the primary
        # signal from this tool. Don't fail the whole lookup if /top trips.
        return []
    return [_normalize_track(t) for t in (payload.get("data") or [])]


def lookup_deezer(artist_name: str, **_: Any) -> dict:
    session = make_session()
    payload = get_json(session, SEARCH_URL, params={"q": artist_name, "limit": 5})
    items = payload.get("data") or []
    candidates = [_normalize_candidate(a) for a in items]

    query_normalized = artist_name.strip().casefold()
    exact = [c for c in candidates if (c.get("name") or "").strip().casefold() == query_normalized]

    # Only fetch top tracks for an exact-name match — pulling them for every
    # candidate would explode API calls on ambiguous searches, and the duration
    # signal is only useful when we're confident which artist we're looking at.
    top_tracks: list[dict] = []
    if exact:
        top_tracks = _fetch_top_tracks(session, exact[0]["id"])

    return {
        "query": artist_name,
        "found": bool(candidates),
        "found_exact": bool(exact),
        "total_count": payload.get("total", len(candidates)),
        "candidates": candidates,
        "exact_match": exact[0] if exact else None,
        "top_tracks": top_tracks,
    }


RUNNERS = {"lookup_deezer": lookup_deezer}

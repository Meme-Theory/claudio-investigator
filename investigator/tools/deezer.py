"""Deezer Public API — no auth, ~50 req per 5 seconds.

Docs: https://developers.deezer.com/api

Lightweight cross-platform presence check. Useful because:
  - It's the only un-gated source for fan-count signal (Last.fm and Spotify
    paywall this behind keys).
  - Absence from Deezer is a (weak) hint that the artist isn't going through
    a full-funnel distributor — AI projects tend to ship Spotify-only.

Returns search candidates + an "exact match" flag, same shape as the other
search tools.
"""

from __future__ import annotations

from typing import Any

from ._http import get_json, make_session

SEARCH_URL = "https://api.deezer.com/search/artist"


TOOLS = [
    {
        "name": "lookup_deezer",
        "description": (
            "Search Deezer for an artist. Returns existence, fan count, album "
            "coverage, and Deezer ID. Useful as a cross-platform presence check "
            "— AI artists distributed via a single channel may be absent here."
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


def lookup_deezer(artist_name: str, **_: Any) -> dict:
    session = make_session()
    payload = get_json(session, SEARCH_URL, params={"q": artist_name, "limit": 5})
    items = payload.get("data") or []
    candidates = [_normalize_candidate(a) for a in items]

    query_normalized = artist_name.strip().casefold()
    exact = [c for c in candidates if (c.get("name") or "").strip().casefold() == query_normalized]

    return {
        "query": artist_name,
        "found": bool(candidates),
        "found_exact": bool(exact),
        "total_count": payload.get("total", len(candidates)),
        "candidates": candidates,
        "exact_match": exact[0] if exact else None,
    }


RUNNERS = {"lookup_deezer": lookup_deezer}

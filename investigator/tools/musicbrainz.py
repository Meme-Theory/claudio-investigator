"""MusicBrainz API — no auth required, but UA mandatory; 1 req/sec hard limit.

Docs: https://musicbrainz.org/doc/MusicBrainz_API

ABSENCE from MusicBrainz is one of our strongest AI signals — most real
artists have an entry, most AI music projects don't. The agent should always
check MusicBrainz, even when other signals are already pointing one way.

We surface two distinct flags so the agent can reason about partial matches:
  - `found_exact`: case-insensitive exact name match in the top results
  - `found`: at least one candidate scored >= 75 (loose match)

Both being false is the "no-musicbrainz" signal. `found_exact=false` with
`found=true` means MusicBrainz has *something* similar but not the same name —
report this honestly and let the model decide whether it's the right artist.
"""

from __future__ import annotations

from typing import Any

from ._http import get_json, make_session, rate_limited

SEARCH_URL = "https://musicbrainz.org/ws/2/artist"
LOOSE_MATCH_SCORE = 75  # MusicBrainz solr scores; their docs use this as a rough threshold

TOOLS = [
    {
        "name": "lookup_musicbrainz",
        "description": (
            "Search MusicBrainz for an artist. Returns whether the artist has an entry, "
            "their MBID if so, relationships, and label history. ABSENCE OF AN ENTRY is "
            "itself a strong signal for AI-generated artists — record absence explicitly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def _normalize_candidate(entry: dict) -> dict:
    aliases = [a.get("name") for a in (entry.get("aliases") or []) if a.get("name")]
    return {
        "mbid": entry.get("id"),
        "name": entry.get("name"),
        "sort_name": entry.get("sort-name"),
        "type": entry.get("type"),
        "country": entry.get("country"),
        "score": entry.get("score"),
        "disambiguation": entry.get("disambiguation"),
        "aliases": aliases,
    }


@rate_limited(1.0)
def lookup_musicbrainz(artist_name: str, **_: Any) -> dict:
    """Search MusicBrainz; return found-flag plus candidate matches."""
    session = make_session()
    payload = get_json(
        session,
        SEARCH_URL,
        params={"query": artist_name, "fmt": "json", "limit": 10},
    )
    raw_artists = payload.get("artists") or []
    candidates = [_normalize_candidate(a) for a in raw_artists]
    loose_matches = [c for c in candidates if (c.get("score") or 0) >= LOOSE_MATCH_SCORE]

    query_normalized = artist_name.strip().casefold()
    exact = [
        c for c in candidates
        if (c.get("name") or "").strip().casefold() == query_normalized
        or any((alias or "").strip().casefold() == query_normalized for alias in c.get("aliases", []))
    ]

    return {
        "query": artist_name,
        "found": bool(loose_matches),
        "found_exact": bool(exact),
        "total_count": payload.get("count", len(candidates)),
        "candidates": candidates[:5],
        "exact_match": exact[0] if exact else None,
    }


RUNNERS = {"lookup_musicbrainz": lookup_musicbrainz}

"""MusicBrainz API — no auth required, but UA mandatory; 1 req/sec hard limit.

Docs: https://musicbrainz.org/doc/MusicBrainz_API

PRESENCE in MusicBrainz is NOT inherently a human signal — distributors
(DistroKid, TuneCore, CD Baby, etc.) auto-submit stub entries to MB for every
artist they handle, AI projects included. The bare existence of an MB entry
proves only that the artist's streaming URLs got mechanically scraped, not
that any editor vetted the entry.

What IS a strong human signal: the *richness* of the entry. Real human
artists accumulate:
  - type:    "Group" or "Person" (set by editors)
  - country: ISO code
  - ISNI:    industry-grade identifier
  - life-span: begin date (when active)
  - member relations (for groups): named musicians
  - label relations: real labels
  - aliases:  prior names, transliterations
  - non-streaming URL relations: official site, Bandcamp, Wikipedia, etc.

Stub entries have none of that — only auto-imported "free streaming" /
"streaming" URL relations pointing at Spotify, Deezer, Apple Music.

This module classifies each found entry as `stub | partial | full` so the
rubric can treat them differently.
"""

from __future__ import annotations

import logging
from typing import Any

from ._http import get_json, make_session, rate_limited

logger = logging.getLogger(__name__)

SEARCH_URL = "https://musicbrainz.org/ws/2/artist"
ARTIST_URL = "https://musicbrainz.org/ws/2/artist"  # /<mbid> appended for lookup
LOOSE_MATCH_SCORE = 75  # MB solr score threshold for loose-match candidates

# Relation `type` values that distributors auto-import. Counting these as
# "real" relations would defeat the stub detection — they fire on every
# distributor-aggregated entry, AI or human.
AUTO_IMPORT_RELATION_TYPES = frozenset({
    "free streaming",
    "streaming",
    "download for free",
    "purchase for download",
    "purchase for mail-order",
})

LOOKUP_INC = "aliases+url-rels+artist-rels+label-rels+release-groups+ratings"


TOOLS = [
    {
        "name": "lookup_musicbrainz",
        "description": (
            "Search MusicBrainz for an artist. On an exact-name match, does a "
            "follow-up lookup to fetch the full artist record (relations, ISNI, "
            "life-span, label affiliations) and classifies the entry quality as "
            "stub | partial | full. CRITICAL: a STUB entry — auto-imported by a "
            "distributor with no type, country, ISNI, or meaningful relations — "
            "is NOT a human signal. Distributors auto-submit stubs for AI artists "
            "too. Only `entry_quality=full` (editorially curated metadata) is a "
            "strong human signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


# --- Rate-limited HTTP --------------------------------------------------------


@rate_limited(1.0)
def _mb_get(url: str, params: dict[str, Any]) -> dict:
    """Single MB GET, gated by the per-second floor at the HTTP level so
    multiple in-investigation calls don't all fire at once."""
    session = make_session()
    return get_json(session, url, params=params)


# --- Normalization -----------------------------------------------------------


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


def _classify_entry_quality(record: dict) -> str:
    """stub | partial | full — based on the count of populated curated fields.

    The classifier deliberately ignores auto-import streaming URLs: those fire
    on every distributor-aggregated entry, including AI ones.
    """
    relations = record.get("relations") or []
    meaningful_relations = [
        r for r in relations
        if r.get("type") and r.get("type") not in AUTO_IMPORT_RELATION_TYPES
    ]
    populated_count = sum([
        bool(record.get("type")),
        bool(record.get("country")),
        bool(record.get("disambiguation") or ""),
        bool((record.get("life-span") or {}).get("begin")),
        len(record.get("isnis") or []) > 0,
        len(record.get("aliases") or []) > 0,
        len(meaningful_relations) > 0,
    ])
    # Max possible: 7. Tuning: 4+ feels editorially curated; 0–1 is stub.
    if populated_count >= 4:
        return "full"
    if populated_count >= 2:
        return "partial"
    return "stub"


def _summarize_full_record(record: dict) -> dict:
    """Extract the rubric-relevant fields from /artist/{mbid}?inc=… payload."""
    life_span = record.get("life-span") or {}
    relations = record.get("relations") or []
    aliases = [a.get("name") for a in (record.get("aliases") or []) if a.get("name")]
    relation_types_counter: dict[str, int] = {}
    meaningful_count = 0
    for r in relations:
        t = r.get("type")
        if not t:
            continue
        relation_types_counter[t] = relation_types_counter.get(t, 0) + 1
        if t not in AUTO_IMPORT_RELATION_TYPES:
            meaningful_count += 1
    return {
        "type": record.get("type"),
        "country": record.get("country"),
        "disambiguation": record.get("disambiguation") or None,
        "life_span_begin": life_span.get("begin"),
        "life_span_end": life_span.get("end"),
        "isni_count": len(record.get("isnis") or []),
        "alias_count": len(aliases),
        "aliases_sample": aliases[:5],
        "rating_votes": (record.get("rating") or {}).get("votes-count", 0),
        "relation_count": len(relations),
        "relation_count_meaningful": meaningful_count,
        "relation_types": relation_types_counter,
        "release_group_count": len(record.get("release-groups") or []),
        "entry_quality": _classify_entry_quality(record),
    }


# --- Main entry --------------------------------------------------------------


def lookup_musicbrainz(artist_name: str, **_: Any) -> dict:
    """Search → if exact match, also do a /artist/{mbid} lookup for richness.

    Returns a dict with `found`, `found_exact`, `candidates`, and (when an
    exact match exists) an `exact_match` block whose `entry_quality` field
    classifies the curation level of the record.
    """
    search_payload = _mb_get(
        SEARCH_URL,
        params={"query": artist_name, "fmt": "json", "limit": 10},
    )
    raw_artists = search_payload.get("artists") or []
    candidates = [_normalize_candidate(a) for a in raw_artists]
    loose_matches = [c for c in candidates if (c.get("score") or 0) >= LOOSE_MATCH_SCORE]

    query_normalized = artist_name.strip().casefold()
    exact = [
        c for c in candidates
        if (c.get("name") or "").strip().casefold() == query_normalized
        or any(
            (alias or "").strip().casefold() == query_normalized
            for alias in c.get("aliases", [])
        )
    ]

    result: dict[str, Any] = {
        "query": artist_name,
        "found": bool(loose_matches),
        "found_exact": bool(exact),
        "total_count": search_payload.get("count", len(candidates)),
        "candidates": candidates[:5],
        "exact_match": exact[0] if exact else None,
    }

    if exact and exact[0].get("mbid"):
        mbid = exact[0]["mbid"]
        try:
            full_record = _mb_get(
                f"{ARTIST_URL}/{mbid}",
                params={"inc": LOOKUP_INC, "fmt": "json"},
            )
            summary = _summarize_full_record(full_record)
            result["exact_match"] = {**result["exact_match"], **summary}
        except Exception:
            # Full-record lookup failure shouldn't kill the search result.
            # The agent still sees the search hit and can reason without
            # the richness data (will read `entry_quality` as missing).
            logger.exception("MB full-record lookup for %s failed", mbid)
            result["exact_match"]["entry_quality"] = "unknown"

    return result


RUNNERS = {"lookup_musicbrainz": lookup_musicbrainz}

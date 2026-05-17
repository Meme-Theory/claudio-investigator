"""iTunes Search API — no auth, generous unenforced limits.

Docs: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/

Used as the first cheap broad-coverage call: confirms an artist exists in the
Apple catalog and pulls release dates, album list, artwork URLs, country, and
genre.

The free iTunes endpoint has no documented rate limit. We don't apply one
here; if we start seeing 429s, add a `rate_limited(0.1)` decorator.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ._http import get_json, make_session

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"

# Cap the album list we return to the model. Large AI catalogs (50+ releases)
# blow up the token budget with negligible signal beyond what
# `release_year_histogram` already encodes. The signal we care about is
# "is the catalog big and recent?" — not the title of release #37.
ALBUM_SAMPLE_LIMIT = 15

TOOLS = [
    {
        "name": "lookup_itunes",
        "description": (
            "Search iTunes for an artist. Returns artist metadata including release "
            "dates, album list, artwork URLs, and country. Use this as the first cheap "
            "broad-coverage call for any artist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "country": {"type": "string", "default": "us"},
            },
            "required": ["artist_name"],
        },
    },
]


def _normalize_album(entry: dict) -> dict:
    return {
        "id": entry.get("collectionId"),
        "name": entry.get("collectionName"),
        "release_date": entry.get("releaseDate"),
        "track_count": entry.get("trackCount"),
        "artwork_url": entry.get("artworkUrl100"),
        "url": entry.get("collectionViewUrl"),
        "explicit": entry.get("collectionExplicitness") == "explicit",
    }


def lookup_itunes(artist_name: str, country: str = "us", **_: Any) -> dict:
    """Search iTunes; if found, also fetch the artist's album discography.

    Returns a flat dict the agent can reason about. `found: false` is a
    normal answer, not an error.
    """
    session = make_session()

    search_payload = get_json(
        session,
        SEARCH_URL,
        params={
            "term": artist_name,
            "entity": "musicArtist",
            "country": country,
            "limit": 5,
        },
    )
    results = search_payload.get("results") or []
    if not results:
        return {"found": False, "query": artist_name, "country": country}

    primary = results[0]
    artist_id = primary.get("artistId")
    if artist_id is None:
        return {"found": False, "query": artist_name, "country": country, "reason": "missing artistId"}

    # Pull albums via /lookup with entity=album.
    lookup_payload = get_json(
        session,
        LOOKUP_URL,
        params={"id": artist_id, "entity": "album", "country": country, "limit": 200},
    )
    lookup_results = lookup_payload.get("results") or []

    # First entry of /lookup is the artist itself; the rest are albums.
    albums = [_normalize_album(e) for e in lookup_results if e.get("wrapperType") == "collection"]
    release_dates = sorted(a["release_date"] for a in albums if a.get("release_date"))

    year_histogram = dict(sorted(
        Counter(
            d[:4] for d in release_dates if d and len(d) >= 4
        ).items()
    ))

    # Most-recent-first; truncate so 50-album AI catalogs don't blow up
    # tool-result tokens. The histogram preserves velocity info; sample
    # gives the model concrete titles to reason about.
    albums_sorted = sorted(
        albums, key=lambda a: a.get("release_date") or "", reverse=True
    )
    albums_sample = albums_sorted[:ALBUM_SAMPLE_LIMIT]

    return {
        "found": True,
        "query": artist_name,
        "country": country,
        "canonical_name": primary.get("artistName"),
        "artist_id": artist_id,
        "primary_genre": primary.get("primaryGenreName"),
        "artist_url": primary.get("artistLinkUrl"),
        "album_count": len(albums),
        "albums_returned": len(albums_sample),
        "albums_truncated": len(albums) > ALBUM_SAMPLE_LIMIT,
        "albums": albums_sample,
        "release_year_histogram": year_histogram,
        "earliest_release_date": release_dates[0] if release_dates else None,
        "latest_release_date": release_dates[-1] if release_dates else None,
        "other_matches": [
            {"name": r.get("artistName"), "id": r.get("artistId")}
            for r in results[1:]
        ],
    }


RUNNERS = {"lookup_itunes": lookup_itunes}

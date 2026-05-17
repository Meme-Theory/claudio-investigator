"""Discogs API — free token, 60 req/min anon, 240/min auth.

Docs: https://www.discogs.com/developers

Physical-release presence is the rubric-relevant signal here. The bare
existence of a Discogs ARTIST entry is registration-level and gameable
(anyone can submit). The presence of an actual physical-release entry
(vinyl, CD, cassette) is artifact-level — distributors don't auto-press
records — and IS a strong human signal per the rubric.

This tool surfaces both: artist presence + physical-release count.
"""

from __future__ import annotations

import os
from typing import Any

from ._http import get_json, make_session

SEARCH_URL = "https://api.discogs.com/database/search"
ARTIST_URL = "https://api.discogs.com/artists"

# Discogs format strings indicating physical media. Heuristic — Discogs format
# field is a free-text list separated by commas, so we substring-match.
# "File" / "WEB" / "Digital" are the digital-only markers; everything else
# we treat as physical evidence.
DIGITAL_FORMAT_MARKERS = frozenset({"file", "web", "digital"})


TOOLS = [
    {
        "name": "lookup_discogs",
        "description": (
            "Search Discogs for an artist and classify their releases as "
            "physical vs digital-only. PHYSICAL releases (vinyl, CD, cassette) "
            "are a STRONG human signal — distributors don't auto-press records. "
            "Absence of physical releases for an artist with a sizeable streaming "
            "catalog is the `no-physical-release` marker. Returns physical_count, "
            "digital_count, and a sample of release titles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"artist_name": {"type": "string"}},
            "required": ["artist_name"],
        },
    },
]


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("DISCOGS_TOKEN")
    if not token:
        raise RuntimeError("DISCOGS_TOKEN must be set in the environment.")
    return {"Authorization": f"Discogs token={token}"}


def _is_physical(release: dict) -> bool:
    """Heuristic on Discogs release format strings.

    Discogs `format` is a comma-separated descriptive string (e.g.,
    "Vinyl, LP, Album, Stereo" or "File, MP3, Album"). Discogs convention:
    digital-only releases include "File" (or "Web" / "Digital") in the
    format list; physical pressings do not. So: any digital marker present
    → digital-only; otherwise → physical.

    Earlier version had a subtraction bug ("tokens - DIGITAL_MARKERS gives
    the physical tokens") that misclassified hybrid format strings like
    "File, MP3, EP" as physical because subtracting "file" still left
    non-digital tokens behind.
    """
    fmt = (release.get("format") or "").lower()
    if not fmt:
        return False
    tokens = {t.strip() for t in fmt.split(",")}
    return not (tokens & DIGITAL_FORMAT_MARKERS)


def lookup_discogs(artist_name: str, **_: Any) -> dict:
    session = make_session()
    headers = _auth_headers()

    search_payload = get_json(
        session,
        SEARCH_URL,
        params={"q": artist_name, "type": "artist", "per_page": 5},
        headers=headers,
    )
    results = [r for r in (search_payload.get("results") or []) if r.get("type") == "artist"]
    if not results:
        return {"found": False, "query": artist_name}

    top = results[0]
    artist_id = top.get("id")
    if not artist_id:
        return {"found": False, "query": artist_name, "reason": "missing artist id"}

    try:
        releases_payload = get_json(
            session,
            f"{ARTIST_URL}/{artist_id}/releases",
            params={"per_page": 100, "sort": "year", "sort_order": "desc"},
            headers=headers,
        )
        releases = releases_payload.get("releases") or []
    except Exception:
        # If the releases call fails, surface artist presence but no detail.
        releases = []

    physical = [r for r in releases if _is_physical(r)]
    digital = [r for r in releases if not _is_physical(r)]

    sample = [
        {
            "title": r.get("title"),
            "year": r.get("year"),
            "format": r.get("format"),
            "type": r.get("type"),
        }
        for r in releases[:10]
    ]

    return {
        "query": artist_name,
        "found": True,
        "discogs_id": artist_id,
        "canonical_name": top.get("title"),
        "url": top.get("uri"),
        "release_count": len(releases),
        "physical_release_count": len(physical),
        "digital_only_release_count": len(digital),
        "has_physical_release": bool(physical),
        "sample_releases": sample,
    }


RUNNERS = {"lookup_discogs": lookup_discogs}

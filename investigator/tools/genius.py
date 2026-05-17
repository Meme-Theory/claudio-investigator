"""Genius API — free token, generous limits.

Docs: https://docs.genius.com/

LIMITATION: the official Genius API does NOT return lyric text. It returns
song metadata (title, URL to genius.com, popularity stats) only. Lyrics live
on the genius.com pages themselves and require either scraping or a wrapper
like `lyricsgenius`. We intentionally do not scrape here — Genius's HTML
structure is JS-rendered and the `data-lyrics-container` divs are brittle.

What this tool actually does:
  1. Search Genius for any song matching the query string
  2. Pick the primary_artist from the best matching hit
  3. Fetch top songs metadata for that artist

The agent should treat this as "I have URLs and titles, not text." Flagging
`gpt-lyric-patterns` requires actual lyric text — without scraping, this
marker can't be evidenced from Genius alone.
"""

from __future__ import annotations

import os
from typing import Any

from ._http import get_json, make_session

API_BASE = "https://api.genius.com"
SEARCH_URL = f"{API_BASE}/search"
ARTISTS_URL = f"{API_BASE}/artists"


TOOLS = [
    {
        "name": "get_genius_lyrics",
        "description": (
            "Look up a Genius artist by name. Returns the resolved artist ID, "
            "name, and metadata for up to N top songs (title, URL, popularity). "
            "IMPORTANT: the Genius API does NOT return lyric text — only URLs "
            "to genius.com pages. You cannot flag `gpt-lyric-patterns` from "
            "the data this tool returns; you can only confirm the artist has "
            "a Genius presence and observe song titles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {"type": "string"},
                "max_tracks": {"type": "integer", "default": 3, "minimum": 1, "maximum": 20},
            },
            "required": ["artist_name"],
        },
    },
]


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("GENIUS_TOKEN")
    if not token:
        raise RuntimeError("GENIUS_TOKEN must be set in the environment.")
    return {"Authorization": f"Bearer {token}"}


def _normalize_song(entry: dict) -> dict:
    stats = entry.get("stats") or {}
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "title_with_featured": entry.get("title_with_featured"),
        "url": entry.get("url"),
        "release_date_for_display": entry.get("release_date_for_display"),
        "annotation_count": entry.get("annotation_count"),
        "pageviews": stats.get("pageviews"),
    }


def _pick_artist(hits: list[dict], query: str) -> dict | None:
    """From a search response's hits, find the primary_artist that best matches."""
    query_normalized = query.strip().casefold()
    fallback = None
    for hit in hits:
        result = hit.get("result") or {}
        primary = result.get("primary_artist") or {}
        if not primary.get("id"):
            continue
        if (primary.get("name") or "").strip().casefold() == query_normalized:
            return primary
        if fallback is None:
            fallback = primary
    return fallback


def get_genius_lyrics(artist_name: str, max_tracks: int = 3, **_: Any) -> dict:
    session = make_session()
    headers = _auth_headers()

    search_payload = get_json(session, SEARCH_URL, params={"q": artist_name}, headers=headers)
    hits = (search_payload.get("response") or {}).get("hits") or []
    if not hits:
        return {"found": False, "query": artist_name, "reason": "no search hits"}

    artist = _pick_artist(hits, artist_name)
    if not artist or not artist.get("id"):
        return {"found": False, "query": artist_name, "reason": "no matching artist in hits"}

    artist_id = artist["id"]
    songs_payload = get_json(
        session,
        f"{ARTISTS_URL}/{artist_id}/songs",
        params={"per_page": max_tracks, "sort": "popularity"},
        headers=headers,
    )
    songs = (songs_payload.get("response") or {}).get("songs") or []

    return {
        "found": True,
        "query": artist_name,
        "artist_id": artist_id,
        "artist_name": artist.get("name"),
        "artist_url": artist.get("url"),
        "song_count_returned": len(songs),
        "songs": [_normalize_song(s) for s in songs],
        "note": (
            "Genius API does not expose lyric text. URLs are provided; "
            "`gpt-lyric-patterns` cannot be evidenced from this tool alone."
        ),
    }


RUNNERS = {"get_genius_lyrics": get_genius_lyrics}
